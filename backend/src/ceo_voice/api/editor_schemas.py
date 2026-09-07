"""Strict editor commands and encrypted state; identity never comes from a command."""

from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from ceo_voice.api.schemas import GenerateWorkflowRequest
from ceo_voice.generation.editor_revision import RevisionProposal
from ceo_voice.generation.fidelity_contracts import BriefSource, FidelityReview
from ceo_voice.models.base import ContractModel, NonBlankText


class EditorSourceInput(ContractModel):
    title: NonBlankText = Field(max_length=300)
    text: NonBlankText = Field(max_length=8_000)
    url: str | None = Field(default=None, max_length=2_000, pattern=r"^https?://")
    attribution: str | None = Field(default=None, max_length=500)


class EditorGenerateRequest(GenerateWorkflowRequest):
    constraints: tuple[NonBlankText, ...] = Field(default=(), max_length=16)
    sources: tuple[EditorSourceInput, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def bounded_brief(self) -> Self:
        if any(len(text) > 1_000 for text in self.constraints):
            raise ValueError("individual constraints must fit 1000 characters")
        if (
            len(self.idea)
            + sum(len(s.text) + len(s.title) for s in self.sources)
            + sum(map(len, self.constraints))
            > 18_000
        ):
            raise ValueError("the complete factual brief exceeds the editor limit")
        return self


class ExpectedRevision(ContractModel):
    expected_revision_id: UUID


class EditorEditRequest(ExpectedRevision):
    content: NonBlankText = Field(max_length=12_000)


class EditorRestoreRequest(ExpectedRevision):
    revision_id: UUID
    revision_number: int = Field(ge=1)


class EditorApprovalRequest(ContractModel):
    revision_id: UUID
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    brief_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_run_id: UUID
    note: str = Field(min_length=20, max_length=2_000)
    reviewed_claim_ids: tuple[str, ...] = Field(max_length=500)

    @model_validator(mode="after")
    def validate_acknowledgement(self) -> Self:
        if len(self.note.strip()) < 20:
            raise ValueError("approval requires an explanatory review note")
        if len(self.reviewed_claim_ids) != len(set(self.reviewed_claim_ids)):
            raise ValueError("claim acknowledgements must not be duplicated")
        return self


class EditorState(ContractModel):
    schema_version: Literal["editor/1"] = "editor/1"
    workspace_id: str
    workflow_id: UUID
    revision_number: int = Field(ge=0)
    profile_slug: str
    profile_name: str
    brief_id: UUID
    brief_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    request: EditorGenerateRequest
    content: NonBlankText = Field(max_length=12_000)
    continuation_token: str = Field(min_length=1, max_length=2_000_000)
    created_by_id: str
    created_by_name: str
    kind: Literal["generated", "human_edit", "revoiced", "restored"]
    fidelity_review: FidelityReview | None = None
    review_run_id: UUID | None = None
    regeneration_count: int = Field(default=0, ge=0)
    format_valid: bool = False
    review_sources: tuple[BriefSource, ...] = Field(default=(), max_length=64)
    revision_proposal: RevisionProposal | None = None


class StoredApprovalNote(ContractModel):
    format: Literal["editor-approval/1"] = "editor-approval/1"
    display_name: str
    note: str
    reviewed_claim_ids: tuple[str, ...] = ()


class EditorCursor(ContractModel):
    kind: Literal["drafts", "revisions"]
    workspace_id: str
    workflow_id: UUID | None = None
    head_revision: int | None = None
    offset: int = Field(ge=0, le=1_000_000)
