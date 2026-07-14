"""Immutable evaluation inputs, measurements, reviews, benchmarks, and reports."""

from typing import Self
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from ceo_voice.context import GenerationContext
from ceo_voice.generation import GeneratedDraft
from ceo_voice.generation.enums import ProviderName
from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import EvaluationStatus
from ceo_voice.profiles import PublishedVoiceProfile
from ceo_voice.retrieval import RetrievalBundle
from ceo_voice.revoice import EditedDraft, ReVoicedDraft
from ceo_voice.virality import ViralityProfile

from .enums import (
    BenchmarkStatus,
    EvaluationDimension,
    FailureCategory,
    MetricSource,
    ReviewRecommendation,
)


class EvaluationVersion(ContractModel):
    major: int = Field(ge=0)
    minor: int = Field(ge=0)
    patch: int = Field(ge=0)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def _default_weights() -> dict[EvaluationDimension, float]:
    return {
        EvaluationDimension.VOICE_FIDELITY: 0.25,
        EvaluationDimension.STRUCTURAL_FIDELITY: 0.15,
        EvaluationDimension.CONSTRAINT_COMPLIANCE: 0.15,
        EvaluationDimension.PLATFORM_COMPLIANCE: 0.10,
        EvaluationDimension.FACTUAL_PRESERVATION: 0.15,
        EvaluationDimension.EDIT_PRESERVATION: 0.10,
        EvaluationDimension.READABILITY: 0.10,
    }


class EvaluationPolicy(ContractModel):
    version: EvaluationVersion = EvaluationVersion(major=1, minor=0, patch=0)
    dimension_weights: dict[EvaluationDimension, float] = Field(default_factory=_default_weights)
    metric_pass_score: float = Field(default=0.70, ge=0, le=1)
    dimension_pass_score: float = Field(default=0.70, ge=0, le=1)
    warning_score: float = Field(default=0.60, ge=0, le=1)
    minimum_overall_score: float = Field(default=0.70, ge=0, le=1)
    maximum_copying_ngram_overlap: float = Field(default=0.35, ge=0, le=1)
    judge_contributes_to_score: bool = False

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if set(self.dimension_weights) != set(EvaluationDimension):
            raise ValueError("evaluation policy must weight every dimension")
        if any(value < 0 for value in self.dimension_weights.values()):
            raise ValueError("dimension weights cannot be negative")
        if sum(self.dimension_weights.values()) <= 0:
            raise ValueError("dimension weights must have positive mass")
        if self.warning_score > self.minimum_overall_score:
            raise ValueError("warning score cannot exceed the pass score")
        return self


class JudgePolicy(ContractModel):
    prompt_version: NonEmptyStr = "evaluation-judge/1.0.0"
    provider: ProviderName
    model: NonEmptyStr
    maximum_output_tokens: int = Field(default=1_200, ge=64)
    maximum_retries: int = Field(default=1, ge=0, le=5)


class HumanDimensionRating(ContractModel):
    dimension: EvaluationDimension
    score: float = Field(ge=0, le=1)
    rationale: NonEmptyStr


class HumanReview(ContractModel):
    review_id: UUID
    candidate_id: UUID
    reviewer_reference: NonEmptyStr
    ratings: tuple[HumanDimensionRating, ...] = Field(min_length=1)
    recommendation: ReviewRecommendation
    notes: NonEmptyStr
    reviewed_at: UtcDatetime

    @model_validator(mode="after")
    def validate_ratings(self) -> Self:
        dimensions = tuple(item.dimension for item in self.ratings)
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("human review dimensions must be unique")
        return self


class EvaluationInput(ContractModel):
    draft: GeneratedDraft | ReVoicedDraft
    context: GenerationContext
    retrieval: RetrievalBundle
    voice_profile: PublishedVoiceProfile
    virality_profile: ViralityProfile
    evaluated_at: UtcDatetime
    edited_draft: EditedDraft | None = None
    human_reviews: tuple[HumanReview, ...] = ()

    @model_validator(mode="after")
    def validate_draft_kind(self) -> Self:
        is_revoiced = isinstance(self.draft, ReVoicedDraft)
        if is_revoiced != (self.edited_draft is not None):
            raise ValueError(
                "Re-Voice evaluation requires its edited draft and only Re-Voice uses it"
            )
        if (
            isinstance(self.draft, ReVoicedDraft)
            and self.edited_draft is not None
            and self.draft.original_draft_id != self.edited_draft.original.id
        ):
            raise ValueError("edited draft does not belong to the Re-Voice result")
        if any(review.candidate_id != self.draft.id for review in self.human_reviews):
            raise ValueError("human reviews must reference the evaluated candidate")
        return self


