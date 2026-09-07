"""Transaction rollback and verified connection settings without an external database."""

import builtins
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import certifi
import psycopg
import pytest

from ceo_voice.core.exceptions import ConfigurationError, StorageError
from ceo_voice.workspace import PostgresDatabase, SQLiteDatabase


def test_sqlite_rolls_back_unexpected_exceptions_and_rejects_unknown_schema(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "db.sqlite", environment="test")
    db.migrate()
    with pytest.raises(RuntimeError, match="failed after write"), db.transaction() as tx:
        tx.execute("INSERT INTO cv_workspace_members VALUES ('w','u','editor',1)")
        raise RuntimeError("failed after write")
    with db.transaction() as tx:
        assert tx.one("SELECT * FROM cv_workspace_members") is None
        tx.execute("UPDATE cv_schema_migrations SET version=999")
    with pytest.raises(ConfigurationError, match="schema version"):
        db.migrate()


def test_postgres_pins_tls_configures_transaction_and_maps_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.rowcount = 1
    connection.execute.return_value.fetchone.return_value = {"id": "record"}
    connection.execute.return_value.fetchall.return_value = [{"id": "record"}]
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(psycopg, "connect", connect)
    db = PostgresDatabase(
        "postgresql://example.invalid/db?sslmode=disable", schema="cv_test_settings"
    )
    with db.transaction() as tx:
        assert tx.execute("UPDATE t SET id=?", ("record",)) == 1
        assert tx.one("SELECT id FROM t WHERE id=?", ("record",), lock=True) == {"id": "record"}
        assert tx.all("SELECT id FROM t") == [{"id": "record"}]
        connection.execute.return_value.fetchone.return_value = None
        assert tx.one("SELECT id FROM t") is None
    assert connect.call_args.kwargs["sslmode"] == "verify-full"
    assert connect.call_args.kwargs["sslrootcert"] == certifi.where()
    assert connect.call_args.kwargs["prepare_threshold"] is None
    connection.execute.assert_any_call(
        "SELECT set_config('search_path', %s, true)", ('"cv_test_settings", pg_catalog',)
    )
    connection.execute.assert_any_call("SELECT id FROM t WHERE id=%s FOR UPDATE", ("record",))


def test_postgres_failures_are_sanitized_without_changing_application_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect = MagicMock(side_effect=psycopg.OperationalError("private DSN and credentials"))
    monkeypatch.setattr(psycopg, "connect", connect)
    db = PostgresDatabase("postgresql://example.invalid/db")
    with pytest.raises(StorageError) as error, db.transaction():
        pass
    assert "private" not in error.value.message and error.value.retryable
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connect.side_effect = None
    connect.return_value = connection
    with pytest.raises(ConfigurationError, match="application failure"), db.transaction():
        raise ConfigurationError("application failure")


def test_missing_postgres_driver_has_actionable_configuration_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = builtins.__import__

    def importing(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "psycopg":
            raise ImportError("driver missing")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)
    with (
        pytest.raises(ConfigurationError, match="psycopg 3"),
        PostgresDatabase("postgresql://example.invalid/db").transaction(),
    ):
        pass
