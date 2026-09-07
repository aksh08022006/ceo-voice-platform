"""Operator-only authenticated backups of allowlisted application data; no auth tables."""

import hashlib
import json
import os
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from ceo_voice.core.exceptions import ConfigurationError
from ceo_voice.workspace.database import PostgresDatabase, SQLDatabase, SQLiteDatabase, Transaction
from ceo_voice.workspace.schema import (
    SCHEMA,
    SCHEMA_VERSION,
    postgres_history_guards,
    sqlite_history_guards,
)

MAX_PLAINTEXT_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 96 * 1024 * 1024
MAX_ROWS = 50_000
# Insert parents before references. Every column is fixed; archives cannot choose SQL identifiers.
TABLES: dict[str, tuple[str, ...]] = {
    "cv_schema_migrations": ("version",),
    "cv_workspace_provisioning": ("workspace_id",),
    "cv_actor_locks": ("workspace_id", "user_id"),
    "cv_workspace_members": ("workspace_id", "user_id", "role", "active"),
    "cv_workflows": (
        "workspace_id",
        "id",
        "owner_user_id",
        "profile_slug",
        "head_revision",
        "active_run_id",
        "current_review_id",
        "created_at",
        "updated_at",
    ),
    "cv_model_runs": (
        "workspace_id",
        "id",
        "actor_user_id",
        "workflow_id",
        "operation",
        "idempotency_key",
        "request_sha256",
        "expected_revision",
        "state",
        "lease_token",
        "lease_expires_at",
        "result_revision",
        "error_code",
        "created_at",
        "updated_at",
    ),
    "cv_review_runs": ("workspace_id", "id", "workflow_id", "candidate_sha256", "eligible"),
    "cv_workflow_revisions": (
        "workspace_id",
        "workflow_id",
        "revision",
        "actor_user_id",
        "kind",
        "encrypted_payload",
        "candidate_sha256",
        "review_run_id",
        "review_eligible",
        "model_run_id",
        "created_at",
    ),
    "cv_workflow_reviews": (
        "workspace_id",
        "id",
        "workflow_id",
        "revision",
        "candidate_sha256",
        "review_run_id",
        "reviewer_user_id",
        "decision",
        "note",
        "created_at",
    ),
}
ORDER_BY = {
    "cv_schema_migrations": "version",
    "cv_workspace_provisioning": "workspace_id",
    "cv_actor_locks": "workspace_id,user_id",
    "cv_workspace_members": "workspace_id,user_id",
    "cv_workflows": "workspace_id,id",
    "cv_model_runs": "workspace_id,id",
    "cv_review_runs": "workspace_id,id",
    "cv_workflow_revisions": "workspace_id,workflow_id,revision",
    "cv_workflow_reviews": "workspace_id,id",
}


@dataclass(frozen=True)
class BackupSummary:
    source_schema: str
    rows: int
    data_sha256: str


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _namespace(database: SQLDatabase) -> str:
    if isinstance(database, PostgresDatabase):
        return database._schema
    if isinstance(database, SQLiteDatabase):
        return database.path.stem
    raise ConfigurationError("unsupported backup database adapter")


def _cipher(key: str) -> Fernet:
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise ConfigurationError("backup encryption key is missing or invalid") from exc


def _require_operator(tx: Transaction, database: SQLDatabase) -> None:
    if database.dialect == "postgres":
        role = tx.one(
            "SELECT has_schema_privilege(current_user, ?, 'CREATE') AS allowed",
            (_namespace(database),),
        )
        if role is None or not role["allowed"]:
            raise ConfigurationError(
                "workspace backup requires the database administrator credential"
            )


def _summary(archive: dict[str, Any]) -> BackupSummary:
    return BackupSummary(
        source_schema=archive["source_schema"],
        rows=sum(len(rows) for rows in archive["tables"].values()),
        data_sha256=archive["data_sha256"],
    )


def create_backup(database: SQLDatabase, destination: Path, key: str) -> BackupSummary:
    """Export one consistent snapshot and write a new mode-0600 authenticated archive."""
    cipher = _cipher(key)
    tables: dict[str, list[dict[str, Any]]] = {}
    total_bytes, row_count = 0, 0
    with database.transaction(repeatable_read=True) as tx:
        _require_operator(tx, database)
        for table, columns in TABLES.items():
            rows = []
            statement = f"SELECT {','.join(columns)} FROM {table} ORDER BY {ORDER_BY[table]}"
            for row in tx.iterate(statement):
                total_bytes += len(_canonical(row)) + 1
                row_count += 1
                if total_bytes > MAX_PLAINTEXT_BYTES or row_count > MAX_ROWS:
                    raise ConfigurationError(
                        "workspace backup exceeds the configured archive bound"
                    )
                rows.append(row)
            tables[table] = rows
    if tables["cv_schema_migrations"] != [{"version": SCHEMA_VERSION}]:
        raise ConfigurationError("workspace backup schema version is unsupported")
    archive = {
        "archive_version": 1,
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "source_schema": _namespace(database),
        "tables": tables,
        "data_sha256": hashlib.sha256(_canonical(tables)).hexdigest(),
    }
    raw = _canonical(archive)
    if len(raw) > MAX_PLAINTEXT_BYTES:
        raise ConfigurationError("workspace backup exceeds the configured archive bound")
    encrypted = cipher.encrypt(zlib.compress(raw))
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(encrypted)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return _summary(archive)


