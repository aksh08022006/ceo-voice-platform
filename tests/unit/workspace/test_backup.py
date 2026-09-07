"""Recovery preserves real workflow semantics and rejects unsafe or malformed archives."""

import hashlib
import json
import os
import stat
import zlib
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from ceo_voice.core.exceptions import ConfigurationError, StorageError
from ceo_voice.workspace import SQLiteDatabase, WorkflowRepository, WorkspaceScope, backup
from ceo_voice.workspace.backup import create_backup, restore_backup
from ceo_voice.workspace.contracts import SnapshotWrite


def populated(tmp_path: Path) -> tuple[SQLiteDatabase, str]:
    source = SQLiteDatabase(tmp_path / "source.sqlite", environment="test")
    source.migrate()
    repo = WorkflowRepository(source)
    scope = WorkspaceScope(workspace_id="workspace", user_id="verified-owner")
    repo.bootstrap_owner_if_empty(scope)
    claim = repo.reserve_run(
        scope,
        idempotency_key="initial",
        operation="generate",
        request_sha256="a" * 64,
        profile_slug="synthetic",
    )
    assert claim.lease_token is not None
    repo.mark_dispatched(scope, claim.run.id, claim.lease_token)
    review_id = uuid4()
    value = SnapshotWrite(
        encrypted_payload=Fernet(Fernet.generate_key()).encrypt(b"Private draft").decode(),
        candidate_sha256=hashlib.sha256(b"Private draft").hexdigest(),
        review_run_id=review_id,
        review_eligible=True,
    )
    repo.complete_run(scope, claim.run.id, claim.lease_token, value)
    repo.record_review(
        scope,
        claim.run.workflow_id,
        expected_revision=0,
        candidate_sha256=value.candidate_sha256,
        review_run_id=review_id,
        decision="approved",
        note="Private review note",
    )
    return source, Fernet.generate_key().decode()


def test_round_trip_preserves_approved_revision_and_idempotency(tmp_path: Path) -> None:
    source, key = populated(tmp_path)
    path = tmp_path / "backup.enc"
    expected = create_backup(source, path, key)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert b"Private review note" not in path.read_bytes()
    destination = SQLiteDatabase(tmp_path / "restored.sqlite", environment="test")
    assert restore_backup(destination, path, key) == expected
    repo = WorkflowRepository(destination)
    workflows = repo.list_workflows("workspace")
    original = WorkflowRepository(source).get_approved_revision("workspace", workflows[0].id)
    assert repo.get_approved_revision("workspace", workflows[0].id) == original
    assert (
        repo.get_run(
            WorkspaceScope(workspace_id="workspace", user_id="verified-owner"), "initial"
        ).state
        == "completed"
    )
    with pytest.raises(StorageError), destination.transaction() as tx:
        tx.execute("DELETE FROM cv_workflow_revisions")


def test_backup_refuses_overwrite_and_restore_refuses_live_or_nonempty_target(
    tmp_path: Path,
) -> None:
    source, key = populated(tmp_path)
    archive = tmp_path / "backup.enc"
    create_backup(source, archive, key)
    original = archive.read_bytes()
    with pytest.raises(FileExistsError):
        create_backup(source, archive, key)
    assert archive.read_bytes() == original
    for name in ("source", "public", "neon_auth", "pg_catalog"):
        with pytest.raises(ConfigurationError, match="distinct"):
            restore_backup(
                SQLiteDatabase(tmp_path / f"{name}.sqlite", environment="test"), archive, key
            )
    target = SQLiteDatabase(tmp_path / "occupied.sqlite", environment="test")
    with target.transaction() as tx:
        tx.execute("CREATE TABLE unrelated (value TEXT)")
        tx.execute("INSERT INTO unrelated VALUES ('keep me')")
    with pytest.raises(ConfigurationError, match="not empty"):
        restore_backup(target, archive, key)
    with target.transaction() as tx:
        assert tx.one("SELECT value FROM unrelated") == {"value": "keep me"}


def test_tamper_wrong_key_and_compression_bomb_are_rejected_before_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, key = populated(tmp_path)
    archive = tmp_path / "backup.enc"
    create_backup(source, archive, key)
    target = SQLiteDatabase(tmp_path / "restored.sqlite", environment="test")
    with pytest.raises(ConfigurationError, match="authenticated"):
        restore_backup(target, archive, Fernet.generate_key().decode())
    original = archive.read_bytes()
    archive.write_bytes(original[:-10] + b"tampered00")
    with pytest.raises(ConfigurationError, match="authenticated"):
        restore_backup(target, archive, key)
    monkeypatch.setattr(backup, "MAX_PLAINTEXT_BYTES", 100)
    archive.write_bytes(Fernet(key).encrypt(zlib.compress(b"x" * 1000)))
    with pytest.raises(ConfigurationError, match="authenticated"):
        restore_backup(target, archive, key)
    with target.transaction() as tx:
        assert tx.one("SELECT name FROM sqlite_master") is None


