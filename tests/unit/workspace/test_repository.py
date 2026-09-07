"""Cross-connection authority, leases, approvals and history on both SQL adapters."""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

import certifi
import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from ceo_voice.core.exceptions import ConfigurationError, StorageError
from ceo_voice.workspace import (
    PostgresDatabase,
    RunReservation,
    SnapshotWrite,
    SQLiteDatabase,
    WorkflowRepository,
    WorkspaceMember,
    WorkspaceScope,
)
from ceo_voice.workspace.database import SQLDatabase
from ceo_voice.workspace.errors import (
    ApprovalConflict,
    IdempotencyConflict,
    LeaseConflict,
    RevisionConflict,
    WorkflowBusy,
    WorkspaceNotFound,
    WorkspaceQuotaExceeded,
)

KEY = Fernet.generate_key()


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def snapshot(
    text: str = "Synthetic candidate", *, review_id: UUID | None = None, eligible: bool = False
) -> SnapshotWrite:
    return SnapshotWrite(
        encrypted_payload=Fernet(KEY).encrypt(text.encode()).decode(),
        candidate_sha256=digest(text),
        review_run_id=review_id,
        review_eligible=eligible,
    )


@dataclass
class Clock:
    now: datetime = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass
class Harness:
    database: SQLDatabase
    scope: WorkspaceScope
    clock: Clock

    @property
    def repository(self) -> WorkflowRepository:
        # Each access creates another repository; adapters create independent connections.
        return WorkflowRepository(self.database, clock=self.clock)


@pytest.fixture(params=["sqlite", "postgres"])
def harness(request: pytest.FixtureRequest, tmp_path: Path) -> Harness:
    if request.param == "postgres":
        url = os.environ.get("CEO_VOICE_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("explicit isolated PostgreSQL test URL/schema not configured")
        schema = os.environ.get("CEO_VOICE_TEST_POSTGRES_SCHEMA")
        if not schema or not schema.startswith("cv_test_"):
            pytest.skip("PostgreSQL tests require an isolated cv_test_* schema")
        database: SQLDatabase = PostgresDatabase(
            url,
            schema=schema,
            sslrootcert=os.environ.get("CEO_VOICE_TEST_POSTGRES_CA"),
            allow_insecure_local=os.environ.get("CEO_VOICE_TEST_POSTGRES_INSECURE") == "1",
        )
    else:
        database = SQLiteDatabase(tmp_path / "workspace.sqlite", environment="test")
    database.migrate()
    return Harness(database, WorkspaceScope(workspace_id=str(uuid4()), user_id="creator"), Clock())


def reserve(harness: Harness, key: str = "initial") -> RunReservation:
    return harness.repository.reserve_run(
        harness.scope,
        idempotency_key=key,
        operation="generate",
        request_sha256=digest("request"),
        profile_slug="synthetic-leader",
    )


def generate(
    harness: Harness, value: SnapshotWrite | None = None, key: str = "initial"
) -> RunReservation:
    claim = reserve(harness, key)
    assert claim.lease_token is not None
    harness.repository.mark_dispatched(harness.scope, claim.run.id, claim.lease_token)
    harness.repository.complete_run(
        harness.scope, claim.run.id, claim.lease_token, value or snapshot()
    )
    return claim


def test_durable_generation_idempotency_and_workspace_ownership(harness: Harness) -> None:
    value = snapshot()
    claim = generate(harness, value)
    repo = harness.repository
    again = reserve(harness)
    assert again.disposition == "existing" and again.lease_token is None
    assert again.run.id == claim.run.id and again.run.state == "completed"
    assert again.run.result_revision == 0
    workflow = repo.get_workflow(harness.scope.workspace_id, claim.run.workflow_id)
    assert workflow.owner_user_id == "creator" and workflow.head_revision == 0
    assert workflow.active_run_id is None and workflow.review_status == "unreviewed"
    revision = repo.get_revision(harness.scope.workspace_id, workflow.id)
    assert (
        revision.encrypted_payload == value.encrypted_payload
        and revision.model_run_id == claim.run.id
    )
    assert Fernet(KEY).decrypt(revision.encrypted_payload) == b"Synthetic candidate"
    assert len(repo.list_revisions(harness.scope.workspace_id, workflow.id)) == 1
    assert repo.list_workflows(harness.scope.workspace_id)[0].id == workflow.id
    foreign = WorkspaceScope(workspace_id="other-workspace", user_id="creator")
    for operation in (
        lambda: repo.get_workflow(foreign.workspace_id, workflow.id),
        lambda: repo.get_revision(foreign.workspace_id, workflow.id),
        lambda: repo.list_revisions(foreign.workspace_id, workflow.id),
        lambda: repo.list_reviews(foreign.workspace_id, workflow.id),
        lambda: repo.get_run(foreign, "initial"),
        lambda: repo.get_run(
            WorkspaceScope(workspace_id=harness.scope.workspace_id, user_id="other-user"), "initial"
        ),
    ):
        with pytest.raises(WorkspaceNotFound):
            operation()
    assert repo.list_workflows(foreign.workspace_id) == ()
    assert claim.lease_token is not None
    assert repo.complete_run(harness.scope, claim.run.id, claim.lease_token, value) == revision
    with pytest.raises(IdempotencyConflict):
        repo.complete_run(
            harness.scope, claim.run.id, claim.lease_token, snapshot("Different candidate")
        )


def test_one_concurrent_claim_even_across_independent_connections(harness: Harness) -> None:
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda _: reserve(harness), range(6)))
    assert sum(claim.disposition == "acquired" for claim in claims) == 1
    assert len({claim.run.id for claim in claims}) == 1
    assert len({claim.run.workflow_id for claim in claims}) == 1
    assert len(harness.repository.list_workflows(harness.scope.workspace_id)) == 1


