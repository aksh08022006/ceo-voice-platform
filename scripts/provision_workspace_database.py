"""Provision a restricted runtime role on the explicitly configured NEW workspace database.

Run only after the workspace migration. This command refuses an existing role/output file;
it never rotates credentials, provisions a database, or prints a connection string.
"""

import argparse
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import certifi
import psycopg
from psycopg import sql

READ_TABLES = (
    "cv_schema_migrations",
    "cv_workspace_provisioning",
    "cv_actor_locks",
    "cv_workspace_members",
    "cv_workflows",
    "cv_model_runs",
    "cv_review_runs",
    "cv_workflow_revisions",
    "cv_workflow_reviews",
)
INSERT_TABLES = tuple(table for table in READ_TABLES if table != "cv_schema_migrations")
UPDATE_TABLES = ("cv_workspace_members", "cv_workflows", "cv_model_runs")
ROLE = "ceo_voice_app"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-env", default="DATABASE_URL_UNPOOLED")
    parser.add_argument("--pooler-env", default="DATABASE_URL")
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--output-env", type=Path, required=True)
    args = parser.parse_args()
    admin_dsn, pooled_dsn = os.environ.get(args.admin_env), os.environ.get(args.pooler_env)
    if not admin_dsn or not pooled_dsn:
        print("Configured database environment variables are required.", file=sys.stderr)
        return 1
    admin, pooled = urlsplit(admin_dsn), urlsplit(pooled_dsn)
    if admin.path != pooled.path or admin.path != f"/{args.expected_database}":
        print("Configured database name does not match the explicit target.", file=sys.stderr)
        return 1
    # Neon pooled/unpooled URLs must identify the same endpoint before generating credentials.
    if (pooled.hostname or "").replace("-pooler.", ".") != admin.hostname:
        print("Pooler and administrator endpoints do not match.", file=sys.stderr)
        return 1
    output_created = False
    try:
        descriptor = os.open(args.output_env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        output_created = True
        with (
            os.fdopen(descriptor, "w") as output,
            psycopg.connect(
                admin_dsn, sslmode="verify-full", sslrootcert=certifi.where(), connect_timeout=10
            ) as conn,
        ):
            if conn.execute("SELECT current_database()").fetchone()[0] != args.expected_database:
                raise ValueError("unexpected database")
            if conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,)).fetchone():
                raise ValueError("runtime role already exists")
            if conn.execute("SELECT version FROM public.cv_schema_migrations").fetchall() != [(1,)]:
                raise ValueError("workspace schema must be migrated first")
            password = secrets.token_urlsafe(48)
            role = sql.Identifier(ROLE)
            conn.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
                ).format(role, sql.Literal(password))
            )
            # This is an isolated new database. Remove PUBLIC's default temp/schema-create
            # privileges so the restricted role cannot obtain DDL through PUBLIC membership.
            conn.execute(
                sql.SQL("REVOKE CREATE, TEMPORARY ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(args.expected_database)
                )
            )
            conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            conn.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(args.expected_database), role
                )
            )
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public, neon_auth TO {}").format(role))
            conn.execute(
                sql.SQL(
                    'GRANT SELECT (id, name, email, "emailVerified", banned, "banExpires") ON neon_auth."user" TO {}'
                ).format(role)
            )
            for privilege, tables in (
                ("SELECT", READ_TABLES),
                ("INSERT", INSERT_TABLES),
                ("UPDATE", UPDATE_TABLES),
            ):
                for table in tables:
                    conn.execute(
                        sql.SQL("GRANT {} ON TABLE public.{} TO {}").format(
                            sql.SQL(privilege), sql.Identifier(table), role
                        )
                    )
            netloc = f"{ROLE}:{quote(password, safe='')}@{pooled.hostname}"
            if pooled.port:
                netloc += f":{pooled.port}"
            query = [
                (key, value)
                for key, value in parse_qsl(pooled.query)
                if key in {"channel_binding", "application_name"}
            ]
            query.append(("sslmode", "verify-full"))
            app_dsn = urlunsplit((pooled.scheme, netloc, pooled.path, urlencode(query), ""))
            output.write(f"DATABASE_URL={app_dsn}\n")
            output.flush()
            os.fsync(output.fileno())
        print(
            "Restricted runtime role provisioned; credentials saved in the requested private file."
        )
        return 0
    except (OSError, ValueError, psycopg.Error):
        if output_created:
            args.output_env.unlink(missing_ok=True)
        print(
            "Runtime role provisioning failed or target already exists; no credentials were printed.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