@pytest.mark.parametrize(
    "mutation", ["table", "column", "cell", "digest", "version", "rows", "manifest"]
)
def test_archive_allowlists_and_integrity_are_checked(tmp_path: Path, mutation: str) -> None:
    source, key = populated(tmp_path)
    archive = tmp_path / "backup.enc"
    create_backup(source, archive, key)
    value = json.loads(zlib.decompress(Fernet(key).decrypt(archive.read_bytes())))
    if mutation == "table":
        value["tables"]["neon_auth.session"] = []
    elif mutation == "column":
        value["tables"]["cv_schema_migrations"][0]["untrusted_sql"] = "secret"
    elif mutation == "cell":
        value["tables"]["cv_schema_migrations"][0]["version"] = {"not": "scalar"}
    elif mutation == "digest":
        value["data_sha256"] = "bad"
    elif mutation == "version":
        value["schema_version"] = 999
    elif mutation == "rows":
        value["tables"]["cv_schema_migrations"] = "invalid"
    else:
        value["unexpected"] = True
    archive.write_bytes(Fernet(key).encrypt(zlib.compress(json.dumps(value).encode())))
    with pytest.raises(ConfigurationError, match="authenticated"):
        restore_backup(
            SQLiteDatabase(tmp_path / "restored.sqlite", environment="test"), archive, key
        )


def test_archive_size_rows_schema_and_key_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, key = populated(tmp_path)
    archive = tmp_path / "backup.enc"
    with pytest.raises(ConfigurationError, match="key"):
        create_backup(source, archive, "invalid-key")
    monkeypatch.setattr(backup, "MAX_ROWS", 1)
    with pytest.raises(ConfigurationError, match="bound"):
        create_backup(source, archive, key)
    assert not archive.exists()
    monkeypatch.setattr(backup, "MAX_ROWS", 50_000)
    create_backup(source, archive, key)
    monkeypatch.setattr(backup, "MAX_ARCHIVE_BYTES", 1)
    with pytest.raises(ConfigurationError, match="authenticated"):
        restore_backup(
            SQLiteDatabase(tmp_path / "restored.sqlite", environment="test"), archive, key
        )
    with source.transaction() as tx:
        tx.execute("UPDATE cv_schema_migrations SET version=999")
    with pytest.raises(ConfigurationError, match="schema version"):
        create_backup(source, tmp_path / "wrong-version.enc", key)


def test_archive_manifest_overhead_is_bounded_and_partial_files_are_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, key = populated(tmp_path)
    archive = tmp_path / "original.fernet"
    create_backup(source, archive, key)
    data = json.loads(zlib.decompress(Fernet(key).decrypt(archive.read_bytes())))
    row_bytes = sum(
        len(backup._canonical(row)) + 1 for rows in data["tables"].values() for row in rows
    )
    monkeypatch.setattr(backup, "MAX_PLAINTEXT_BYTES", row_bytes + 1)
    with pytest.raises(ConfigurationError, match="bound"):
        create_backup(source, tmp_path / "too-large.fernet", key)
    monkeypatch.setattr(backup, "MAX_PLAINTEXT_BYTES", 64 * 1024 * 1024)

    def full_disk(descriptor: int) -> None:
        raise OSError("simulated full volume")

    monkeypatch.setattr(os, "fsync", full_disk)
    partial = tmp_path / "partial.fernet"
    with pytest.raises(OSError, match="full volume"):
        create_backup(source, partial, key)
    assert not partial.exists() and archive.exists()


def test_restore_rejects_type_coercion_and_rolls_back_every_created_object(tmp_path: Path) -> None:
    source, key = populated(tmp_path)
    archive = tmp_path / "backup.enc"
    create_backup(source, archive, key)
    data = json.loads(zlib.decompress(Fernet(key).decrypt(archive.read_bytes())))
    data["tables"]["cv_workflows"][0]["head_revision"] = "0"
    data["data_sha256"] = hashlib.sha256(backup._canonical(data["tables"])).hexdigest()
    archive.write_bytes(Fernet(key).encrypt(zlib.compress(json.dumps(data).encode())))
    destination = SQLiteDatabase(tmp_path / "restored.sqlite", environment="test")
    with pytest.raises(ConfigurationError, match="fingerprint"):
        restore_backup(destination, archive, key)
    with destination.transaction() as tx:
        assert tx.one("SELECT name FROM sqlite_master") is None


def test_backup_requires_postgres_administrator_and_restore_rejects_occupied_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import nullcontext
    from unittest.mock import MagicMock

    from ceo_voice.workspace import PostgresDatabase

    source, key = populated(tmp_path)
    archive = tmp_path / "backup.enc"
    create_backup(source, archive, key)
    postgres = PostgresDatabase("postgresql://example.invalid/db", schema="restored")
    transaction = MagicMock()
    transaction.one.return_value = {"allowed": False}
    monkeypatch.setattr(postgres, "transaction", lambda **kwargs: nullcontext(transaction))
    with pytest.raises(ConfigurationError, match="administrator"):
        create_backup(postgres, tmp_path / "denied.enc", key)
    transaction.one.return_value = {"total": 1}
    with pytest.raises(ConfigurationError, match="not empty"):
        restore_backup(postgres, archive, key)
    transaction.execute.assert_not_called()
