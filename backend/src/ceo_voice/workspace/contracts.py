"""Workspace persistence contracts; identities come only from authenticated server context."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from ceo_voice.models.base import ContractModel, UtcDatetime

Identity = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
EncryptedPayload = Annotated[
    str, StringConstraints(min_length=1, max_length=2_000_000, pattern=r"^[A-Za-z0-9_-]+={0,2}$")
]
RunOperation = Literal["generate", "revoice", "review"]
RunState = Literal["reserved", "dispatched", "completed", "failed", "indeterminate"]
RevisionKind = Literal["generation", "revoice", "edit", "evaluation"]
ReviewDecision = Literal["approved", "changes_requested"]
MemberRole = Literal["owner", "admin", "editor", "reviewer", "viewer"]


class WorkspaceScope(ContractModel):
    workspace_id: Identity
    user_id: Identity


class WorkspaceMember(WorkspaceScope):
    role: MemberRole
    active: bool = True


class SnapshotWrite(ContractModel):
    """Already-encrypted compact state and trusted server-computed candidate/review evidence."""

    encrypted_payload: EncryptedPayload
    candidate_sha256: Digest
    review_run_id: UUID | None = None
    review_eligible: bool = False

    @model_validator(mode="after")
    def validate_review(self) -> "SnapshotWrite":
        if self.review_eligible and self.review_run_id is None:
            raise ValueError("approval eligibility requires a pinned review run")
        return self


class WorkflowRecord(ContractModel):
    id: UUID
    workspace_id: Identity
    owner_user_id: Identity
    profile_slug: Identity
    head_revision: int = Field(ge=-1)
    active_run_id: UUID | None
    candidate_sha256: Digest | None
    review_status: Literal["unreviewed", "approved", "changes_requested"]
    created_at: UtcDatetime
    updated_at: UtcDatetime


class RevisionRecord(SnapshotWrite):
    workflow_id: UUID
    workspace_id: Identity
    revision: int = Field(ge=0)
    actor_user_id: Identity
    kind: RevisionKind
    model_run_id: UUID | None
    created_at: UtcDatetime


class ModelRun(ContractModel):
    id: UUID
    workspace_id: Identity
    actor_user_id: Identity
    workflow_id: UUID
    operation: RunOperation
    idempotency_key: Identity
    request_sha256: Digest
    expected_revision: int = Field(ge=-1)
    state: RunState
    lease_expires_at: UtcDatetime
    result_revision: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class RunReservation(ContractModel):
    """Only an acquired reservation includes the opaque fencing token needed to dispatch."""

    disposition: Literal["acquired", "existing"]
    run: ModelRun
    lease_token: UUID | None = None


class ReviewRecord(ContractModel):
    id: UUID
    workspace_id: Identity
    workflow_id: UUID
    revision: int = Field(ge=0)
    candidate_sha256: Digest
    review_run_id: UUID
    reviewer_user_id: Identity
    decision: ReviewDecision
    note: str = Field(default="", max_length=4000)
    created_at: UtcDatetime