def test_request_or_profile_changes_cannot_reuse_an_idempotency_key(harness: Harness) -> None:
    claim = generate(harness)
    repo = harness.repository
    with pytest.raises(IdempotencyConflict):
        repo.reserve_run(
            harness.scope,
            idempotency_key="initial",
            operation="generate",
            request_sha256=digest("different"),
            profile_slug="synthetic-leader",
        )
    with pytest.raises(IdempotencyConflict):
        repo.reserve_run(
            harness.scope,
            idempotency_key="initial",
            operation="generate",
            request_sha256=digest("request"),
            profile_slug="another-leader",
        )
    with pytest.raises(IdempotencyConflict):
        repo.reserve_run(
            harness.scope,
            idempotency_key="initial",
            operation="revoice",
            request_sha256=digest("request"),
            workflow_id=claim.run.workflow_id,
            expected_revision=0,
        )
    with pytest.raises(IdempotencyConflict):
        repo.get_run(harness.scope, "initial", request_sha256=digest("different"))
    assert (
        repo.get_run(harness.scope, "initial", request_sha256=digest("request")).state
        == "completed"
    )


def test_concurrent_revoices_reserve_one_head_before_any_provider_charge(harness: Harness) -> None:
    initial = generate(harness)

    def attempt(key: str) -> RunReservation | WorkflowBusy:
        try:
            return harness.repository.reserve_run(
                harness.scope,
                idempotency_key=key,
                operation="revoice",
                request_sha256=digest(key),
                workflow_id=initial.run.workflow_id,
                expected_revision=0,
            )
        except WorkflowBusy as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, ("edit-a", "edit-b")))
    assert sum(isinstance(item, WorkflowBusy) for item in outcomes) == 1
    claim = next(item for item in outcomes if isinstance(item, RunReservation))
    assert claim.lease_token is not None
    repo = harness.repository
    with pytest.raises(WorkflowBusy):
        repo.append_revision(
            harness.scope,
            initial.run.workflow_id,
            expected_revision=0,
            snapshot=snapshot("manual edit"),
        )
    repo.mark_dispatched(harness.scope, claim.run.id, claim.lease_token)
    changed = repo.complete_run(
        harness.scope, claim.run.id, claim.lease_token, snapshot("Revoiced candidate")
    )
    assert changed.revision == 1 and changed.kind == "revoice"
    with pytest.raises(RevisionConflict):
        repo.reserve_run(
            harness.scope,
            idempotency_key="stale",
            operation="revoice",
            request_sha256=digest("stale"),
            workflow_id=initial.run.workflow_id,
            expected_revision=0,
        )
    with pytest.raises(WorkspaceNotFound):
        repo.get_run(harness.scope, "stale")