class EvaluationMetric(ContractModel):
    metric_id: NonEmptyStr
    dimension: EvaluationDimension
    source: MetricSource
    score: float = Field(ge=0, le=1)
    passed: bool
    applicable: bool = True
    explanation: NonEmptyStr
    evidence_references: tuple[UUID, ...] = ()
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)


class DimensionScore(ContractModel):
    dimension: EvaluationDimension
    score: float = Field(ge=0, le=1)
    passed: bool
    metrics: tuple[EvaluationMetric, ...] = Field(min_length=1)
    summary: NonEmptyStr


class JudgeDimensionScore(ContractModel):
    dimension: EvaluationDimension
    score: float = Field(ge=0, le=1)
    rationale: NonEmptyStr
    evidence_references: tuple[UUID, ...] = ()


class JudgeReview(ContractModel):
    prompt_version: NonEmptyStr
    provider: ProviderName
    model: NonEmptyStr
    dimensions: tuple[JudgeDimensionScore, ...] = Field(min_length=1)
    recommendation: ReviewRecommendation
    limitations: tuple[NonEmptyStr, ...]
    latency_ms: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class EvaluationFailure(ContractModel):
    category: FailureCategory
    severity: EvaluationStatus
    message: NonEmptyStr
    metric_ids: tuple[NonEmptyStr, ...]
    recommended_action: NonEmptyStr


class EvaluationReport(ContractModel):
    report_id: UUID
    candidate_id: UUID
    evaluator_version: EvaluationVersion
    status: EvaluationStatus
    overall_score: float = Field(ge=0, le=1)
    dimensions: tuple[DimensionScore, ...]
    judge_review: JudgeReview | None
    human_reviews: tuple[HumanReview, ...]
    failures: tuple[EvaluationFailure, ...]
    evidence_references: tuple[UUID, ...]
    context_id: UUID
    retrieval_bundle_id: UUID
    hvm_release_id: UUID
    vkr_release_id: UUID
    recommended_improvements: tuple[NonEmptyStr, ...]
    evaluated_at: UtcDatetime


class BatchEvaluationReport(ContractModel):
    reports: tuple[EvaluationReport, ...]
    mean_score: float = Field(ge=0, le=1)
    passed: int = Field(ge=0)
    warned: int = Field(ge=0)
    failed: int = Field(ge=0)


class BenchmarkExpectation(ContractModel):
    minimum_overall_score: float = Field(ge=0, le=1)
    minimum_dimension_scores: dict[EvaluationDimension, float] = Field(default_factory=dict)


class BenchmarkCase(ContractModel):
    case_id: NonEmptyStr
    leader_label: NonEmptyStr
    evaluation_input: EvaluationInput
    expectation: BenchmarkExpectation


class BenchmarkSuite(ContractModel):
    suite_id: NonEmptyStr
    version: EvaluationVersion
    cases: tuple[BenchmarkCase, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_cases(self) -> Self:
        identifiers = tuple(item.case_id for item in self.cases)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("benchmark case IDs must be unique")
        return self


class BenchmarkCaseResult(ContractModel):
    case_id: NonEmptyStr
    leader_label: NonEmptyStr
    report: EvaluationReport
    status: BenchmarkStatus
    regressions: tuple[NonEmptyStr, ...]


class BenchmarkReport(ContractModel):
    suite_id: NonEmptyStr
    suite_version: EvaluationVersion
    cases: tuple[BenchmarkCaseResult, ...]
    status: BenchmarkStatus
    mean_score: float = Field(ge=0, le=1)


class RegressionDelta(ContractModel):
    candidate_id: UUID
    previous_score: float = Field(ge=0, le=1)
    current_score: float = Field(ge=0, le=1)
    delta: float = Field(ge=-1, le=1)
    regressed_dimensions: tuple[EvaluationDimension, ...]


class RegressionReport(ContractModel):
    status: BenchmarkStatus
    tolerance: float = Field(ge=0, le=1)
    deltas: tuple[RegressionDelta, ...]
