"""Immutable, model-neutral contracts emitted by the Context Compiler."""

from datetime import date
from typing import Self, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, JsonValue, model_validator

from ceo_voice.context.enums import (
    ConstraintCategory,
    ConstraintOperator,
    ConstraintStrength,
    IgnoredReason,
    TraceArtifactKind,
    VoiceResolutionSource,
)
from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime
from ceo_voice.models.communication import CommentContext
from ceo_voice.models.enums import ContentType, ContextRole, Platform
from ceo_voice.models.expression import ExpressionDirection, ExpressionProfile
from ceo_voice.models.retrieval import RetrievedContext, RetrievedItem
from ceo_voice.schemas.generation import GenerationRequest
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.utils.json import dumps_json
from ceo_voice.virality.contracts import ViralityProfile
from ceo_voice.virality.enums import StructuralDimension
from ceo_voice.voice.enums import DecisionState, VoiceDimension
from ceo_voice.voice.identity import VoiceIdentity
from ceo_voice.voice.registry import FeatureRegistry
from ceo_voice.voice.releases import ManagedRelease


class ContextCompilerVersion(ContractModel):
    """Domain-local semantic version for compiler and policy contracts."""

    major: int = Field(ge=0)
    minor: int = Field(ge=0)
    patch: int = Field(ge=0)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class PlatformContract(ContractModel):
    """Versioned publishing limits consumed as data rather than scattered constants."""

    platform: Platform
    version: ContextCompilerVersion
    maximum_characters: int = Field(ge=1)
    thread_output_supported: bool
    maximum_thread_posts: int | None = Field(default=None, ge=1)
    source_name: NonEmptyStr
    source_reference: NonEmptyStr
    verified_on: date

    @model_validator(mode="after")
    def validate_thread_limit(self) -> Self:
        if self.thread_output_supported != (self.maximum_thread_posts is not None):
            raise ValueError("thread support and maximum thread posts must agree")
        return self


class UserConstraint(ContractModel):
    """Typed optional caller constraint supplied outside the legacy string field."""

    constraint_id: NonEmptyStr
    category: ConstraintCategory
    strength: ConstraintStrength
    operator: ConstraintOperator
    key: NonEmptyStr
    value: JsonValue
    priority: int = Field(default=50, ge=1, le=100)
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def validate_user_category(self) -> Self:
        if self.category not in {ConstraintCategory.USER, ConstraintCategory.FORMATTING}:
            raise ValueError("caller constraints must be user or formatting constraints")
        return self


class CompilationInput(ContractModel):
    """Complete, pinned input required for one deterministic compilation."""

    request: GenerationRequest
    target_identity: VoiceIdentity
    voice_release: ManagedRelease | None
    feature_registry: FeatureRegistry
    virality_profile: ViralityProfile | None
    language: NonEmptyStr = "en"
    retrieved_evidence: RetrievedContext | None = None
    user_constraints: tuple[UserConstraint, ...] = ()
    compiled_at: UtcDatetime


class ConfidenceThresholds(ContractModel):
    """Explicit gates for promoting HVM components into generation guidance."""

    minimum_measurement_reliability: float = Field(default=0.6, ge=0, le=1)
    minimum_attribution_reliability: float = Field(default=0.7, ge=0, le=1)
    minimum_coverage: float = Field(default=0.3, ge=0, le=1)
    minimum_effective_support: float = Field(default=1.0, ge=0)
    minimum_distinctiveness: float = Field(default=0.2, ge=0, le=1)
    minimum_calibration: float = Field(default=0.5, ge=0, le=1)
    maximum_conflict: float = Field(default=0.5, ge=0, le=1)
    minimum_transfer_confidence: float = Field(default=0.5, ge=0, le=1)


class StructuralSelectionPolicy(ContractModel):
    """Support and compactness policy for structural target selection."""

    minimum_documents: int = Field(default=3, ge=1)
    minimum_leaders: int = Field(default=2, ge=1)
    minimum_comparable_fraction: float = Field(default=0.5, ge=0, le=1)
    maximum_patterns_per_dimension: int = Field(default=1, ge=1, le=5)


class ContextCompilationPolicy(ContractModel):
    """Versioned compactness and confidence policy for the orchestration boundary."""

    compiler_version: ContextCompilerVersion = ContextCompilerVersion(major=1, minor=0, patch=0)
    confidence: ConfidenceThresholds = ConfidenceThresholds()
    structure: StructuralSelectionPolicy = StructuralSelectionPolicy()
    maximum_voice_features: int = Field(default=12, ge=1, le=50)


class CompiledConstraint(ContractModel):
    """One source-attributed rule in the model-neutral constraint set."""

    constraint_id: NonEmptyStr
    category: ConstraintCategory
    strength: ConstraintStrength
    operator: ConstraintOperator
    key: NonEmptyStr
    value: JsonValue
    priority: int = Field(ge=1, le=100)
    source: NonEmptyStr
    rationale: NonEmptyStr
    trace_ids: tuple[UUID, ...] = ()


