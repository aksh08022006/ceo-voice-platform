# Durable workspace storage

`ceo_voice.workspace.WorkflowRepository` is the authority for workflow IDs, current revision,
run state, and human approvals. Its production adapter uses PostgreSQL; its SQLite adapter
is explicitly limited to local development/tests and refuses to initialize when `VERCEL` is
set. No production revision storage falls back to memory or `/tmp`.

## Integration contract

Construct `PostgresDatabase(database_url)` and `WorkflowRepository(database)`. Connections
use `verify-full` TLS with the pinned certifi CA bundle, bounded connection/statement/lock
timeouts, and no prepared-statement cache (compatible with the provider pooler). An explicit
`sslrootcert` override can select another trusted CA file. Plaintext connections require
`allow_insecure_local=True` and an explicit loopback host; host/service overrides are rejected.
Use the pooler URL for runtime and the unpooled administrator URL for migrations.

The synchronous repository opens short transactions; call it from an HTTP thread pool.
Never put model requests inside database transactions. Membership and profile-role policy
are checked by the API using verified server identity, rather than browser workspace/user
fields. Every repository operation scopes database access by workspace; run operations also
scope by actor. `get_member` returns `None` for an unknown member. Inactive rows are preserved.

`SnapshotWrite` accepts an already-encrypted, bounded URL-safe payload, candidate SHA-256,
automatic review UUID, and trusted review eligibility. It does not encrypt or validate the
contents itself. The server codec must encrypt and authenticate the snapshot and bind its
workspace ID, workflow ID, revision, candidate hash, and review ID to the corresponding row.
Never put raw bearer tokens, provider credentials, or raw prompts into diagnostic identifiers.

## Model calls and revisions

1. `reserve_run(scope, idempotency_key=..., operation=..., request_sha256=...,
   maximum_runs_per_hour=30, ...)` durably allocates or retrieves one run. A generation
   additionally takes `profile_slug` and allocates its stable workflow UUID immediately.
   Revoice/review take `workflow_id` and `expected_revision`; stale heads and busy workflows
   fail before contacting a model. Only an `acquired` reservation returns a fencing token.
2. Commit `mark_dispatched(scope, run_id, lease_token)` **before** the provider request.
3. `complete_run(..., snapshot)` atomically saves the immutable revision, moves the head,
   releases the run, and records its result revision. Generate/revoice/review produce
   `generation`/`revoice`/`evaluation` revisions respectively.
4. `get_run(scope, key, request_sha256=...)` returns the existing state. A completed run's
   `result_revision` selects the exact cached result through `get_revision`; a browser's old
   snapshot is never accepted as a new head.

The idempotency key is scoped by workspace and actor. Reusing it with different request,
operation, profile, workflow, or expected revision is rejected. Distinct new reservations
atomically count toward the preceding rolling hour's quota, including known failures and
expired claims; duplicates and lease reacquisition do not consume an additional slot.
Rejected quota, stale-head, or busy reservations roll back fully. Configure the same quota
on every paid API path. `WorkspaceQuotaExceeded` should map to HTTP 429.

Leases last 15–900 seconds and can be renewed with `heartbeat`. Only expired **undispatched**
reservations can be reacquired. A dispatched run whose lease expires becomes `indeterminate`
and continues to fence the workflow. It is never automatically replayed: a timeout cannot
establish whether the provider charged or completed. The original fenced worker can persist
a late result. Known pre-provider failures or explicitly confirmed provider failures can use
`fail_run(uncertain=False)`; unknown provider outcomes must use `uncertain=True`. An operator
must reconcile unresolved outcomes from provider evidence before intentionally releasing a
run. This design prevents automatic duplicate dispatch; it does not claim exactly-once
execution across an external model provider.

`append_revision` performs a current-head comparison and rejects writes while a model run
is pending. Every edit/evaluation creates a new revision. The old history remains readable
with `get_revision`, `list_revisions`, and `list_reviews`. List methods are bounded to 100
records per call. The editor exposes encrypted pagination cursors; history cursors bind to
the workflow's current head and must restart after a new revision. Archival remains future work.

## Approval and access

`record_review` requires the current revision, candidate hash, and stored automatic review
UUID to match, with no active model run. Approval also requires that revision's trusted
review eligibility. Automatic review UUIDs cannot be rebound to another candidate,
workflow, or eligibility. The authenticated reviewer identity is retained in immutable
history. Every new revision clears the current approval; previous review records remain.
The API must require a reviewer/admin/owner role before invoking this method.
Exports use `get_approved_revision` to verify and read the approved current snapshot in one
locked transaction, including the same candidate, review UUID, and eligibility checks.

