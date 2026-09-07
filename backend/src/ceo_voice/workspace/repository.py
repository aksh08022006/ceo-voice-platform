"""Authoritative revision heads, fenced model work, immutable history, and approval records."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from ceo_voice.workspace.contracts import (
    ModelRun,
    ReviewDecision,
    ReviewRecord,
    RevisionKind,
    RevisionRecord,
    RunOperation,
    RunReservation,
    SnapshotWrite,
    WorkflowRecord,
    WorkspaceMember,
    WorkspaceScope,
)
from ceo_voice.workspace.database import Row, SQLDatabase, Transaction
from ceo_voice.workspace.errors import (
    ApprovalConflict,
    IdempotencyConflict,
    LeaseConflict,
    RevisionConflict,
    WorkflowBusy,
    WorkspaceNotFound,
    WorkspaceQuotaExceeded,
)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("repository timestamps must include a timezone")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


class WorkflowRepository:
    """All writes are short atomic transactions. Never hold a transaction during model calls."""

    def __init__(
        self, database: SQLDatabase, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self.database = database
        self.clock = clock or (lambda: datetime.now(UTC))

    def reserve_run(
        self,
        scope: WorkspaceScope,
        *,
        idempotency_key: str,
        operation: RunOperation,
        request_sha256: str,
        profile_slug: str | None = None,
        workflow_id: UUID | None = None,
        expected_revision: int | None = None,
        lease_seconds: int = 300,
        maximum_runs_per_hour: int | None = None,
    ) -> RunReservation:
        """Claim one model run; only an acquired claim may proceed to mark_dispatched.

        Reusing an expired, undispatched claim is safe. Dispatched work is never automatically
        repeated after expiry: provider billing/completion may be unknown.
        """

        if not 15 <= lease_seconds <= 900:
            raise ValueError("model lease must be between 15 and 900 seconds")
        if maximum_runs_per_hour is not None and not 1 <= maximum_runs_per_hour <= 10000:
            raise ValueError("hourly model run limit must be between 1 and 10000")
        if operation == "generate":
            if not profile_slug or workflow_id is not None or expected_revision is not None:
                raise ValueError("generation requires profile_slug and allocates its workflow ID")
            target_id, expected = uuid4(), -1
        elif workflow_id is None or expected_revision is None or expected_revision < 0:
            raise ValueError(
                "revoice/review requires workflow_id and a nonnegative expected revision"
            )
        else:
            target_id, expected = workflow_id, expected_revision
        now = self.clock()
        stamp, expires = _timestamp(now), _timestamp(now + timedelta(seconds=lease_seconds))
        identifier, token = uuid4(), uuid4()
        # Validate user-facing boundaries before opening the transaction.
        proposed = ModelRun(
            id=identifier,
            workspace_id=scope.workspace_id,
            actor_user_id=scope.user_id,
            workflow_id=target_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request_sha256=request_sha256,
            expected_revision=expected,
            state="reserved",
            lease_expires_at=expires,
            created_at=stamp,
            updated_at=stamp,
        )
        with self.database.transaction() as tx:
            inserted = tx.execute(
                """INSERT INTO cv_model_runs(workspace_id,id,actor_user_id,workflow_id,operation,
                idempotency_key,request_sha256,expected_revision,state,lease_token,lease_expires_at,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,'reserved',?,?,?,?)
                ON CONFLICT(workspace_id,actor_user_id,idempotency_key) DO NOTHING""",
                (
                    scope.workspace_id,
                    str(identifier),
                    scope.user_id,
                    str(target_id),
                    operation,
                    idempotency_key,
                    request_sha256,
                    expected,
                    str(token),
                    expires,
                    stamp,
                    stamp,
                ),
            )
            if not inserted:
                row = self._run_for_key(tx, scope, idempotency_key, lock=True)
                if (
                    row["request_sha256"] != request_sha256
                    or row["operation"] != operation
                    or row["expected_revision"] != expected
                    or (workflow_id is not None and row["workflow_id"] != str(workflow_id))
                ):
                    raise IdempotencyConflict(
                        "idempotency key was already used for another request"
                    )
                if (
                    operation == "generate"
                    and self._workflow(tx, scope.workspace_id, UUID(row["workflow_id"]), lock=True)[
                        "profile_slug"
                    ]
                    != profile_slug
                ):
                    raise IdempotencyConflict(
                        "idempotency key was already used for another profile"
                    )
                row = self._expire_dispatched(tx, row, stamp)
                if row["state"] == "reserved" and row["lease_expires_at"] <= stamp:
                    tx.execute(
                        "UPDATE cv_model_runs SET lease_token=?,lease_expires_at=?,updated_at=? WHERE workspace_id=? AND id=?",
                        (str(token), expires, stamp, scope.workspace_id, row["id"]),
                    )
                    row.update(lease_token=str(token), lease_expires_at=expires, updated_at=stamp)
                    return RunReservation(
                        disposition="acquired", run=self._run(row), lease_token=token
                    )
                return RunReservation(disposition="existing", run=self._run(row))
            if maximum_runs_per_hour is not None:
                self._enforce_quota(tx, scope, now, maximum_runs_per_hour)
            if operation == "generate":
                assert profile_slug is not None
                # The placeholder is durable before dispatch, including stable ownership/ID.
                WorkflowRecord(
                    id=target_id,
                    workspace_id=scope.workspace_id,
                    owner_user_id=scope.user_id,
                    profile_slug=profile_slug,
                    head_revision=-1,
                    active_run_id=identifier,
                    candidate_sha256=None,
                    review_status="unreviewed",
                    created_at=stamp,
                    updated_at=stamp,
                )
                tx.execute(
                    """INSERT INTO cv_workflows(workspace_id,id,owner_user_id,profile_slug,head_revision,
                    active_run_id,created_at,updated_at) VALUES (?,?,?,?,-1,?,?,?)""",
                    (
                        scope.workspace_id,
                        str(target_id),
                        scope.user_id,
                        profile_slug,
                        str(identifier),
                        stamp,
                        stamp,
                    ),
                )
            else:
                workflow = self._workflow(tx, scope.workspace_id, target_id, lock=True)
                self._check_head(workflow, expected)
                self._check_idle(workflow)
                tx.execute(
                    "UPDATE cv_workflows SET active_run_id=?,updated_at=? WHERE workspace_id=? AND id=?",
                    (str(identifier), stamp, scope.workspace_id, str(target_id)),
                )
            return RunReservation(disposition="acquired", run=proposed, lease_token=token)

    def get_run(
        self, scope: WorkspaceScope, idempotency_key: str, *, request_sha256: str | None = None
    ) -> ModelRun:
        with self.database.transaction() as tx:
            row = self._run_for_key(tx, scope, idempotency_key, lock=True)
            if request_sha256 is not None and row["request_sha256"] != request_sha256:
                raise IdempotencyConflict("idempotency key was already used for another request")
            return self._run(self._expire_dispatched(tx, row, _timestamp(self.clock())))

    def mark_dispatched(self, scope: WorkspaceScope, run_id: UUID, lease_token: UUID) -> ModelRun:
        """Commit this transition before contacting the external model provider."""
        stamp = _timestamp(self.clock())
        with self.database.transaction() as tx:
            row = self._owned_run(tx, scope, run_id)
            self._check_token(row, lease_token)
            if row["state"] != "reserved" or row["lease_expires_at"] <= stamp:
                raise LeaseConflict("model run cannot be dispatched from this lease or state")
            tx.execute(
                "UPDATE cv_model_runs SET state='dispatched',updated_at=? WHERE workspace_id=? AND id=?",
                (stamp, scope.workspace_id, str(run_id)),
            )
            row.update(state="dispatched", updated_at=stamp)
            return self._run(row)

    def heartbeat(
        self, scope: WorkspaceScope, run_id: UUID, lease_token: UUID, *, lease_seconds: int = 300
    ) -> ModelRun:
        if not 15 <= lease_seconds <= 900:
            raise ValueError("model lease must be between 15 and 900 seconds")
        now = self.clock()
        stamp, expires = _timestamp(now), _timestamp(now + timedelta(seconds=lease_seconds))
        with self.database.transaction() as tx:
            row = self._owned_run(tx, scope, run_id)
            self._check_token(row, lease_token)
            if row["state"] not in {"reserved", "dispatched"} or row["lease_expires_at"] <= stamp:
                raise LeaseConflict("model run lease is no longer active")
            tx.execute(
                "UPDATE cv_model_runs SET lease_expires_at=?,updated_at=? WHERE workspace_id=? AND id=?",
                (expires, stamp, scope.workspace_id, str(run_id)),
            )
            row.update(lease_expires_at=expires, updated_at=stamp)
            return self._run(row)

    def complete_run(
        self, scope: WorkspaceScope, run_id: UUID, lease_token: UUID, snapshot: SnapshotWrite
    ) -> RevisionRecord:
        stamp = _timestamp(self.clock())
        with self.database.transaction() as tx:
            run = self._owned_run(tx, scope, run_id)
            self._check_token(run, lease_token)
            workflow_id = UUID(run["workflow_id"])
            if run["state"] == "completed":
                existing = self._revision(
                    tx, scope.workspace_id, workflow_id, run["result_revision"]
                )
                if existing.candidate_sha256 != snapshot.candidate_sha256:
                    raise IdempotencyConflict("completed model run has a different candidate")
                return existing
            # The original fenced worker may still reconcile a late provider response. No other
            # worker can reacquire a dispatched/indeterminate run or dispatch a duplicate charge.
            if run["state"] not in {"dispatched", "indeterminate"}:
                raise LeaseConflict("only a dispatched model run can be completed")
            workflow = self._workflow(tx, scope.workspace_id, workflow_id, lock=True)
            self._check_head(workflow, run["expected_revision"])
            if workflow["active_run_id"] != str(run_id):
                raise LeaseConflict("workflow is no longer held by this model run")
            kind: RevisionKind = (
                "generation"
                if run["operation"] == "generate"
                else "evaluation" if run["operation"] == "review" else "revoice"
            )
            revision = self._append(
                tx,
                scope,
                workflow,
                snapshot,
                kind,
                stamp,
                run_id,
            )
            changed = tx.execute(
                """UPDATE cv_workflows SET head_revision=?,active_run_id=NULL,current_review_id=NULL,updated_at=?
                WHERE workspace_id=? AND id=? AND head_revision=? AND active_run_id=?""",
                (
                    revision.revision,
                    stamp,
                    scope.workspace_id,
                    str(workflow_id),
                    run["expected_revision"],
                    str(run_id),
                ),
            )
            if changed != 1:
                raise RevisionConflict("workflow changed before model completion")
            tx.execute(
                "UPDATE cv_model_runs SET state='completed',result_revision=?,updated_at=? WHERE workspace_id=? AND id=?",
                (revision.revision, stamp, scope.workspace_id, str(run_id)),
            )
            return revision

    def fail_run(
        self,
        scope: WorkspaceScope,
        run_id: UUID,
        lease_token: UUID,
        *,
        error_code: str,
        uncertain: bool = False,
    ) -> ModelRun:
        """Known failures release the workflow; uncertain provider outcomes remain fenced."""
        if (
            not error_code
            or len(error_code) > 160
            or not all(c.isalnum() or c in "_-" for c in error_code)
        ):
            raise ValueError("error_code must be a bounded diagnostic identifier without content")
        stamp = _timestamp(self.clock())
        with self.database.transaction() as tx:
            row = self._owned_run(tx, scope, run_id)
            self._check_token(row, lease_token)
            if row["state"] == "completed":
                raise LeaseConflict("completed model run cannot fail")
            state = "indeterminate" if uncertain else "failed"
            if row["state"] == "failed":
                if uncertain:
                    raise LeaseConflict("failed model run cannot be dispatched or made uncertain")
                return self._run(row)
            tx.execute(
                "UPDATE cv_model_runs SET state=?,error_code=?,updated_at=? WHERE workspace_id=? AND id=?",
                (state, error_code, stamp, scope.workspace_id, str(run_id)),
            )
            if not uncertain:
                tx.execute(
                    "UPDATE cv_workflows SET active_run_id=NULL,updated_at=? WHERE workspace_id=? AND id=? AND active_run_id=?",
                    (stamp, scope.workspace_id, row["workflow_id"], str(run_id)),
                )
            row.update(state=state, error_code=error_code, updated_at=stamp)
            return self._run(row)

    def append_revision(
        self,
        scope: WorkspaceScope,
        workflow_id: UUID,
        *,
        expected_revision: int,
        snapshot: SnapshotWrite,
        kind: RevisionKind = "edit",
    ) -> RevisionRecord:
        if kind not in {"edit", "evaluation"}:
            raise ValueError("model revisions must complete a reserved model run")
        stamp = _timestamp(self.clock())
        with self.database.transaction() as tx:
            row = self._workflow(tx, scope.workspace_id, workflow_id, lock=True)
            self._check_head(row, expected_revision)
            self._check_idle(row)
            if expected_revision < 0:
                raise RevisionConflict("workflow has no generated revision")
            revision = self._append(tx, scope, row, snapshot, kind, stamp, None)
            tx.execute(
                "UPDATE cv_workflows SET head_revision=?,current_review_id=NULL,updated_at=? WHERE workspace_id=? AND id=?",
                (revision.revision, stamp, scope.workspace_id, str(workflow_id)),
            )
            return revision

    def record_review(
        self,
        scope: WorkspaceScope,
        workflow_id: UUID,
        *,
        expected_revision: int,
        candidate_sha256: str,
        review_run_id: UUID,
        decision: ReviewDecision,
        note: str = "",
    ) -> ReviewRecord:
        record = ReviewRecord(
            id=uuid4(),
            workspace_id=scope.workspace_id,
            workflow_id=workflow_id,
            revision=expected_revision,
            candidate_sha256=candidate_sha256,
            review_run_id=review_run_id,
            reviewer_user_id=scope.user_id,
            decision=decision,
            note=note,
            created_at=self.clock(),
        )
        with self.database.transaction() as tx:
            row = self._workflow(tx, scope.workspace_id, workflow_id, lock=True)
            self._check_head(row, expected_revision)
            self._check_idle(row)
            revision = self._revision(tx, scope.workspace_id, workflow_id, expected_revision)
            if (
                revision.candidate_sha256 != candidate_sha256
                or revision.review_run_id != review_run_id
            ):
                raise ApprovalConflict(
                    "review is not bound to the current candidate and review run"
                )
            if decision == "approved" and not revision.review_eligible:
                raise ApprovalConflict("current candidate has not passed the required review")
            tx.execute(
                """INSERT INTO cv_workflow_reviews(workspace_id,id,workflow_id,revision,candidate_sha256,
                review_run_id,reviewer_user_id,decision,note,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    scope.workspace_id,
                    str(record.id),
                    str(workflow_id),
                    expected_revision,
                    candidate_sha256,
                    str(review_run_id),
                    scope.user_id,
                    decision,
                    note,
                    _timestamp(record.created_at),
                ),
            )
            tx.execute(
                "UPDATE cv_workflows SET current_review_id=?,updated_at=? WHERE workspace_id=? AND id=?",
                (
                    str(record.id),
                    _timestamp(record.created_at),
                    scope.workspace_id,
                    str(workflow_id),
                ),
            )
            return record

    def get_approved_revision(
        self, workspace_id: str, workflow_id: UUID
    ) -> tuple[RevisionRecord, ReviewRecord]:
        """Return one atomically verified approved snapshot for export."""
        with self.database.transaction() as tx:
            workflow = self._workflow(tx, workspace_id, workflow_id, lock=True)
            if workflow["active_run_id"] is not None or workflow["current_review_id"] is None:
                raise ApprovalConflict("workflow has no current exportable approval")
            revision = self._revision(tx, workspace_id, workflow_id, workflow["head_revision"])
            row = tx.one(
                "SELECT * FROM cv_workflow_reviews WHERE workspace_id=? AND id=?",
                (workspace_id, workflow["current_review_id"]),
            )
            if row is None:
                raise ApprovalConflict("workflow has no current exportable approval")
            review = ReviewRecord.model_validate(row)
            if (
                review.workflow_id != workflow_id
                or review.revision != revision.revision
                or review.candidate_sha256 != revision.candidate_sha256
                or review.review_run_id != revision.review_run_id
                or review.decision != "approved"
                or not revision.review_eligible
            ):
                raise ApprovalConflict("approval is not bound to the current eligible candidate")
            return revision, review

    def get_workflow(self, workspace_id: str, workflow_id: UUID) -> WorkflowRecord:
        with self.database.transaction() as tx:
            return self._project_workflow(tx, self._workflow(tx, workspace_id, workflow_id))

    def get_revision(
        self, workspace_id: str, workflow_id: UUID, revision: int | None = None
    ) -> RevisionRecord:
        with self.database.transaction() as tx:
            workflow = self._workflow(tx, workspace_id, workflow_id)
            number = workflow["head_revision"] if revision is None else revision
            return self._revision(tx, workspace_id, workflow_id, number)

    def list_workflows(
        self, workspace_id: str, *, limit: int = 50, offset: int = 0
    ) -> tuple[WorkflowRecord, ...]:
        self._page(limit, offset)
        with self.database.transaction() as tx:
            return tuple(
                self._project_workflow(tx, row)
                for row in tx.all(
                    "SELECT * FROM cv_workflows WHERE workspace_id=? ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?",
                    (workspace_id, limit, offset),
                )
            )

    def list_revisions(
        self, workspace_id: str, workflow_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> tuple[RevisionRecord, ...]:
        self._page(limit, offset)
        with self.database.transaction() as tx:
            self._workflow(tx, workspace_id, workflow_id)
            return tuple(
                RevisionRecord.model_validate(row)
                for row in tx.all(
                    "SELECT * FROM cv_workflow_revisions WHERE workspace_id=? AND workflow_id=? ORDER BY revision DESC LIMIT ? OFFSET ?",
                    (workspace_id, str(workflow_id), limit, offset),
                )
            )

    def list_reviews(
        self, workspace_id: str, workflow_id: UUID, *, limit: int = 100
    ) -> tuple[ReviewRecord, ...]:
        self._limit(limit)
        with self.database.transaction() as tx:
            self._workflow(tx, workspace_id, workflow_id)
            return tuple(
                ReviewRecord.model_validate(row)
                for row in tx.all(
                    "SELECT * FROM cv_workflow_reviews WHERE workspace_id=? AND workflow_id=? ORDER BY created_at DESC,id DESC LIMIT ?",
                    (workspace_id, str(workflow_id), limit),
                )
            )

    def bootstrap_owner_if_empty(self, scope: WorkspaceScope) -> WorkspaceMember | None:
        """Trusted bootstrap only: one owner, no overwrite or reactivation of existing users."""
        with self.database.transaction() as tx:
            tx.execute(
                "INSERT INTO cv_workspace_provisioning(workspace_id) VALUES (?) ON CONFLICT(workspace_id) DO NOTHING",
                (scope.workspace_id,),
            )
            tx.one(
                "SELECT * FROM cv_workspace_provisioning WHERE workspace_id=?",
                (scope.workspace_id,),
                lock=True,
            )
            existing = tx.one(
                "SELECT * FROM cv_workspace_members WHERE workspace_id=? AND user_id=?",
                (scope.workspace_id, scope.user_id),
            )
            if existing is not None:
                member = WorkspaceMember.model_validate(existing)
                return member if member.active and member.role == "owner" else None
            if (
                tx.one(
                    "SELECT user_id FROM cv_workspace_members WHERE workspace_id=? AND role='owner' LIMIT 1",
                    (scope.workspace_id,),
                )
                is not None
            ):
                return None
            member = WorkspaceMember(**scope.model_dump(), role="owner")
            tx.execute(
                "INSERT INTO cv_workspace_members(workspace_id,user_id,role,active) VALUES (?,?,'owner',1)",
                (scope.workspace_id, scope.user_id),
            )
            return member

    def upsert_member(self, member: WorkspaceMember) -> WorkspaceMember:
        """Trusted provisioning boundary; the caller must authenticate an administrator."""
        with self.database.transaction() as tx:
            tx.execute(
                """INSERT INTO cv_workspace_members(workspace_id,user_id,role,active) VALUES (?,?,?,?)
                ON CONFLICT(workspace_id,user_id) DO UPDATE SET role=excluded.role,active=excluded.active""",
                (member.workspace_id, member.user_id, member.role, int(member.active)),
            )
        return member

    def get_member(self, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        with self.database.transaction() as tx:
            row = tx.one(
                "SELECT * FROM cv_workspace_members WHERE workspace_id=? AND user_id=?",
                (workspace_id, user_id),
            )
            return WorkspaceMember.model_validate(row) if row is not None else None

    def list_members(self, workspace_id: str, *, limit: int = 100) -> tuple[WorkspaceMember, ...]:
        self._limit(limit)
        with self.database.transaction() as tx:
            return tuple(
                WorkspaceMember.model_validate(row)
                for row in tx.all(
                    "SELECT * FROM cv_workspace_members WHERE workspace_id=? ORDER BY user_id LIMIT ?",
                    (workspace_id, limit),
                )
            )

    @staticmethod
    def _enforce_quota(tx: Transaction, scope: WorkspaceScope, now: datetime, maximum: int) -> None:
        # Distinct idempotency keys must serialize their rolling-hour count on the same actor.
        # The new run is already inserted in this transaction; a rejection rolls it all back.
        tx.execute(
            "INSERT INTO cv_actor_locks(workspace_id,user_id) VALUES (?,?) ON CONFLICT(workspace_id,user_id) DO NOTHING",
            (scope.workspace_id, scope.user_id),
        )
        tx.one(
            "SELECT * FROM cv_actor_locks WHERE workspace_id=? AND user_id=?",
            (scope.workspace_id, scope.user_id),
            lock=True,
        )
        row = tx.one(
            "SELECT COUNT(*) AS total FROM cv_model_runs WHERE workspace_id=? AND actor_user_id=? AND created_at>?",
            (scope.workspace_id, scope.user_id, _timestamp(now - timedelta(hours=1))),
        )
        assert row is not None
        if row["total"] > maximum:
            raise WorkspaceQuotaExceeded(
                "hourly model run limit reached",
                retryable=True,
                details={"maximum_runs_per_hour": maximum},
            )

    @staticmethod
    def _page(limit: int, offset: int) -> None:
        if not 1 <= limit <= 101 or not 0 <= offset <= 1_000_000:
            raise ValueError("page limit must be 1..101 and offset 0..1000000")

    @staticmethod
    def _limit(limit: int) -> None:
        if not 1 <= limit <= 100:
            raise ValueError("page limit must be between 1 and 100")

    @staticmethod
    def _workflow(
        tx: Transaction, workspace_id: str, workflow_id: UUID, *, lock: bool = False
    ) -> Row:
        row = tx.one(
            "SELECT * FROM cv_workflows WHERE workspace_id=? AND id=?",
            (workspace_id, str(workflow_id)),
            lock=lock,
        )
        if row is None:
            raise WorkspaceNotFound("workflow not found")
        return row

    @staticmethod
    def _run_for_key(
        tx: Transaction, scope: WorkspaceScope, key: str, *, lock: bool = False
    ) -> Row:
        row = tx.one(
            "SELECT * FROM cv_model_runs WHERE workspace_id=? AND actor_user_id=? AND idempotency_key=?",
            (scope.workspace_id, scope.user_id, key),
            lock=lock,
        )
        if row is None:
            raise WorkspaceNotFound("model run not found")
        return row

    @staticmethod
    def _owned_run(tx: Transaction, scope: WorkspaceScope, run_id: UUID) -> Row:
        row = tx.one(
            "SELECT * FROM cv_model_runs WHERE workspace_id=? AND actor_user_id=? AND id=?",
            (scope.workspace_id, scope.user_id, str(run_id)),
            lock=True,
        )
        if row is None:
            raise WorkspaceNotFound("model run not found")
        return row

    @staticmethod
    def _run(row: Row) -> ModelRun:
        return ModelRun.model_validate(
            {key: value for key, value in row.items() if key != "lease_token"}
        )

    @staticmethod
    def _check_token(row: Row, token: UUID) -> None:
        if row["lease_token"] != str(token):
            raise LeaseConflict("model run is held by another lease")

    @staticmethod
    def _check_head(row: Row, expected: int) -> None:
        if row["head_revision"] != expected:
            raise RevisionConflict(
                "workflow has a newer revision", details={"current_revision": row["head_revision"]}
            )

    @staticmethod
    def _check_idle(row: Row) -> None:
        if row["active_run_id"] is not None:
            raise WorkflowBusy("workflow has an active or unresolved model run", retryable=True)

    @staticmethod
    def _expire_dispatched(tx: Transaction, row: Row, stamp: str) -> Row:
        if row["state"] == "dispatched" and row["lease_expires_at"] <= stamp:
            tx.execute(
                "UPDATE cv_model_runs SET state='indeterminate',error_code='lease_expired_after_dispatch',updated_at=? WHERE workspace_id=? AND id=?",
                (stamp, row["workspace_id"], row["id"]),
            )
            row.update(
                state="indeterminate", error_code="lease_expired_after_dispatch", updated_at=stamp
            )
        return row

    @staticmethod
    def _revision(
        tx: Transaction, workspace_id: str, workflow_id: UUID, revision: int
    ) -> RevisionRecord:
        row = tx.one(
            "SELECT * FROM cv_workflow_revisions WHERE workspace_id=? AND workflow_id=? AND revision=?",
            (workspace_id, str(workflow_id), revision),
        )
        if row is None:
            raise WorkspaceNotFound("workflow revision not found")
        return RevisionRecord.model_validate(row)

    @staticmethod
    def _project_workflow(tx: Transaction, row: Row) -> WorkflowRecord:
        projected = {key: value for key, value in row.items() if key != "current_review_id"}
        revision = tx.one(
            "SELECT candidate_sha256 FROM cv_workflow_revisions WHERE workspace_id=? AND workflow_id=? AND revision=?",
            (row["workspace_id"], row["id"], row["head_revision"]),
        )
        review = (
            tx.one(
                "SELECT decision FROM cv_workflow_reviews WHERE workspace_id=? AND id=?",
                (row["workspace_id"], row["current_review_id"]),
            )
            if row["current_review_id"]
            else None
        )
        projected.update(
            candidate_sha256=revision["candidate_sha256"] if revision else None,
            review_status=review["decision"] if review else "unreviewed",
        )
        return WorkflowRecord.model_validate(projected)

    @staticmethod
    def _append(
        tx: Transaction,
        scope: WorkspaceScope,
        workflow: Row,
        snapshot: SnapshotWrite,
        kind: RevisionKind,
        stamp: str,
        model_run_id: UUID | None,
    ) -> RevisionRecord:
        workflow_id = UUID(workflow["id"])
        if snapshot.review_run_id is not None:
            tx.execute(
                """INSERT INTO cv_review_runs(workspace_id,id,workflow_id,candidate_sha256,eligible)
                VALUES (?,?,?,?,?) ON CONFLICT(workspace_id,id) DO NOTHING""",
                (
                    scope.workspace_id,
                    str(snapshot.review_run_id),
                    str(workflow_id),
                    snapshot.candidate_sha256,
                    int(snapshot.review_eligible),
                ),
            )
            binding = tx.one(
                "SELECT * FROM cv_review_runs WHERE workspace_id=? AND id=?",
                (scope.workspace_id, str(snapshot.review_run_id)),
            )
            assert binding is not None
            if (binding["workflow_id"], binding["candidate_sha256"], bool(binding["eligible"])) != (
                str(workflow_id),
                snapshot.candidate_sha256,
                snapshot.review_eligible,
            ):
                raise ApprovalConflict(
                    "review run was already bound to another candidate or workflow"
                )
        revision = RevisionRecord(
            **snapshot.model_dump(),
            workflow_id=workflow_id,
            workspace_id=scope.workspace_id,
            revision=workflow["head_revision"] + 1,
            actor_user_id=scope.user_id,
            kind=kind,
            model_run_id=model_run_id,
            created_at=stamp,
        )
        tx.execute(
            """INSERT INTO cv_workflow_revisions(workspace_id,workflow_id,revision,actor_user_id,
            kind,encrypted_payload,candidate_sha256,review_run_id,review_eligible,model_run_id,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                scope.workspace_id,
                str(workflow_id),
                revision.revision,
                scope.user_id,
                kind,
                snapshot.encrypted_payload,
                snapshot.candidate_sha256,
                str(snapshot.review_run_id) if snapshot.review_run_id else None,
                int(snapshot.review_eligible),
                str(model_run_id) if model_run_id else None,
                stamp,
            ),
        )
        return revision
