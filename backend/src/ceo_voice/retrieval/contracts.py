"""Immutable input, output, budget, explanation, and sealing contracts for retrieval."""

from datetime import datetime
from typing import Self, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, JsonValue, model_validator

from ceo_voice.context import (
    CompiledVoiceFeature,
    ConstraintBundle,
    GenerationContext,
    GenerationIntent,
    PlatformContract,
    StructuralGuidance,
)
from ceo_voice.models.base import ContractModel, NonBlankText, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import Platform
from ceo_voice.profiles import PublishedVoiceProfile
from ceo_voice.retrieval.enums import (
    EvidencePurpose,
    EvidenceSourceKind,
    KnowledgeKind,
    RetrievalPruneReason,
)
from ceo_voice.retrieval.ranking_contracts import RetrievalRankingInput, RetrievalRankingReport
from ceo_voice.schemas.generation import GenerationRequest
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.utils.json import dumps_json
from ceo_voice.virality import ViralityProfile
from ceo_voice.voice import DecisionState


class RetrievalEngineVersion(ContractModel):
    """Domain-local version of deterministic selection and budgeting behavior."""

    major: int = Field(ge=0)
    minor: int = Field(ge=0)
    patch: int = Field(ge=0)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class RetrievalBudget(ContractModel):
    """Hard information-density limits applied to materialized evidence."""

    maximum_evidence_items: int = Field(default=24, ge=1, le=200)
    maximum_evidence_characters: int = Field(default=12_000, ge=1, le=200_000)
    maximum_representative_examples: int = Field(default=4, ge=0, le=50)
    maximum_items_per_requirement: int = Field(default=2, ge=1, le=10)
    minimum_voice_evidence_per_feature: int = Field(default=1, ge=1, le=5)
    minimum_structural_evidence_per_pattern: int = Field(default=1, ge=1, le=5)

    @model_validator(mode="after")
    def validate_minima(self) -> Self:
        if self.maximum_items_per_requirement < max(
            self.minimum_voice_evidence_per_feature,
            self.minimum_structural_evidence_per_pattern,
        ):
            raise ValueError("per-requirement maximum must accommodate evidence minima")
        return self


class RetrievalPolicy(ContractModel):
    """Versioned deterministic ranking and admissibility policy."""

    version: RetrievalEngineVersion = RetrievalEngineVersion(major=1, minor=0, patch=1)
    freshness_horizon_days: int = Field(default=730, ge=1)
    minimum_observation_quality: float = Field(default=0.5, ge=0, le=1)
    diversity_bonus: float = Field(default=0.05, ge=0, le=0.25)
    repeated_document_penalty: float = Field(default=0.08, ge=0, le=0.5)


class RetrievalInput(ContractModel):
    """Pinned knowledge and intent required for one retrieval operation."""

    request: GenerationRequest
    context: GenerationContext
    voice_profile: PublishedVoiceProfile
    virality_profile: ViralityProfile
    budget: RetrievalBudget = RetrievalBudget()
    retrieved_at: UtcDatetime
    ranking: RetrievalRankingInput | None = None


class EvidenceMaterial(ContractModel):
    """A bounded immutable evidence span resolved without loading a raw document."""

    evidence_id: UUID
    tenant_id: UUID
    document_id: UUID
    document_version: int = Field(ge=1)
    content: NonBlankText
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    source_kind: EvidenceSourceKind
    platform: Platform | None
    publication_time: UtcDatetime | None
    diversity_cluster_id: NonEmptyStr

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        if sha256_text(self.content) != self.content_hash:
            raise ValueError("evidence material content does not match its hash")
        return self


class RetrievalScore(ContractModel):
    """Decomposed deterministic ranking factors for one evidence item."""

    confidence: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    freshness: float = Field(ge=0, le=1)
    platform_match: float = Field(ge=0, le=1)
    feature_importance: float = Field(ge=0, le=1)
    representativeness: float = Field(ge=0, le=1)
    profile_authority: float = Field(ge=0, le=1)
    intent_match: float = Field(ge=0, le=1)
    base_score: float = Field(ge=0, le=1)
    diversity_adjustment: float = Field(default=0, ge=-0.5, le=0.5)
    final_score: float = Field(ge=0, le=1)


class SelectionExplanation(ContractModel):
    """Human- and machine-readable justification for one selected span."""

    reason: NonEmptyStr
    generation_use: NonEmptyStr
    requirements: tuple[NonEmptyStr, ...] = Field(min_length=1)
    supporting_feature_ids: tuple[NonEmptyStr, ...] = ()
    supporting_pattern_ids: tuple[UUID, ...] = ()
    source_artifact_ids: tuple[UUID, ...] = Field(min_length=1)


class RetrievedEvidence(ContractModel):
    """One ranked, explainable, bounded span in the final retrieval bundle."""

    evidence_id: UUID
    document_id: UUID
    content: NonBlankText
    content_hash: NonEmptyStr
    source_kind: EvidenceSourceKind
    platform: Platform | None
    publication_time: UtcDatetime | None
    diversity_cluster_id: NonEmptyStr
    purposes: tuple[EvidencePurpose, ...] = Field(min_length=1)
    rank: int = Field(ge=1)
    priority: int = Field(ge=1, le=100)
    score: RetrievalScore
    explanation: SelectionExplanation