def _read_archive(source: Path, key: str) -> dict[str, Any]:
    cipher = _cipher(key)
    try:
        with source.open("rb") as input_file:
            encrypted = input_file.read(MAX_ARCHIVE_BYTES + 1)
        if len(encrypted) > MAX_ARCHIVE_BYTES:
            raise ValueError("oversized archive")
        compressed = cipher.decrypt(encrypted)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, MAX_PLAINTEXT_BYTES + 1)
        if len(raw) > MAX_PLAINTEXT_BYTES or not decoder.eof or decoder.unused_data:
            raise ValueError("oversized or malformed compressed archive")
        archive = json.loads(raw)
        if not isinstance(archive, dict) or set(archive) != {
            "archive_version",
            "schema_version",
            "created_at",
            "source_schema",
            "tables",
            "data_sha256",
        }:
            raise ValueError("unexpected manifest")
        if archive["archive_version"] != 1 or archive["schema_version"] != SCHEMA_VERSION:
            raise ValueError("unsupported version")
        if not isinstance(archive["source_schema"], str) or not archive["source_schema"]:
            raise ValueError("missing source identity")
        tables = archive["tables"]
        if not isinstance(tables, dict) or set(tables) != set(TABLES):
            raise ValueError("unexpected tables")
        count = 0
        for table, columns in TABLES.items():
            rows = tables[table]
            if not isinstance(rows, list):
                raise ValueError("invalid rows")
            count += len(rows)
            for row in rows:
                if not isinstance(row, dict) or set(row) != set(columns):
                    raise ValueError("unexpected columns")
                if any(type(value) not in {str, int, type(None)} for value in row.values()):
                    raise ValueError("unexpected cell type")
        if count > MAX_ROWS or tables["cv_schema_migrations"] != [{"version": SCHEMA_VERSION}]:
            raise ValueError("invalid row count or schema version")
        if archive["data_sha256"] != hashlib.sha256(_canonical(tables)).hexdigest():
            raise ValueError("data fingerprint mismatch")
        return archive
    except (InvalidToken, UnicodeError, ValueError, TypeError, zlib.error) as exc:
        raise ConfigurationError(
            "workspace backup could not be authenticated or validated"
        ) from exc


def restore_backup(database: SQLDatabase, source: Path, key: str) -> BackupSummary:
    """Restore only into an explicitly distinct empty namespace, atomically, without UPDATE/DELETE."""
    archive = _read_archive(source, key)
    target = _namespace(database)
    if target in {"public", "neon_auth", archive["source_schema"]} or target.startswith("pg_"):
        raise ConfigurationError("restore requires a distinct non-public destination schema")
    with database.transaction() as tx:
        if database.dialect == "postgres":
            # Includes tables, functions, types, and other namespace-dependent objects.
            occupied = tx.one(
                "SELECT COUNT(*) AS total FROM pg_depend WHERE refclassid='pg_namespace'::regclass AND refobjid=(SELECT oid FROM pg_namespace WHERE nspname=?)",
                (target,),
            )
            assert occupied is not None
            if occupied["total"]:
                raise ConfigurationError("restore destination is not empty")
            exists = tx.one("SELECT 1 AS present FROM pg_namespace WHERE nspname=?", (target,))
            if exists is None:
                # Constructor already validates this identifier; archives never provide it.
                tx.execute(f'CREATE SCHEMA "{target}"')
            tx.execute(f'SET LOCAL search_path TO "{target}", pg_catalog')
            _require_operator(tx, database)
        elif tx.one("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1"):
            raise ConfigurationError("restore destination is not empty")
        tx.execute("CREATE TABLE cv_schema_migrations (version INTEGER PRIMARY KEY)")
        for statement in SCHEMA:
            tx.execute(statement)
        for table, columns in TABLES.items():
            placeholders = ",".join("?" for _ in columns)
            for row in archive["tables"][table]:
                tx.execute(
                    f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
                    tuple(row[column] for column in columns),
                )
        for statement in (
            postgres_history_guards() if database.dialect == "postgres" else sqlite_history_guards()
        ):
            tx.execute(statement)
        # Verify exactly the restored data before committing the transaction.
        restored = {
            table: list(
                tx.iterate(f"SELECT {','.join(columns)} FROM {table} ORDER BY {ORDER_BY[table]}")
            )
            for table, columns in TABLES.items()
        }
        if hashlib.sha256(_canonical(restored)).hexdigest() != archive["data_sha256"]:
            raise ConfigurationError("restored workspace data fingerprint does not match")
    return _summary(archive)
