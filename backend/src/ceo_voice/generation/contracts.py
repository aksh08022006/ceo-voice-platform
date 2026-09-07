"""Provider-neutral generation input, prompt, result, and report contracts."""

from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from ceo_voice.context import GenerationContext
from ceo_voice.generation.enums import AttemptKind, PromptSectionKind, ProviderName, ValidationCode
from ceo_voice.generation.fidelity_contracts import FidelityPolicy, FidelityReview
from ceo_voice.models.base import ContractModel, NonBlankText, NonEmptyStr, UtcDatetime
from ceo_voice.retrieval import RetrievalBundle
from ceo_voice.schemas.generation import GenerationRequest


class GenerationEngineVersion(ContractModel):
    major: int = Field(ge=0)
    minor: int = Field(ge=0)
    patch: int = Field(ge=0)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class GenerationPolicy(ContractModel):
    version: GenerationEngineVersion = GenerationEngineVersion(major=1, minor=0, patch=0)
    provider: ProviderName
    model: NonEmptyStr
    model_context_tokens: int = Field(ge=512)
    maximum_output_tokens: int = Field(default=800, ge=32)
    maximum_provider_retries: int = Field(default=2, ge=0, le=10)
    maximum_validation_retries: int = Field(default=1, ge=0, le=5)
    estimated_characters_per_token: float = Field(default=4.0, ge=1, le=10)
    minimum_voice_confidence: float = Field(default=0.5, ge=0, le=1)
    fidelity: FidelityPolicy = FidelityPolicy()

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.maximum_output_tokens >= self.model_context_tokens:
            raise ValueError("output budget must be smaller than model context")
        return self


class GenerationInput(ContractModel):
    request: GenerationRequest
    context: GenerationContext
    retrieval: RetrievalBundle
    generated_at: UtcDatetime


class PromptSection(ContractModel):
    kind: PromptSectionKind
    content: NonBlankText
    mandatory: bool
    priority: int = Field(ge=1, le=100)
    source_ids: tuple[UUID, ...] = ()


class StructuredPrompt(ContractModel):
    version: NonEmptyStr
    sections: tuple[PromptSection, ...] = Field(min_length=1)
    included_evidence_ids: tuple[UUID, ...]
    pruned_evidence_ids: tuple[UUID, ...]


class RenderedPrompt(ContractModel):
    version: NonEmptyStr
    system: NonBlankText
    user: NonBlankText
    estimated_input_tokens: int = Field(ge=1)
    included_evidence_ids: tuple[UUID, ...]
    pruned_evidence_ids: tuple[UUID, ...]


class ProviderRequest(ContractModel):
    request_id: UUID
    system: NonBlankText
    user: NonBlankText
    model: NonEmptyStr
    maximum_output_tokens: int = Field(ge=1)


class TokenUsage(ContractModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ProviderResult(ContractModel):
    text: NonBlankText
    provider: ProviderName
    model: NonEmptyStr
    provider_request_id: str | None = None
    usage: TokenUsage
    latency_ms: int = Field(ge=0)


class ValidationFinding(ContractModel):
    code: ValidationCode
    message: NonEmptyStr
    blocking: bool


class OutputValidation(ContractModel):
    valid: bool
    findings: tuple[ValidationFinding, ...]
    character_count: int = Field(ge=0)
    thread_posts: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_disposition(self) -> Self:
        if self.valid == any(item.blocking for item in self.findings):
            raise ValueError("validation disposition must match blocking findings")
        return self


class GenerationAttempt(ContractModel):
    number: int = Field(ge=1)
    kind: AttemptKind
    prompt_version: NonEmptyStr
    provider: ProviderName
    model: NonEmptyStr
    latency_ms: int = Field(ge=0)
    usage: TokenUsage | None
    validation: OutputValidation | None
    error_code: str | None = None
    fidelity_review: FidelityReview | None = None


class ConstraintResult(ContractModel):
    constraint_id: NonEmptyStr
    satisfied: bool | None
    detail: NonEmptyStr


class GenerationReport(ContractModel):
    engine_version: GenerationEngineVersion
    prompt_version: NonEmptyStr
    retrieval_bundle_id: UUID
    selected_evidence_ids: tuple[UUID, ...]
    voice_feature_ids: tuple[NonEmptyStr, ...]
    structural_pattern_ids: tuple[UUID, ...]
    provider: ProviderName
    model: NonEmptyStr
    attempts: tuple[GenerationAttempt, ...]
    total_latency_ms: int = Field(ge=0)
    total_usage: TokenUsage
    final_validation: OutputValidation
    constraint_results: tuple[ConstraintResult, ...]
    fidelity_review: FidelityReview | None = None
    generation_call_count: int | None = Field(default=None, ge=0)
    fidelity_call_count: int | None = Field(default=None, ge=0)
    total_model_calls: int | None = Field(default=None, ge=0)
    maximum_generation_calls: int | None = Field(default=None, ge=1)
    maximum_fidelity_calls: int | None = Field(default=None, ge=0)


class GeneratedDraft(ContractModel):
    id: UUID
    request_id: UUID
    content: NonBlankText
    thread: tuple[NonBlankText, ...]
    report: GenerationReport
    created_at: UtcDatetime
