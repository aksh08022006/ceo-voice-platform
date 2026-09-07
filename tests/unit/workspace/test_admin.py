"""Administrative actions require an explicit configured target and preserve existing access."""

from pathlib import Path

import pytest

from ceo_voice.workspace import (
    SQLiteDatabase,
    WorkflowRepository,
    WorkspaceMember,
    WorkspaceScope,
    admin,
)


def test_admin_requires_configured_target_and_never_outputs_secrets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)
    assert admin.main(["migrate"]) == 1
    assert "configured database" in capsys.readouterr().err
    assert admin.main(["--database-env", "invalid.name", "migrate"]) == 1
    assert "variable name" in capsys.readouterr().err
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "private-credential-value")
    assert admin.main(["migrate"]) == 1
    assert "private-credential-value" not in capsys.readouterr().err


def test_admin_migration_and_owner_bootstrap_are_explicit_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database = SQLiteDatabase(tmp_path / "admin.sqlite", environment="test")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "configured-private-target")
    monkeypatch.setattr(admin, "PostgresDatabase", lambda dsn, schema: database)
    assert admin.main(["migrate"]) == 0
    assert admin.main(["bootstrap-owner", "--workspace-id", "test", "--user-id", " "]) == 1
    args = ["bootstrap-owner", "--workspace-id", "test", "--user-id", "owner"]
    assert admin.main(args) == 0
    assert admin.main(args) == 0
    repo = WorkflowRepository(database)
    assert repo.get_member("test", "owner") == WorkspaceMember(
        workspace_id="test", user_id="owner", role="owner"
    )
    assert admin.main(["bootstrap-owner", "--workspace-id", "test", "--user-id", "second"]) == 1
    assert repo.get_member("test", "second") is None
    repo.upsert_member(
        WorkspaceMember(workspace_id="test", user_id="owner", role="owner", active=False)
    )
    assert admin.main(args) == 1
    assert (
        repo.bootstrap_owner_if_empty(WorkspaceScope(workspace_id="test", user_id="owner")) is None
    )
    assert "configured-private-target" not in str(capsys.readouterr())


def test_admin_backup_restore_requires_key_and_explicit_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from cryptography.fernet import Fernet

    source = SQLiteDatabase(tmp_path / "source.sqlite", environment="test")
    source.migrate()
    restored = SQLiteDatabase(tmp_path / "restored.sqlite", environment="test")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "private-target")
    monkeypatch.setattr(
        admin, "PostgresDatabase", lambda dsn, schema: restored if schema == "restored" else source
    )
    monkeypatch.setenv("WORKSPACE_BACKUP_KEY", Fernet.generate_key().decode())
    archive = tmp_path / "application.fernet"
    assert admin.main(["backup", "--output", str(archive), "--backup-key-env", "invalid.name"]) == 1
    assert admin.main(["backup", "--output", str(archive)]) == 0
    assert admin.main(["restore", "--input", str(archive), "--destination-schema", "restored"]) == 0
    assert admin.main(["restore", "--input", str(archive), "--destination-schema", "restored"]) == 1
    assert "private-target" not in str(capsys.readouterr())