def test_optimistic_cas_rejects_concurrent_forked_edits(harness: Harness) -> None:
    initial = generate(harness)

    def edit(text: str) -> int | RevisionConflict:
        try:
            return harness.repository.append_revision(
                harness.scope, initial.run.workflow_id, expected_revision=0, snapshot=snapshot(text)
            ).revision
        except RevisionConflict as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ("Editor A content", "Editor B content")))
    assert results.count(1) == 1
    assert sum(isinstance(item, RevisionConflict) for item in results) == 1
    history = harness.repository.list_revisions(harness.scope.workspace_id, initial.run.workflow_id)
    assert [item.revision for item in history] == [1, 0]


def test_expired_undispatched_lease_can_be_reclaimed_but_old_worker_is_fenced(
    harness: Harness,
) -> None:
    first = reserve(harness)
    assert first.lease_token is not None
    harness.clock.advance(301)
    with pytest.raises(LeaseConflict):
        harness.repository.mark_dispatched(harness.scope, first.run.id, first.lease_token)
    replacement = reserve(harness)
    assert replacement.disposition == "acquired" and replacement.run.id == first.run.id
    assert replacement.lease_token is not None and replacement.lease_token != first.lease_token
    with pytest.raises(LeaseConflict):
        harness.repository.mark_dispatched(harness.scope, first.run.id, first.lease_token)
    harness.repository.mark_dispatched(harness.scope, replacement.run.id, replacement.lease_token)
    with pytest.raises(LeaseConflict):
        harness.repository.mark_dispatched(
            harness.scope, replacement.run.id, replacement.lease_token
        )


def test_expired_dispatched_run_never_automatically_repeats_provider_work(harness: Harness) -> None:
    original = generate(harness)
    repo = harness.repository
    claim = repo.reserve_run(
        harness.scope,
        idempotency_key="rewrite",
        operation="revoice",
        request_sha256=digest("rewrite"),
        workflow_id=original.run.workflow_id,
        expected_revision=0,
    )
    assert claim.lease_token is not None
    repo.mark_dispatched(harness.scope, claim.run.id, claim.lease_token)
    harness.clock.advance(301)
    uncertain = repo.get_run(harness.scope, "rewrite")
    assert (
        uncertain.state == "indeterminate"
        and uncertain.error_code == "lease_expired_after_dispatch"
    )
    repeat = repo.reserve_run(
        harness.scope,
        idempotency_key="rewrite",
        operation="revoice",
        request_sha256=digest("rewrite"),
        workflow_id=original.run.workflow_id,
        expected_revision=0,
    )
    assert repeat.disposition == "existing" and repeat.lease_token is None
    with pytest.raises(WorkflowBusy):
        repo.reserve_run(
            harness.scope,
            idempotency_key="another-charge",
            operation="revoice",
            request_sha256=digest("another-charge"),
            workflow_id=original.run.workflow_id,
            expected_revision=0,
        )
    with pytest.raises(LeaseConflict):
        repo.heartbeat(harness.scope, claim.run.id, claim.lease_token)
    # The original worker can reconcile an eventually returned provider result without charging again.
    late = repo.complete_run(
        harness.scope, claim.run.id, claim.lease_token, snapshot("Late provider result")
    )
    assert late.revision == 1


def test_heartbeat_known_failure_and_ambiguous_failure_state_transitions(harness: Harness) -> None:
    claim = reserve(harness)
    assert claim.lease_token is not None
    repo = harness.repository
    with pytest.raises(LeaseConflict):
        repo.complete_run(harness.scope, claim.run.id, claim.lease_token, snapshot())
    harness.clock.advance(30)
    updated = repo.heartbeat(harness.scope, claim.run.id, claim.lease_token, lease_seconds=600)
    assert updated.lease_expires_at > claim.run.lease_expires_at
    repo.mark_dispatched(harness.scope, claim.run.id, claim.lease_token)
    ambiguous = repo.fail_run(
        harness.scope,
        claim.run.id,
        claim.lease_token,
        error_code="provider_timeout",
        uncertain=True,
    )
    assert ambiguous.state == "indeterminate"
    assert (
        repo.get_workflow(harness.scope.workspace_id, claim.run.workflow_id).active_run_id
        == claim.run.id
    )
    known = repo.fail_run(
        harness.scope,
        claim.run.id,
        claim.lease_token,
        error_code="provider_rejected",
        uncertain=False,
    )
    assert known.state == "failed"
    assert (
        repo.get_workflow(harness.scope.workspace_id, claim.run.workflow_id).active_run_id is None
    )
    assert reserve(harness).run.state == "failed"
    with pytest.raises(LeaseConflict):
        repo.fail_run(
            harness.scope, claim.run.id, claim.lease_token, error_code="unknown", uncertain=True
        )
    finished = generate(harness, key="success")
    assert finished.lease_token is not None
    with pytest.raises(LeaseConflict):
        repo.fail_run(
            harness.scope, finished.run.id, finished.lease_token, error_code="late_failure"
        )
    with pytest.raises(WorkspaceNotFound):
        repo.mark_dispatched(
            WorkspaceScope(workspace_id="elsewhere", user_id="creator"),
            claim.run.id,
            claim.lease_token,
        )