class ObservationSummary(ContractModel):
    """High-confidence observation selected to explain one compiled feature."""

    observation_id: UUID
    feature_id: NonEmptyStr
    value: JsonValue
    quality: float = Field(ge=0, le=1)
    measurement_class: NonEmptyStr
    event_time: UtcDatetime
    evidence_ids: tuple[UUID, ...]
    selection_reason: NonEmptyStr


class AggregateSummary(ContractModel):
    """Applicable HVM aggregate retained without exposing the entire profile."""

    aggregate_id: UUID
    feature_id: NonEmptyStr
    value: JsonValue
    platform: Platform | None
    decision_state: DecisionState
    coverage: float = Field(ge=0, le=1)
    effective_support: float = Field(ge=0)
    evidence_ids: tuple[UUID, ...]


class PreferenceSummary(ContractModel):
    """Explicit preference that actually governed a compiled voice feature."""

    preference_id: UUID
    feature_id: NonEmptyStr
    target: JsonValue
    priority: int = Field(ge=1, le=100)
    authority: NonEmptyStr
    rationale_category: NonEmptyStr


class PrunedCandidate(ContractModel):
    """Explain why a relevant evidence candidate was omitted."""

    evidence_id: UUID
    reason: RetrievalPruneReason
    base_score: float = Field(ge=0, le=1)
    requirements: tuple[NonEmptyStr, ...]


class RequirementCoverage(ContractModel):
    """Selected evidence satisfying one mandatory generation requirement."""

    requirement: NonEmptyStr
    kind: KnowledgeKind
    selected_evidence_ids: tuple[UUID, ...] = Field(min_length=1)


class RetrievalTrace(ContractModel):
    """Reference from the bundle back to one immutable governed artifact."""

    kind: KnowledgeKind
    identifier: UUID
    parent_identifier: UUID | None = None


class RetrievalReport(ContractModel):
    """Coverage, pruning, confidence, and provenance for retrieval decisions."""

    coverage: tuple[RequirementCoverage, ...]
    pruned: tuple[PrunedCandidate, ...]
    traceability: tuple[RetrievalTrace, ...]
    minimum_selected_score: float = Field(ge=0, le=1)
    mean_selected_score: float = Field(ge=0, le=1)
    distinct_documents: int = Field(ge=1)
    distinct_diversity_clusters: int = Field(ge=1)


class RetrievalMetadata(ContractModel):
    """Reproducibility and budget accounting for one engine execution."""

    engine_version: RetrievalEngineVersion
    retrieved_at: UtcDatetime
    candidates_considered: int = Field(ge=1)
    evidence_items_selected: int = Field(ge=1)
    evidence_items_pruned: int = Field(ge=0)
    evidence_characters_used: int = Field(ge=1)
    representative_examples_selected: int = Field(ge=0)
    budget: RetrievalBudget
    deterministic: bool = True
    semantic_ranking_used: bool = False
    # Omit absent diagnostics so previously sealed baseline bundles remain readable.
    ranking_report: RetrievalRankingReport | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class RetrievalBundle(ContractModel):
    """Only knowledge-serving object a future prompt builder may consume."""

    bundle_id: UUID
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    source_context_id: UUID
    source_context_hash: NonEmptyStr
    intent: GenerationIntent
    platform: PlatformContract
    voice_features: tuple[CompiledVoiceFeature, ...] = Field(min_length=1)
    structural_guidance: tuple[StructuralGuidance, ...] = Field(min_length=1)
    constraints: ConstraintBundle
    observations: tuple[ObservationSummary, ...] = Field(min_length=1)
    aggregates: tuple[AggregateSummary, ...] = Field(min_length=1)
    preferences: tuple[PreferenceSummary, ...]
    evidence: tuple[RetrievedEvidence, ...] = Field(min_length=1)
    report: RetrievalReport
    metadata: RetrievalMetadata

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        ranks = tuple(item.rank for item in self.evidence)
        if ranks != tuple(range(1, len(self.evidence) + 1)):
            raise ValueError("retrieval evidence ranks must be contiguous from one")
        if self.metadata.evidence_items_selected != len(self.evidence):
            raise ValueError("retrieval metadata item count does not match evidence")
        if self.metadata.evidence_characters_used != sum(
            len(item.content) for item in self.evidence
        ):
            raise ValueError("retrieval metadata character count does not match evidence")
        expected_hash = compute_retrieval_bundle_hash(self)
        if self.content_hash != expected_hash:
            raise ValueError("retrieval bundle content hash does not match its payload")
        if self.bundle_id != retrieval_bundle_id(expected_hash):
            raise ValueError("retrieval bundle ID does not match its content hash")
        return self


def compute_retrieval_bundle_hash(bundle: RetrievalBundle) -> str:
    """Hash every field except the derived ID and digest."""

    payload = cast(
        JsonValue,
        bundle.model_dump(mode="json", exclude={"bundle_id", "content_hash"}),
    )
    return sha256_text(dumps_json(payload))


def retrieval_bundle_id(content_hash: str) -> UUID:
    """Derive the stable retrieval-bundle identifier from its digest."""

    return uuid5(NAMESPACE_URL, f"retrieval-bundle:{content_hash}")


def freshness_score(
    publication_time: datetime | None, *, now: datetime, horizon_days: int
) -> float:
    """Return a deterministic linear freshness score with an explicit missing-time prior."""

    if publication_time is None:
        return 0.5
    age_days = max(0.0, (now - publication_time).total_seconds() / 86_400)
    return round(max(0.0, 1 - age_days / horizon_days), 6)