`bootstrap_owner_if_empty(scope)` serializes first-owner provisioning. It returns an existing
same active owner idempotently, otherwise grants an owner only when no owner exists and
that user has no membership record. It never overwrites or reactivates revoked memberships.
The API must first match an explicitly configured verified bootstrap identity. Administrative
membership changes use `upsert_member`; this is a trusted provisioning boundary, not a public
self-service method.

## Explicit administration

Migrations never run as a side effect of an HTTP request. Load the administrator connection
into `DATABASE_URL_UNPOOLED` using the deployment secret manager, then run:

```bash
python -m ceo_voice.workspace.admin --database-env DATABASE_URL_UNPOOLED migrate
python -m ceo_voice.workspace.admin --database-env DATABASE_URL_UNPOOLED bootstrap-owner \
  --workspace-id narrative-company --user-id VERIFIED_PROVIDER_SUBJECT
```

The CLI accepts an environment variable **name**, avoiding credentials in shell history.
It checks the schema version, serializes PostgreSQL migrations, and prints safe diagnostics.
The equivalent initial SQL is in `migrations/001_workspace_postgres.sql`. A non-default
schema is supported through `--schema` and the adapter's `schema` argument.

On the newly provisioned isolated resource, the restricted runtime role is created explicitly
with `scripts/provision_workspace_database.py --expected-database neondb --output-env
.env.workspace.app.local`. It reads the configured administrator and pooler environment
variables, refuses an existing role/output file, and writes credentials with mode 0600.
The script removes PUBLIC schema-create and database-temp privileges on this new resource.
The app role has no DDL or DELETE grants. It can select workspace tables, insert new records,
and update only membership/workflow/model-run state. Revision and review UPDATE/DELETE are
also rejected by database triggers. Managed identity access is limited to six required user
columns; session/account tables receive no grants. The database owner remains a separate
migration credential and is never the HTTP runtime identity.

## Encrypted backup and restore

Load a separate Fernet key into `WORKSPACE_BACKUP_KEY` from the secret manager, alongside
the administrator connection. Keep this archive key separate from the snapshot encryption
key. The CLI reads environment variable names, never credentials supplied as arguments:

```bash
python -m ceo_voice.workspace.admin --database-env DATABASE_URL_UNPOOLED backup \
  --output /protected-backups/workspace-YYYYMMDD.fernet
python -m ceo_voice.workspace.admin --database-env DATABASE_URL_UNPOOLED restore \
  --input /protected-backups/workspace-YYYYMMDD.fernet \
  --destination-schema cv_restore_YYYYMMDD
```

Backups use a repeatable-read snapshot of fixed application tables and columns, authenticated
encryption, a data digest, and exclusive mode-0600 file creation. Managed authentication
tables are excluded. The archive is bounded to 50,000 rows, 64 MB of uncompressed data and
96 MB on disk; exceeding a bound fails explicitly. Operators must move completed archives
to durable storage outside the deployment and preserve the backup key independently.

Restore only accepts a distinct empty schema, refuses `public` and managed/system namespaces,
and installs the versioned schema and immutable-history guards before committing the data
atomically. It does not overwrite production or switch the application to the restored schema.
Validate the restored digest, decrypt representative revisions with the snapshot key, verify
membership mappings and profile bundles, and rehearse reads before a separately planned cutover.

The 7 September 2026 live PostgreSQL rehearsal backed up the newly migrated **empty** workspace
(one schema-version row), restored it into an isolated temporary schema, matched the digest,
then removed that rehearsal schema. Populated revisions, approvals and idempotency records
were exercised by local round-trip tests. A populated live recovery rehearsal remains due
after real editorial data exists. These application archives do not replace managed auth
recovery: provider identity records, immutable profile bundles, the continuation key and the
snapshot encryption key require their own recovery arrangements. Automated backup scheduling,
off-site retention and an agreed recovery-time objective are not yet configured.

## Verification and operational limits

The repository contract suite covers independent connections, concurrent same-key claims,
distinct-key quota races, stale edit/revoice rejection, unknown provider outcomes, immutable
SQL history, candidate-bound approvals, workspace isolation, and bootstrap races. To opt
into PostgreSQL tests, provide `CEO_VOICE_TEST_POSTGRES_URL` and an existing dedicated schema
named `cv_test_*` via `CEO_VOICE_TEST_POSTGRES_SCHEMA`. Never target the production `public`
schema with test fixtures. Optional `CEO_VOICE_TEST_POSTGRES_CA` overrides trusted roots;
local unencrypted test servers additionally require `CEO_VOICE_TEST_POSTGRES_INSECURE=1`.

Snapshots and history are durable until explicitly archived under a future retention policy.
The 2 MB encrypted-payload bound caps each write; it is not a total account-storage quota.
Protect and back up the snapshot encryption key independently: losing it makes saved
snapshots unreadable. No runtime method deletes records or cleans user data.