def test_human_approval_is_bound_to_current_candidate_review_run_and_named_reviewer(
    harness: Harness,
) -> None:
    review_id = uuid4()
    value = snapshot(review_id=review_id, eligible=True)
    initial = generate(harness, value)
    reviewer = WorkspaceScope(workspace_id=harness.scope.workspace_id, user_id="named-reviewer")
    repo = harness.repository
    review = repo.record_review(
        reviewer,
        initial.run.workflow_id,
        expected_revision=0,
        candidate_sha256=value.candidate_sha256,
        review_run_id=review_id,
        decision="approved",
        note="Synthetic test review",
    )
    assert review.reviewer_user_id == "named-reviewer"
    assert (
        repo.get_workflow(harness.scope.workspace_id, initial.run.workflow_id).review_status
        == "approved"
    )
    with pytest.raises(ApprovalConflict):
        repo.record_review(
            reviewer,
            initial.run.workflow_id,
            expected_revision=0,
            candidate_sha256=digest("wrong"),
            review_run_id=review_id,
            decision="approved",
        )
    with pytest.raises(ApprovalConflict):
        repo.record_review(
            reviewer,
            initial.run.workflow_id,
            expected_revision=0,
            candidate_sha256=value.candidate_sha256,
            review_run_id=uuid4(),
            decision="approved",
        )
    changed = repo.append_revision(
        harness.scope, initial.run.workflow_id, expected_revision=0, snapshot=snapshot("Human edit")
    )
    assert changed.revision == 1
    assert (
        repo.get_workflow(harness.scope.workspace_id, initial.run.workflow_id).review_status
        == "unreviewed"
    )
    assert repo.list_reviews(harness.scope.workspace_id, initial.run.workflow_id) == (review,)
    with pytest.raises(RevisionConflict):
        repo.record_review(
            reviewer,
            initial.run.workflow_id,
            expected_revision=0,
            candidate_sha256=value.candidate_sha256,
            review_run_id=review_id,
            decision="approved",
        )


def test_review_binding_cannot_be_reused_for_changed_candidate_or_other_workflow(
    harness: Harness,
) -> None:
    review_id = uuid4()
    value = snapshot(review_id=review_id, eligible=True)
    first = generate(harness, value)
    repo = harness.repository
    with pytest.raises(ApprovalConflict):
        repo.append_revision(
            harness.scope,
            first.run.workflow_id,
            expected_revision=0,
            snapshot=snapshot("Changed candidate", review_id=review_id, eligible=True),
        )
    assert repo.get_workflow(harness.scope.workspace_id, first.run.workflow_id).head_revision == 0
    second = reserve(harness, "second")
    assert second.lease_token is not None
    repo.mark_dispatched(harness.scope, second.run.id, second.lease_token)
    with pytest.raises(ApprovalConflict):
        repo.complete_run(harness.scope, second.run.id, second.lease_token, value)
    assert repo.get_run(harness.scope, "second").state == "dispatched"
    assert repo.get_workflow(harness.scope.workspace_id, second.run.workflow_id).head_revision == -1


def test_failed_automatic_review_blocks_approval_and_active_work_blocks_review(
    harness: Harness,
) -> None:
    review_id = uuid4()
    value = snapshot(review_id=review_id)
    initial = generate(harness, value)
    repo = harness.repository
    with pytest.raises(ApprovalConflict):
        repo.record_review(
            harness.scope,
            initial.run.workflow_id,
            expected_revision=0,
            candidate_sha256=value.candidate_sha256,
            review_run_id=review_id,
            decision="approved",
        )
    rejected = repo.record_review(
        harness.scope,
        initial.run.workflow_id,
        expected_revision=0,
        candidate_sha256=value.candidate_sha256,
        review_run_id=review_id,
        decision="changes_requested",
    )
    assert rejected.decision == "changes_requested"
    repo.reserve_run(
        harness.scope,
        idempotency_key="revision",
        operation="revoice",
        request_sha256=digest("revision"),
        workflow_id=initial.run.workflow_id,
        expected_revision=0,
    )
    with pytest.raises(WorkflowBusy):
        repo.record_review(
            harness.scope,
            initial.run.workflow_id,
            expected_revision=0,
            candidate_sha256=value.candidate_sha256,
            review_run_id=review_id,
            decision="changes_requested",
        )


