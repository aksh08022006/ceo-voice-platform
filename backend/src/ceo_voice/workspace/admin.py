"""Explicit administrator commands. Connection secrets are read only from environment."""

import argparse
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from ceo_voice.core.exceptions import ApplicationError, ConfigurationError
from ceo_voice.workspace import PostgresDatabase, WorkflowRepository, WorkspaceScope
from ceo_voice.workspace.backup import create_backup, restore_backup


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate or bootstrap the configured workspace database"
    )
    parser.add_argument("--database-env", default="DATABASE_URL_UNPOOLED")
    parser.add_argument("--schema", default="public")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="Apply the explicit versioned SQL schema")
    bootstrap = commands.add_parser(
        "bootstrap-owner", help="Provision the first owner without overwriting memberships"
    )
    bootstrap.add_argument("--workspace-id", required=True)
    bootstrap.add_argument("--user-id", required=True)
    backup = commands.add_parser(
        "backup", help="Write an encrypted allowlisted application-data archive"
    )
    backup.add_argument("--output", type=Path, required=True)
    backup.add_argument("--backup-key-env", default="WORKSPACE_BACKUP_KEY")
    restore = commands.add_parser(
        "restore", help="Restore into a distinct empty schema; never overwrites live tables"
    )
    restore.add_argument("--input", type=Path, required=True)
    restore.add_argument("--destination-schema", required=True)
    restore.add_argument("--backup-key-env", default="WORKSPACE_BACKUP_KEY")
    args = parser.parse_args(argv)
    try:
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", args.database_env) is None:
            raise ConfigurationError("database environment variable name is invalid")
        dsn = os.environ.get(args.database_env)
        if not dsn:
            raise ConfigurationError("configured database environment variable is empty")
        schema = args.destination_schema if args.command == "restore" else args.schema
        database = PostgresDatabase(dsn, schema=schema)
        if args.command in {"backup", "restore"}:
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", args.backup_key_env) is None:
                raise ConfigurationError("backup key environment variable name is invalid")
            key = os.environ.get(args.backup_key_env, "")
            result = (
                create_backup(database, args.output, key)
                if args.command == "backup"
                else restore_backup(database, args.input, key)
            )
            print(
                f"Workspace {args.command} completed: rows={result.rows}, data_sha256={result.data_sha256}"
            )
        elif args.command == "migrate":
            database.migrate()
            print("Workspace schema migration completed.")
        else:
            member = WorkflowRepository(database).bootstrap_owner_if_empty(
                WorkspaceScope(workspace_id=args.workspace_id, user_id=args.user_id)
            )
            if member is None:
                print(
                    "Owner bootstrap refused: an owner or this membership already exists.",
                    file=sys.stderr,
                )
                return 1
            print("Workspace owner is provisioned.")
        return 0
    except ApplicationError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1
    except (ValueError, OSError):
        print(
            "configuration_error: administrator arguments or file operation are invalid",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
