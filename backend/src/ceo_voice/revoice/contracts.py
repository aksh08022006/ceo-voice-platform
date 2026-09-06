"""Immutable Re-Voice inputs, edit decisions, validation, output, and report contracts."""

from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from ceo_voice.context import GenerationContext
from ceo_voice.generation import GeneratedDraft
from ceo_voice.generation.contracts import TokenUsage
from ceo_voice.generation.enums import ProviderName
from ceo_voice.models.base import ContractModel, NonBlankText, NonEmptyStr, UtcDatetime
from ceo_voice.profiles import PublishedVoiceProfile
from ceo_voice.retrieval import RetrievalBundle
from ceo_voice.revoice.enums import (
    ChangeKind,
    ProtectionKind,
    ReVoiceAttemptKind,
    ReVoiceValidationCode,
)
from ceo_voice.virality import ViralityProfile


class ReVoiceEngineVersion(ContractModel):
    major: int = Field(ge=0)
    minor: int = Field(ge=0)
    patch: int = Field(ge=0)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class ReVoicePolicy(ContractModel):
    """Conservative limits governing one restoration operation."""

    version: ReVoiceEngineVersion = ReVoiceEngineVersion(major=1, minor=0, patch=0)
    prompt_version: NonEmptyStr = "revoice-prompt/1.0.0"
    provider: ProviderName
    model: NonEmptyStr
    model_context_tokens: int = Field(default=32_000, ge=512)
    maximum_output_tokens: int = Field(default=1_200, ge=32)
    maximum_provider_retries: int = Field(default=2, ge=0, le=10)
    maximum_validation_retries: int = Field(default=1, ge=0, le=5)
    maximum_changed_fraction: float = Field(default=0.35, gt=0, le=1)
    estimated_characters_per_token: float = Field(default=4.0, ge=1, le=10)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.maximum_output_tokens >= self.model_context_tokens:
            raise ValueError("output budget must be smaller than model context")
        return self


class TextChange(ContractModel):
    kind: ChangeKind
    original_start: int = Field(ge=0)
    original_end: int = Field(ge=0)
    edited_start: int = Field(ge=0)
    edited_end: int = Field(ge=0)
    original_text: str
    edited_text: str


class DifferenceAnalysis(ContractModel):
    original_hash: NonEmptyStr
    edited_hash: NonEmptyStr
    similarity: float = Field(ge=0, le=1)
    changes: tuple[TextChange, ...]
    changed_line_indices: tuple[int, ...]


class EditableRegion(ContractModel):
    region_id: NonEmptyStr
    line_index: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    content: NonBlankText
    reason: NonEmptyStr


class ProtectedRegion(ContractModel):
    region_id: NonEmptyStr
    line_index: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    content: NonBlankText
    kind: ProtectionKind
    reason: NonEmptyStr


class RegionPlan(ContractModel):
    editable: tuple[EditableRegion, ...]
    protected: tuple[ProtectedRegion, ...]


class ReVoiceFinding(ContractModel):
    code: ReVoiceValidationCode
    message: NonEmptyStr
    blocking: bool
    region_ids: tuple[NonEmptyStr, ...] = ()


class ReVoiceValidation(ContractModel):
    valid: bool
    findings: tuple[ReVoiceFinding, ...]
    changed_fraction: float = Field(ge=0, le=1)
    protected_regions_preserved: int = Field(ge=0)
    protected_regions_total: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_disposition(self) -> Self:
        if self.valid == any(item.blocking for item in self.findings):
            raise ValueError("validation disposition must match blocking findings")
        if self.protected_regions_preserved > self.protected_regions_total:
            raise ValueError("preserved protected-region count exceeds total")
        return self


class ReVoiceAttempt(ContractModel):
    number: int = Field(ge=1)
    kind: ReVoiceAttemptKind
    provider: ProviderName
    model: NonEmptyStr
    latency_ms: int = Field(ge=0)
    usage: TokenUsage | None
    validation: ReVoiceValidation | None
    error_code: str | None = None


class PreservedDecision(ContractModel):
    subject: NonEmptyStr
    reason: NonEmptyStr


class VoiceFeatureStrengthening(ContractModel):
    feature_id: NonEmptyStr
    target: str
    confidence: float = Field(ge=0, le=1)
    assessment: NonEmptyStr


class ReVoiceReport(ContractModel):
    engine_version: ReVoiceEngineVersion
    prompt_version: NonEmptyStr
    original_draft_id: UUID
    context_id: UUID
    retrieval_bundle_id: UUID
    hvm_release_id: UUID
    vkr_release_id: UUID
    difference: DifferenceAnalysis
    regions: RegionPlan
    changed_regions: tuple[NonEmptyStr, ...]
    preserved: tuple[PreservedDecision, ...]
    voice_features_strengthened: tuple[VoiceFeatureStrengthening, ...]
    constrained_by: tuple[NonEmptyStr, ...]
    attempts: tuple[ReVoiceAttempt, ...]
    total_usage: TokenUsage
    total_latency_ms: int = Field(ge=0)
    final_validation: ReVoiceValidation
    confidence: float = Field(ge=0, le=1)


class ReVoicedDraft(ContractModel):
    id: UUID
    original_draft_id: UUID
    content: NonBlankText
    thread: tuple[NonBlankText, ...]
    report: ReVoiceReport
    created_at: UtcDatetime


class EditedDraft(ContractModel):
    """Human edit with the initial generation and immediate prior accepted revision."""

    original: GeneratedDraft
    content: NonBlankText
    edited_at: UtcDatetime
    previous_revision: ReVoicedDraft | None = None

    @model_validator(mode="after")
    def validate_previous_revision(self) -> Self:
        previous = self.previous_revision
        if previous is not None and (
            previous.original_draft_id != self.original.id
            or previous.report.original_draft_id != self.original.id
            or previous.report.retrieval_bundle_id != self.original.report.retrieval_bundle_id
        ):
            raise ValueError("previous revision must belong to the original generated draft")
        return self

    @property
    def baseline_content(self) -> str:
        return self.previous_revision.content if self.previous_revision else self.original.content


class ReVoiceInput(ContractModel):
    """Complete sealed input needed to restore voice without hidden lookups."""

    edited_draft: EditedDraft
    context: GenerationContext
    retrieval: RetrievalBundle
    voice_profile: PublishedVoiceProfile
    virality_profile: ViralityProfile
    requested_at: UtcDatetime