def test_database_rejects_rewriting_or_deleting_history(harness: Harness) -> None:
    value = snapshot(review_id=uuid4(), eligible=True)
    initial = generate(harness, value)
    assert value.review_run_id is not None
    harness.repository.record_review(
        harness.scope,
        initial.run.workflow_id,
        expected_revision=0,
        candidate_sha256=value.candidate_sha256,
        review_run_id=value.review_run_id,
        decision="approved",
    )
    for table in ("cv_workflow_revisions", "cv_workflow_reviews", "cv_review_runs"):
        for statement in (
            f"DELETE FROM {table} WHERE workspace_id=?",
            f"UPDATE {table} SET workspace_id=workspace_id WHERE workspace_id=?",
        ):
            with (
                pytest.raises(StorageError, match="transaction failed"),
                harness.database.transaction() as tx,
            ):
                tx.execute(statement, (harness.scope.workspace_id,))
    assert (
        len(harness.repository.list_revisions(harness.scope.workspace_id, initial.run.workflow_id))
        == 1
    )


def test_membership_is_explicit_partitioned_and_can_be_revoked(harness: Harness) -> None:
    repo = harness.repository
    assert repo.get_member(harness.scope.workspace_id, "editor") is None
    member = WorkspaceMember(
        workspace_id=harness.scope.workspace_id, user_id="editor", role="editor"
    )
    assert repo.upsert_member(member) == member
    assert repo.get_member(harness.scope.workspace_id, "editor") == member
    assert repo.list_members(harness.scope.workspace_id) == (member,)
    assert repo.list_members("other-workspace") == ()
    changed = member.model_copy(update={"role": "viewer", "active": False})
    repo.upsert_member(changed)
    revoked = repo.get_member(harness.scope.workspace_id, "editor")
    assert revoked is not None and revoked.active is False
    harness.database.migrate()  # Explicit migration is safely repeatable.


def test_invalid_boundaries_missing_history_and_wrong_lease_fail_closed(harness: Harness) -> None:
    repo = harness.repository
    claim = reserve(harness)
    assert claim.lease_token is not None
    with pytest.raises(LeaseConflict):
        repo.mark_dispatched(harness.scope, claim.run.id, uuid4())
    with pytest.raises(WorkspaceNotFound):
        repo.get_revision(harness.scope.workspace_id, claim.run.workflow_id)
    with pytest.raises(ValueError):
        repo.reserve_run(
            harness.scope,
            idempotency_key="bad",
            operation="generate",
            request_sha256=digest("a"),
            lease_seconds=1,
        )
    with pytest.raises(ValueError):
        repo.reserve_run(
            harness.scope, idempotency_key="bad", operation="generate", request_sha256=digest("a")
        )
    with pytest.raises(ValueError):
        repo.reserve_run(
            harness.scope, idempotency_key="bad", operation="revoice", request_sha256=digest("a")
        )
    with pytest.raises(ValueError):
        repo.heartbeat(harness.scope, claim.run.id, claim.lease_token, lease_seconds=1)
    with pytest.raises(ValueError):
        repo.fail_run(
            harness.scope,
            claim.run.id,
            claim.lease_token,
            error_code="secret content in diagnostic",
        )
    with pytest.raises(ValueError):
        repo.list_workflows(harness.scope.workspace_id, limit=102)
    with pytest.raises(ValueError):
        repo.append_revision(
            harness.scope,
            claim.run.workflow_id,
            expected_revision=-1,
            snapshot=snapshot(),
            kind="generation",
        )
    repo.fail_run(
        harness.scope, claim.run.id, claim.lease_token, error_code="cancelled_before_dispatch"
    )
    with pytest.raises(RevisionConflict):
        repo.append_revision(
            harness.scope, claim.run.workflow_id, expected_revision=-1, snapshot=snapshot()
        )
    with pytest.raises(ValidationError):
        snapshot(eligible=True)
    with pytest.raises(ValidationError):
        SnapshotWrite(
            encrypted_payload='{"plaintext":"not encrypted"}', candidate_sha256=digest("a")
        )