class ConstraintSummary(ContractModel):
    """Counts used by reports without duplicating compiled constraints."""

    total: int = Field(ge=0)
    hard: int = Field(ge=0)
    soft: int = Field(ge=0)
    platform: int = Field(ge=0)
    formatting: int = Field(ge=0)
    user: int = Field(ge=0)
    negative_voice: int = Field(ge=0)
    safety: int = Field(ge=0)


class ConstraintBundle(ContractModel):
    """Canonical nonduplicated constraint set and its category summary."""

    constraints: tuple[CompiledConstraint, ...]
    summary: ConstraintSummary

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        categories = tuple(item.category for item in self.constraints)
        expected = ConstraintSummary(
            total=len(self.constraints),
            hard=sum(item.strength is ConstraintStrength.HARD for item in self.constraints),
            soft=sum(item.strength is ConstraintStrength.SOFT for item in self.constraints),
            platform=categories.count(ConstraintCategory.PLATFORM),
            formatting=categories.count(ConstraintCategory.FORMATTING),
            user=categories.count(ConstraintCategory.USER),
            negative_voice=categories.count(ConstraintCategory.NEGATIVE_VOICE),
            safety=categories.count(ConstraintCategory.SAFETY),
        )
        if self.summary != expected:
            raise ValueError("constraint summary does not match the canonical constraint set")
        return self


class VoiceConfidence(ContractModel):
    """Decision-relevant uncertainty retained for one compiled voice feature."""

    measurement_reliability: float = Field(ge=0, le=1)
    attribution_reliability: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    effective_support: float = Field(ge=0)
    distinctiveness: float = Field(ge=0, le=1)
    calibration: float = Field(ge=0, le=1)
    conflict: float = Field(ge=0, le=1)
    transfer_confidence: float | None = Field(default=None, ge=0, le=1)
    selection_score: float = Field(ge=0, le=1)


class CompiledVoiceFeature(ContractModel):
    """Compact feature target resolved from core, conditional, and explicit layers."""

    feature_id: NonEmptyStr
    feature_version: NonEmptyStr
    display_name: NonEmptyStr
    dimension: VoiceDimension
    rank: int = Field(ge=1)
    resolution_source: VoiceResolutionSource
    decision_state: DecisionState
    target_value: JsonValue
    core_value: JsonValue
    conditional_delta: JsonValue | None = None
    confidence: VoiceConfidence
    component_ids: tuple[UUID, ...]
    evidence_unit_ids: tuple[UUID, ...]


class CompiledVoiceInteraction(ContractModel):
    """Supported relationship retained only when every marginal was selected."""

    interaction_id: UUID
    feature_ids: tuple[NonEmptyStr, ...]
    interaction_type: NonEmptyStr
    value: JsonValue
    component_evidence_ids: tuple[UUID, ...]
    confidence: VoiceConfidence


class VoiceTarget(ContractModel):
    """Generation-authorized HVM projection for one target context."""

    identity_id: UUID
    leader_id: UUID
    release_id: UUID
    release_version: int = Field(ge=1)
    release_content_hash: NonEmptyStr
    registry_hash: NonEmptyStr
    language: NonEmptyStr
    platform: Platform
    features: tuple[CompiledVoiceFeature, ...] = Field(min_length=1)
    interactions: tuple[CompiledVoiceInteraction, ...] = ()


class StructuralGuidance(ContractModel):
    """One descriptive, evidence-backed structure option kept separate from voice."""

    pattern_id: UUID
    feature_id: NonEmptyStr
    feature_version: NonEmptyStr
    dimension: StructuralDimension
    pattern_key: NonEmptyStr
    label: NonEmptyStr
    rank_within_dimension: int = Field(ge=1)
    support_count: int = Field(ge=1)
    leader_count: int = Field(ge=1)
    prevalence: float = Field(ge=0, le=1)
    comparable_fraction: float = Field(ge=0, le=1)
    observed_relative_difference: float | None
    supporting_observation_ids: tuple[UUID, ...]
    supporting_evidence_ids: tuple[UUID, ...]


class ViralityTarget(ContractModel):
    """Platform-specific structural projection from one active VKR release."""

    library_id: UUID
    release_id: UUID
    release_version: int = Field(ge=1)
    release_content_hash: NonEmptyStr
    platform: Platform
    influence: float = Field(ge=0, le=0.25)
    guidance: tuple[StructuralGuidance, ...] = Field(min_length=1)
    causal_claims_permitted: bool = False


class EvidenceLane(ContractModel):
    """Evidence with one explicit role and canonical rank ordering."""

    role: ContextRole
    items: tuple[RetrievedItem, ...] = ()

    @model_validator(mode="after")
    def validate_roles(self) -> Self:
        if any(item.role is not self.role for item in self.items):
            raise ValueError("evidence lane items must share the lane role")
        ranks = tuple(item.rank for item in self.items)
        if ranks != tuple(sorted(ranks)) or len(ranks) != len(set(ranks)):
            raise ValueError("evidence lane ranks must be unique and ordered")
        return self


