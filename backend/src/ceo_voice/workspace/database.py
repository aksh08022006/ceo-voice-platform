"""Short-lived SQL transactions; SQLite is explicitly prohibited in production/Vercel."""

import os
import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import certifi

from ceo_voice.core.exceptions import ApplicationError, ConfigurationError, StorageError
from ceo_voice.workspace.schema import (
    SCHEMA,
    SCHEMA_VERSION,
    postgres_history_guards,
    sqlite_history_guards,
)

Row = dict[str, Any]


class Transaction(Protocol):
    def execute(self, sql: str, params: Sequence[object] = ()) -> int: ...
    def one(self, sql: str, params: Sequence[object] = (), *, lock: bool = False) -> Row | None: ...
    def all(self, sql: str, params: Sequence[object] = ()) -> list[Row]: ...
    def iterate(self, sql: str, params: Sequence[object] = ()) -> Iterator[Row]: ...


class _SQLiteTransaction:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def execute(self, sql: str, params: Sequence[object] = ()) -> int:
        return self.connection.execute(sql, tuple(params)).rowcount

    def one(self, sql: str, params: Sequence[object] = (), *, lock: bool = False) -> Row | None:
        row = self.connection.execute(sql, tuple(params)).fetchone()
        return dict(row) if row is not None else None

    def all(self, sql: str, params: Sequence[object] = ()) -> list[Row]:
        return [dict(row) for row in self.connection.execute(sql, tuple(params)).fetchall()]

    def iterate(self, sql: str, params: Sequence[object] = ()) -> Iterator[Row]:
        for row in self.connection.execute(sql, tuple(params)):
            yield dict(row)


class _PostgresTransaction:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def execute(self, sql: str, params: Sequence[object] = ()) -> int:
        return int(self.connection.execute(sql.replace("?", "%s"), tuple(params)).rowcount)

    def one(self, sql: str, params: Sequence[object] = (), *, lock: bool = False) -> Row | None:
        statement = sql + (" FOR UPDATE" if lock else "")
        row = self.connection.execute(statement.replace("?", "%s"), tuple(params)).fetchone()
        return dict(row) if row is not None else None

    def all(self, sql: str, params: Sequence[object] = ()) -> list[Row]:
        return [
            dict(row)
            for row in self.connection.execute(sql.replace("?", "%s"), tuple(params)).fetchall()
        ]

    def iterate(self, sql: str, params: Sequence[object] = ()) -> Iterator[Row]:
        # Backup reads stream in bounded batches, including multi-megabyte snapshot cells.
        with self.connection.cursor(name=f"cv_backup_{uuid4().hex}") as cursor:
            cursor.itersize = 16
            cursor.execute(sql.replace("?", "%s"), tuple(params))
            for row in cursor:
                yield dict(row)


class SQLDatabase:
    """Transaction boundary implemented by production and local adapters."""

    dialect: Literal["sqlite", "postgres"]

    def transaction(self, *, repeatable_read: bool = False) -> AbstractContextManager[Transaction]:
        raise NotImplementedError

    def migrate(self) -> None:
        """Explicit deployment/CLI migration; never invoked automatically on HTTP requests."""

        with self.transaction() as transaction:
            if self.dialect == "postgres":
                transaction.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(current_schema() || ':ceo_voice_migration'))"
                )
            transaction.execute(
                "CREATE TABLE IF NOT EXISTS cv_schema_migrations (version INTEGER PRIMARY KEY)"
            )
            versions = transaction.all("SELECT version FROM cv_schema_migrations")
            if versions:
                if {row["version"] for row in versions} != {SCHEMA_VERSION}:
                    raise ConfigurationError("workspace database schema version is unsupported")
                return
            for statement in SCHEMA:
                transaction.execute(statement)
            guards = (
                sqlite_history_guards() if self.dialect == "sqlite" else postgres_history_guards()
            )
            for statement in guards:
                transaction.execute(statement)
            transaction.execute(
                "INSERT INTO cv_schema_migrations(version) VALUES (?)", (SCHEMA_VERSION,)
            )


class SQLiteDatabase(SQLDatabase):
    dialect: Literal["sqlite", "postgres"] = "sqlite"

    def __init__(self, path: Path, *, environment: Literal["development", "test"]) -> None:
        if environment not in {"development", "test"} or os.environ.get("VERCEL"):
            raise ConfigurationError(
                "SQLite workflow storage is allowed only for local development/tests"
            )
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def transaction(self, *, repeatable_read: bool = False) -> Iterator[Transaction]:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            # Serializes local writers across distinct connections/processes, matching the CAS contract.
            connection.execute("BEGIN IMMEDIATE")
            yield _SQLiteTransaction(connection)
            connection.commit()
        except ApplicationError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise StorageError("workspace database transaction failed", retryable=True) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class PostgresDatabase(SQLDatabase):
    dialect: Literal["sqlite", "postgres"] = "postgres"

    def __init__(
        self,
        database_url: str,
        *,
        allow_insecure_local: bool = False,
        schema: str = "public",
        sslrootcert: str | None = None,
    ) -> None:
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise ConfigurationError(
                "PostgreSQL workflow storage requires a PostgreSQL connection URL"
            )
        if re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", schema) is None:
            raise ConfigurationError("PostgreSQL schema must be a simple lowercase identifier")
        self._schema = schema
        self._database_url = database_url
        parsed = urlsplit(database_url)
        query = parse_qs(parsed.query)
        if allow_insecure_local and (
            parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or "host" in query
            or "hostaddr" in query
            or "service" in query
        ):
            raise ConfigurationError(
                "unencrypted PostgreSQL is allowed only on explicit loopback test hosts"
            )
        # Override weaker provider URL defaults: encryption alone does not authenticate a server.
        self._sslmode = "disable" if allow_insecure_local else "verify-full"
        self._sslrootcert = "" if allow_insecure_local else (sslrootcert or certifi.where())

    @contextmanager
    def transaction(self, *, repeatable_read: bool = False) -> Iterator[Transaction]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise ConfigurationError("PostgreSQL workflow storage requires psycopg 3") from exc
        try:
            # No transaction spans a model request. A provider's pooling URL may be supplied.
            with psycopg.connect(
                self._database_url,
                row_factory=dict_row,
                connect_timeout=10,
                prepare_threshold=None,
                sslmode=self._sslmode,
                sslrootcert=self._sslrootcert,
            ) as connection:
                if repeatable_read:
                    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                connection.execute(
                    "SELECT set_config('search_path', %s, true)",
                    (f'"{self._schema}", pg_catalog',),
                )
                connection.execute("SET LOCAL statement_timeout = '15s'")
                connection.execute("SET LOCAL lock_timeout = '10s'")
                yield _PostgresTransaction(connection)
        except ApplicationError:
            raise
        except psycopg.Error as exc:
            raise StorageError("workspace database transaction failed", retryable=True) from exc