def test_sqlite_is_prohibited_in_production_or_on_vercel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ConfigurationError):
        SQLiteDatabase(
            tmp_path / "no.db", environment=cast(Literal["development", "test"], "production")
        )
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(ConfigurationError):
        SQLiteDatabase(tmp_path / "no.db", environment="test")
    assert not (tmp_path / "no.db").exists()


def test_postgres_configuration_requires_tls_except_explicit_loopback_tests() -> None:
    with pytest.raises(ConfigurationError):
        PostgresDatabase("sqlite://local")
    with pytest.raises(ConfigurationError):
        PostgresDatabase("postgresql://remote.example/db", allow_insecure_local=True)
    with pytest.raises(ConfigurationError):
        PostgresDatabase("postgresql://localhost/db?host=remote.example", allow_insecure_local=True)
    assert (
        PostgresDatabase("postgresql://remote.example/db?sslmode=disable")._sslmode == "verify-full"
    )
    assert PostgresDatabase("postgresql://remote.example/db")._sslrootcert == certifi.where()
    assert (
        PostgresDatabase("postgresql://localhost/db", allow_insecure_local=True)._sslmode
        == "disable"
    )
    with pytest.raises(ConfigurationError):
        PostgresDatabase("postgresql://remote.example/db", schema="public; DROP TABLE users")
    assert (
        PostgresDatabase("postgresql://remote.example/db?sslmode=verify-full")._sslmode
        == "verify-full"
    )


def test_paid_review_is_reserved_and_completes_as_evaluation(harness: Harness) -> None:
    initial = generate(harness)
    repo = harness.repository
    claim = repo.reserve_run(
        harness.scope,
        idempotency_key="paid-review",
        operation="review",
        request_sha256=digest("review-request"),
        workflow_id=initial.run.workflow_id,
        expected_revision=0,
    )
    assert claim.lease_token is not None
    repo.mark_dispatched(harness.scope, claim.run.id, claim.lease_token)
    revision = repo.complete_run(
        harness.scope,
        claim.run.id,
        claim.lease_token,
        snapshot(review_id=uuid4(), eligible=True),
    )
    assert revision.kind == "evaluation" and revision.revision == 1
    assert revision.model_run_id == claim.run.id


def test_rolling_quota_is_atomic_across_distinct_keys_and_deduplicates(harness: Harness) -> None:
    def claim(index: int) -> str:
        try:
            harness.repository.reserve_run(
                harness.scope,
                idempotency_key=f"quota-{index}",
                operation="generate",
                request_sha256=digest(str(index)),
                profile_slug="synthetic-leader",
                maximum_runs_per_hour=2,
            )
            return "acquired"
        except WorkspaceQuotaExceeded:
            return "quota"

    with ThreadPoolExecutor(max_workers=6) as pool:
        result = list(pool.map(claim, range(6)))
    assert result.count("acquired") == 2 and result.count("quota") == 4
    successful = next(index for index, state in enumerate(result) if state == "acquired")
    duplicate = harness.repository.reserve_run(
        harness.scope,
        idempotency_key=f"quota-{successful}",
        operation="generate",
        request_sha256=digest(str(successful)),
        profile_slug="synthetic-leader",
        maximum_runs_per_hour=2,
    )
    assert duplicate.disposition == "existing"
    assert len(harness.repository.list_workflows(harness.scope.workspace_id)) == 2
    harness.clock.advance(3600)
    assert claim(6) == "acquired"
    other = WorkspaceScope(workspace_id=harness.scope.workspace_id, user_id="another-editor")
    assert (
        harness.repository.reserve_run(
            other,
            idempotency_key="quota-other",
            operation="generate",
            request_sha256=digest("other"),
            profile_slug="synthetic-leader",
            maximum_runs_per_hour=1,
        ).disposition
        == "acquired"
    )
    with pytest.raises(ValueError):
        harness.repository.reserve_run(
            other,
            idempotency_key="invalid-quota",
            operation="generate",
            request_sha256=digest("a"),
            profile_slug="synthetic-leader",
            maximum_runs_per_hour=0,
        )