class EvidenceBundle(ContractModel):
    """Supplied evidence partitioned by purpose; no retrieval occurs here."""

    retrieval_trace_id: UUID | None = None
    retrieval_query: str | None = None
    generated_at: UtcDatetime | None = None
    lanes: tuple[EvidenceLane, ...]

    @model_validator(mode="after")
    def validate_lanes(self) -> Self:
        if tuple(lane.role for lane in self.lanes) != tuple(ContextRole):
            raise ValueError("evidence lanes must contain every role in canonical order")
        return self


class IgnoredKnowledge(ContractModel):
    """Auditable record explaining one rejected component or pattern."""

    knowledge_id: NonEmptyStr
    knowledge_type: NonEmptyStr
    reason: IgnoredReason
    detail: NonEmptyStr


class ConfidenceSummary(ContractModel):
    """Aggregate uncertainty summary for operator inspection."""

    selected_voice_features: int = Field(ge=0)
    minimum_voice_score: float | None = Field(default=None, ge=0, le=1)
    mean_voice_score: float | None = Field(default=None, ge=0, le=1)
    selected_structural_patterns: int = Field(ge=0)
    minimum_structural_support: int | None = Field(default=None, ge=1)


class TraceReference(ContractModel):
    """Typed edge back to an immutable source artifact or evidence unit."""

    kind: TraceArtifactKind
    identifier: UUID
    parent_identifier: UUID | None = None


class CompilationReport(ContractModel):
    """Selection, rejection, confidence, and evidence diagnostics."""

    selected_voice_feature_ids: tuple[NonEmptyStr, ...]
    ignored_voice: tuple[IgnoredKnowledge, ...]
    selected_structural_pattern_ids: tuple[UUID, ...]
    ignored_structure: tuple[IgnoredKnowledge, ...]
    constraint_summary: ConstraintSummary
    confidence_summary: ConfidenceSummary
    traceability: tuple[TraceReference, ...]


class GenerationIntent(ContractModel):
    """Generation request semantics without model or prompt configuration."""

    request_id: UUID
    tenant_id: UUID
    leader_id: UUID
    topic: NonEmptyStr
    expression: ExpressionDirection | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    expression_profile: ExpressionProfile | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    objective: NonEmptyStr
    audience: NonEmptyStr
    platform: Platform
    content_type: ContentType
    thread_post_count: int | None = Field(default=None, ge=2, le=5)
    minimum_words: int | None = Field(default=None, ge=1, le=2_000)
    maximum_words: int | None = Field(default=None, ge=1, le=2_000)
    comment_context: CommentContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    candidate_count: int = Field(ge=1, le=10)
    source_document_ids: tuple[UUID, ...]


class GenerationContext(ContractModel):
    """Only structured object future prompt builders and generators may consume."""

    context_id: UUID
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    compiler_version: ContextCompilerVersion
    compiled_at: UtcDatetime
    intent: GenerationIntent
    platform: PlatformContract
    voice: VoiceTarget
    virality: ViralityTarget
    constraints: ConstraintBundle
    evidence: EvidenceBundle
    report: CompilationReport

    @model_validator(mode="after")
    def validate_seal(self) -> Self:
        expected_hash = compute_generation_context_hash(
            compiler_version=self.compiler_version,
            compiled_at=self.compiled_at,
            intent=self.intent,
            platform=self.platform,
            voice=self.voice,
            virality=self.virality,
            constraints=self.constraints,
            evidence=self.evidence,
            report=self.report,
        )
        if self.content_hash != expected_hash:
            raise ValueError("generation context content hash does not match its payload")
        if self.context_id != generation_context_id(expected_hash):
            raise ValueError("generation context ID does not match its content hash")
        return self


def compute_generation_context_hash(
    *,
    compiler_version: ContextCompilerVersion,
    compiled_at: UtcDatetime,
    intent: GenerationIntent,
    platform: PlatformContract,
    voice: VoiceTarget,
    virality: ViralityTarget,
    constraints: ConstraintBundle,
    evidence: EvidenceBundle,
    report: CompilationReport,
) -> str:
    """Return the canonical digest shared by assembly and deserialization validation."""

    payload = cast(
        JsonValue,
        {
            "compiler_version": compiler_version.model_dump(mode="json"),
            "compiled_at": compiled_at.isoformat(),
            "intent": intent.model_dump(mode="json"),
            "platform": platform.model_dump(mode="json"),
            "voice": voice.model_dump(mode="json"),
            "virality": virality.model_dump(mode="json"),
            "constraints": constraints.model_dump(mode="json"),
            "evidence": evidence.model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
        },
    )
    return sha256_text(dumps_json(payload))


def generation_context_id(content_hash: str) -> UUID:
    """Derive a stable UUID from one canonical generation-context digest."""

    return uuid5(NAMESPACE_URL, f"generation-context:{content_hash}")
