"""Versioned SQL common to PostgreSQL production and SQLite local verification."""

SCHEMA_VERSION = 1
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS cv_workspace_provisioning (
        workspace_id TEXT PRIMARY KEY
    )""",
    """CREATE TABLE IF NOT EXISTS cv_actor_locks (
        workspace_id TEXT NOT NULL, user_id TEXT NOT NULL,
        PRIMARY KEY(workspace_id,user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS cv_workspace_members (
        workspace_id TEXT NOT NULL, user_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('owner','admin','editor','reviewer','viewer')),
        active INTEGER NOT NULL CHECK(active IN (0,1)),
        PRIMARY KEY(workspace_id,user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS cv_workflows (
        workspace_id TEXT NOT NULL, id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
        profile_slug TEXT NOT NULL, head_revision INTEGER NOT NULL CHECK(head_revision >= -1),
        active_run_id TEXT, current_review_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY(workspace_id,id)
    )""",
    """CREATE TABLE IF NOT EXISTS cv_model_runs (
        workspace_id TEXT NOT NULL, id TEXT NOT NULL, actor_user_id TEXT NOT NULL,
        workflow_id TEXT NOT NULL, operation TEXT NOT NULL CHECK(operation IN ('generate','revoice','review')),
        idempotency_key TEXT NOT NULL, request_sha256 TEXT NOT NULL,
        expected_revision INTEGER NOT NULL CHECK(expected_revision >= -1),
        state TEXT NOT NULL CHECK(state IN ('reserved','dispatched','completed','failed','indeterminate')),
        lease_token TEXT NOT NULL, lease_expires_at TEXT NOT NULL,
        result_revision INTEGER, error_code TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,actor_user_id,idempotency_key)
    )""",
    """CREATE TABLE IF NOT EXISTS cv_review_runs (
        workspace_id TEXT NOT NULL, id TEXT NOT NULL, workflow_id TEXT NOT NULL,
        candidate_sha256 TEXT NOT NULL, eligible INTEGER NOT NULL CHECK(eligible IN (0,1)),
        PRIMARY KEY(workspace_id,id),
        FOREIGN KEY(workspace_id,workflow_id) REFERENCES cv_workflows(workspace_id,id)
    )""",
    """CREATE TABLE IF NOT EXISTS cv_workflow_revisions (
        workspace_id TEXT NOT NULL, workflow_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision >= 0),
        actor_user_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('generation','revoice','edit','evaluation')),
        encrypted_payload TEXT NOT NULL CHECK(length(encrypted_payload) BETWEEN 1 AND 2000000),
        candidate_sha256 TEXT NOT NULL, review_run_id TEXT, review_eligible INTEGER NOT NULL CHECK(review_eligible IN (0,1)),
        model_run_id TEXT, created_at TEXT NOT NULL,
        PRIMARY KEY(workspace_id,workflow_id,revision),
        FOREIGN KEY(workspace_id,workflow_id) REFERENCES cv_workflows(workspace_id,id)
    )""",
    """CREATE TABLE IF NOT EXISTS cv_workflow_reviews (
        workspace_id TEXT NOT NULL, id TEXT NOT NULL, workflow_id TEXT NOT NULL, revision INTEGER NOT NULL,
        candidate_sha256 TEXT NOT NULL, review_run_id TEXT NOT NULL, reviewer_user_id TEXT NOT NULL,
        decision TEXT NOT NULL CHECK(decision IN ('approved','changes_requested')),
        note TEXT NOT NULL CHECK(length(note) <= 4000), created_at TEXT NOT NULL,
        PRIMARY KEY(workspace_id,id),
        FOREIGN KEY(workspace_id,workflow_id,revision)
            REFERENCES cv_workflow_revisions(workspace_id,workflow_id,revision)
    )""",
    "CREATE INDEX IF NOT EXISTS cv_workflows_recent ON cv_workflows(workspace_id,updated_at,id)",
    "CREATE INDEX IF NOT EXISTS cv_runs_actor_time ON cv_model_runs(workspace_id,actor_user_id,created_at)",
    "CREATE INDEX IF NOT EXISTS cv_runs_workflow ON cv_model_runs(workspace_id,workflow_id,created_at)",
    "CREATE INDEX IF NOT EXISTS cv_reviews_workflow ON cv_workflow_reviews(workspace_id,workflow_id,revision)",
)

IMMUTABLE_TABLES = ("cv_workflow_revisions", "cv_workflow_reviews", "cv_review_runs")


def sqlite_history_guards() -> tuple[str, ...]:
    return tuple(
        f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable_{action.lower()}
        BEFORE {action} ON {table} BEGIN
        SELECT RAISE(ABORT, 'workflow history is immutable'); END"""
        for table in IMMUTABLE_TABLES
        for action in ("UPDATE", "DELETE")
    )


def postgres_history_guards() -> tuple[str, ...]:
    return (
        """CREATE OR REPLACE FUNCTION cv_reject_history_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'workflow history is immutable'; END;
        $$ LANGUAGE plpgsql""",
        *(
            statement
            for table in IMMUTABLE_TABLES
            for statement in (
                f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}",
                f"""CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION cv_reject_history_mutation()""",
            )
        ),
    )