def test_bootstrap_is_atomic_once_and_does_not_restore_revoked_members(harness: Harness) -> None:
    scopes = [
        WorkspaceScope(workspace_id=harness.scope.workspace_id, user_id=f"owner-{i}")
        for i in range(6)
    ]
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(harness.repository.bootstrap_owner_if_empty, scopes))
    owners = [claim for claim in claims if claim is not None]
    assert len(owners) == 1
    owner = owners[0]
    scope = WorkspaceScope(workspace_id=owner.workspace_id, user_id=owner.user_id)
    assert harness.repository.bootstrap_owner_if_empty(scope) == owner
    harness.repository.upsert_member(owner.model_copy(update={"active": False}))
    assert harness.repository.bootstrap_owner_if_empty(scope) is None
    assert all(harness.repository.bootstrap_owner_if_empty(item) is None for item in scopes)
    other = WorkspaceScope(workspace_id="revoked-nonowner", user_id=str(uuid4()))
    harness.repository.upsert_member(
        WorkspaceMember(**other.model_dump(), role="viewer", active=False)
    )
    assert harness.repository.bootstrap_owner_if_empty(other) is None
    revoked = harness.repository.get_member(other.workspace_id, other.user_id)
    assert revoked is not None and revoked.active is False


def test_export_returns_only_current_approved_snapshot_atomically(harness: Harness) -> None:
    value = snapshot(review_id=uuid4(), eligible=True)
    initial = generate(harness, value)
    repo = harness.repository
    workflow_id = initial.run.workflow_id
    with pytest.raises(ApprovalConflict):
        repo.get_approved_revision(harness.scope.workspace_id, workflow_id)
    assert value.review_run_id is not None
    requested = repo.record_review(
        harness.scope,
        workflow_id,
        expected_revision=0,
        candidate_sha256=value.candidate_sha256,
        review_run_id=value.review_run_id,
        decision="changes_requested",
    )
    with pytest.raises(ApprovalConflict):
        repo.get_approved_revision(harness.scope.workspace_id, workflow_id)
    approved = repo.record_review(
        harness.scope,
        workflow_id,
        expected_revision=0,
        candidate_sha256=value.candidate_sha256,
        review_run_id=value.review_run_id,
        decision="approved",
    )
    revision, review = repo.get_approved_revision(harness.scope.workspace_id, workflow_id)
    assert revision.candidate_sha256 == value.candidate_sha256 and review == approved
    assert review.id != requested.id
    claim = repo.reserve_run(
        harness.scope,
        idempotency_key="revoice-export",
        operation="revoice",
        request_sha256=digest("revoice"),
        workflow_id=workflow_id,
        expected_revision=0,
    )
    with pytest.raises(ApprovalConflict):
        repo.get_approved_revision(harness.scope.workspace_id, workflow_id)
    assert claim.lease_token is not None
    repo.fail_run(
        harness.scope, claim.run.id, claim.lease_token, error_code="cancelled_before_dispatch"
    )
    assert repo.get_approved_revision(harness.scope.workspace_id, workflow_id)[1] == approved
    repo.append_revision(
        harness.scope, workflow_id, expected_revision=0, snapshot=snapshot("edited")
    )
    with pytest.raises(ApprovalConflict):
        repo.get_approved_revision(harness.scope.workspace_id, workflow_id)


def test_workflow_and_revision_pages_have_stable_order_and_bounds(harness: Harness) -> None:
    first = generate(harness)
    harness.clock.advance(1)
    second = generate(harness, key="second")
    repo = harness.repository
    workspace = harness.scope.workspace_id
    assert repo.list_workflows(workspace, limit=1)[0].id == second.run.workflow_id
    assert repo.list_workflows(workspace, limit=1, offset=1)[0].id == first.run.workflow_id
    assert repo.list_workflows(workspace, offset=2) == ()
    for revision in range(3):
        repo.append_revision(
            harness.scope,
            first.run.workflow_id,
            expected_revision=revision,
            snapshot=snapshot(str(revision)),
        )
    assert [
        row.revision for row in repo.list_revisions(workspace, first.run.workflow_id, limit=2)
    ] == [3, 2]
    assert [
        row.revision
        for row in repo.list_revisions(workspace, first.run.workflow_id, limit=2, offset=2)
    ] == [1, 0]
    assert len(repo.list_revisions(workspace, first.run.workflow_id, limit=101)) == 4
    with pytest.raises(ValueError):
        repo.list_workflows(workspace, offset=-1)
    with pytest.raises(ValueError):
        repo.list_revisions(workspace, first.run.workflow_id, limit=102)
