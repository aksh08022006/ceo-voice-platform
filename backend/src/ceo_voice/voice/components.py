"""Immutable aggregate, residual, interaction, preference, and constraint components."""

from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime
from ceo_voice.voice.enums import (
    ConstraintBasis,
    ConstraintSeverity,
    CopyRisk,
    DecisionState,
    DriftStatus,
    InteractionType,
    PreferenceAuthority,
    PrototypeKind,
)
from ceo_voice.voice.evidence import EvidenceReference
from ceo_voice.voice.features import AggregationStrategyReference
from ceo_voice.voice.primitives import (
    BaselineReference,
    FeatureReference,
    NonNegativeFloat,
    TimeRange,
    UnitInterval,
    VoiceContext,
)
from ceo_voice.voice.values import VoiceValue


def _require_unique(values: tuple[object, ...], *, field_name: str) -> None:
    """Raise a field-specific error for duplicate immutable references."""

    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must be unique")


class ConfidenceVector(ContractModel):
    """Complete, decomposed confidence state for one HVM component."""

    measurement_reliability: UnitInterval = Field(description="Producer repeatability/reliability.")
    attribution_reliability: UnitInterval = Field(description="Target-authorship reliability.")
    coverage: UnitInterval = Field(description="Share of eligible opportunities represented.")
    effective_support: NonNegativeFloat = Field(
        description="Effective support after dependence adjustments."
    )
    context_diversity: UnitInterval = Field(description="Breadth across governed context strata.")
    stability: UnitInterval = Field(description="Resampling and source-removal stability.")
    cross_context_robustness: UnitInterval = Field(
        description="Robustness to topic, time, and platform perturbation."
    )
    nuisance_robustness: UnitInterval = Field(
        description="Robustness to editor, modality, campaign, and entity controls."
    )
    distinctiveness: UnitInterval = Field(description="Practical difference from the baseline.")
    freshness: UnitInterval = Field(description="Relevance to the current time regime.")
    calibration: UnitInterval = Field(description="Empirical reliability of uncertainty values.")
    conflict: UnitInterval = Field(description="Mass of valid contradictory evidence.")
    evidence_count: int = Field(ge=0, description="Raw supporting evidence-unit count.")
    independent_cluster_count: int = Field(ge=0, description="Support after dependence grouping.")
    variance: NonNegativeFloat = Field(description="Estimator or sampling variance.")

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        """Keep effective and independent support bounded by raw evidence."""

        if self.independent_cluster_count > self.evidence_count:
            raise ValueError("independent clusters must not exceed evidence count")
        if self.effective_support > self.evidence_count:
            raise ValueError("effective support must not exceed evidence count")
        return self


class Aggregate(ContractModel):
    """Opportunity-aware aggregate derived from immutable observations."""

    id: UUID = Field(description="Stable aggregate identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Target writing identity.")
    feature: FeatureReference = Field(description="Exact aggregated feature definition.")
    context: VoiceContext = Field(description="Aggregate context key.")
    value: VoiceValue = Field(description="Typed aggregate value.")
    observation_ids: tuple[UUID, ...] = Field(
        min_length=1, description="Contributing observations."
    )
    evidence_unit_ids: tuple[UUID, ...] = Field(
        min_length=1, description="Addressable contributing evidence."
    )
    aggregation_strategy: AggregationStrategyReference = Field(
        description="Exact aggregation contract used."
    )
    confidence: ConfidenceVector = Field(description="Complete component uncertainty.")
    decision_state: DecisionState = Field(description="Maximum permitted downstream use.")
    created_at: UtcDatetime = Field(description="UTC aggregate creation time.")

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Reject duplicate observation or evidence contributions."""

        _require_unique(self.observation_ids, field_name="aggregate observation IDs")
        _require_unique(self.evidence_unit_ids, field_name="aggregate evidence-unit IDs")
        return self


class Residual(ContractModel):
    """Leader-specific deviation from an applicable versioned baseline."""

    id: UUID = Field(description="Stable residual identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Target writing identity.")
    feature: FeatureReference = Field(description="Exact residualized feature definition.")
    aggregate_id: UUID = Field(description="Aggregate from which the residual was estimated.")
    baseline: BaselineReference = Field(description="Applicable cohort/platform baseline.")
    context: VoiceContext = Field(description="Core language/register context.")
    value: VoiceValue = Field(description="Typed leader residual value.")
    evidence_unit_ids: tuple[UUID, ...] = Field(
        min_length=1, description="Evidence supporting the residual."
    )
    confidence: ConfidenceVector = Field(description="Complete residual uncertainty.")
    decision_state: DecisionState = Field(description="Maximum permitted downstream use.")
    created_at: UtcDatetime = Field(description="UTC residual creation time.")

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Require independent evidence references."""

        _require_unique(self.evidence_unit_ids, field_name="residual evidence-unit IDs")
        return self


class ConditionalResidual(ContractModel):
    """Context-specific delta that inherits from, rather than duplicates, a core residual."""

    id: UUID = Field(description="Stable conditional-residual identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Target writing identity.")
    feature: FeatureReference = Field(description="Exact conditioned feature definition.")
    parent_residual_id: UUID = Field(description="Inherited core residual.")
    condition: VoiceContext = Field(description="Platform/form/audience/mode/time condition.")
    delta: VoiceValue = Field(description="Typed conditional deviation from the parent.")
    transfer_confidence: UnitInterval = Field(
        description="Confidence that the parent transfers into this condition."
    )
    evidence_unit_ids: tuple[UUID, ...] = Field(
        min_length=1, description="Evidence supporting the conditional delta."
    )
    confidence: ConfidenceVector = Field(description="Complete conditional uncertainty.")
    decision_state: DecisionState = Field(description="Maximum permitted downstream use.")
    created_at: UtcDatetime = Field(description="UTC conditional-residual creation time.")

    @model_validator(mode="after")
    def validate_condition(self) -> Self:
        """Require a genuinely conditioned context and unique evidence."""

        if not self.condition.is_conditioned():
            raise ValueError("conditional residual requires a context beyond language")
        _require_unique(self.evidence_unit_ids, field_name="conditional residual evidence-unit IDs")
        return self


class Interaction(ContractModel):
    """Supported dependency among two or more marginal feature definitions."""

    id: UUID = Field(description="Stable interaction identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Target writing identity.")
    features: tuple[FeatureReference, ...] = Field(
        min_length=2, description="Marginal features participating in the relationship."
    )
    interaction_type: InteractionType = Field(description="Relationship semantics.")
    context: VoiceContext = Field(description="Context in which the interaction applies.")
    value: VoiceValue = Field(description="Typed interaction parameters or graph.")
    evidence_unit_ids: tuple[UUID, ...] = Field(
        min_length=1, description="Evidence supporting the interaction."
    )
    confidence: ConfidenceVector = Field(description="Complete interaction uncertainty.")
    decision_state: DecisionState = Field(description="Maximum permitted downstream use.")
    selection_policy_version: NonEmptyStr = Field(
        description="Versioned multiple-testing/selection contract."
    )
    created_at: UtcDatetime = Field(description="UTC interaction creation time.")

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Reject repeated marginals or evidence references."""

        _require_unique(self.features, field_name="interaction feature references")
        _require_unique(self.evidence_unit_ids, field_name="interaction evidence-unit IDs")
        return self


class Prototype(ContractModel):
    """Approved representative or boundary evidence for named HVM behavior."""

    id: UUID = Field(description="Stable prototype identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Target writing identity.")
    kind: PrototypeKind = Field(description="Representative or anti-prototype semantics.")
    evidence_unit_id: UUID = Field(description="Exact immutable evidence span.")
    represented_features: tuple[FeatureReference, ...] = Field(
        min_length=1, description="Feature behavior demonstrated by the span."
    )
    represented_interaction_ids: tuple[UUID, ...] = Field(
        default_factory=tuple, description="Interactions demonstrated by the span."
    )
    representativeness: UnitInterval = Field(description="Calibrated representativeness.")
    diversity_cluster_id: NonEmptyStr = Field(description="Retrieval diversity cluster.")
    copy_risk: CopyRisk = Field(description="Governed downstream copying risk.")
    approved_by: UUID = Field(description="Authorizing reviewer.")
    approved_at: UtcDatetime = Field(description="UTC approval time.")

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Reject duplicate represented features and interactions."""

        _require_unique(self.represented_features, field_name="prototype feature references")
        _require_unique(
            self.represented_interaction_ids, field_name="prototype interaction references"
        )
        return self


class NegativeConstraint(ContractModel):
    """Scoped statistical avoidance or explicit prohibition kept distinct from preference."""

    id: UUID = Field(description="Stable negative-constraint identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Target writing identity.")
    feature: FeatureReference = Field(description="Feature constrained.")
    basis: ConstraintBasis = Field(description="Statistical or explicit evidence semantics.")
    severity: ConstraintSeverity = Field(description="Enforcement strength.")
    scope: VoiceContext = Field(description="Context in which the constraint applies.")
    prohibited_value: VoiceValue | None = Field(
        default=None, description="Specific prohibited value when applicable."
    )
    frequency_ceiling: UnitInterval | None = Field(
        default=None, description="Maximum allowed occurrence probability."
    )
    authority: PreferenceAuthority | None = Field(
        default=None, description="Policy authority for explicit constraints."
    )
    actor_id: UUID | None = Field(default=None, description="Authorizing actor when explicit.")
    evidence: tuple[EvidenceReference, ...] = Field(
        default_factory=tuple, description="Evidence and opportunity links."
    )
    effective_range: TimeRange = Field(description="Effective policy or evidence interval.")

    @model_validator(mode="after")
    def validate_constraint(self) -> Self:
        """Keep explicit policy and statistical avoidance evidence semantics separate."""

        if self.prohibited_value is None and self.frequency_ceiling is None:
            raise ValueError("negative constraint requires a prohibited value or frequency ceiling")
        if self.basis is ConstraintBasis.EXPLICIT_POLICY:
            if self.authority is None or self.actor_id is None:
                raise ValueError("explicit constraints require authority and actor")
        elif self.authority is not None or self.actor_id is not None:
            raise ValueError("statistical constraints must not claim policy authority")
        if self.basis is ConstraintBasis.STATISTICAL_AVOIDANCE and not self.evidence:
            raise ValueError("statistical constraints require evidence and opportunities")
        links = tuple((item.evidence_unit_id, item.role) for item in self.evidence)
        _require_unique(links, field_name="negative-constraint evidence links")
        return self


class ExplicitPreference(ContractModel):
    """Human-authorized, scoped target that never masquerades as corpus frequency."""

    id: UUID = Field(description="Stable explicit-preference identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Target writing identity.")
    feature: FeatureReference = Field(description="Feature targeted by the preference.")
    target: VoiceValue = Field(description="Typed preferred value or range.")
    scope: VoiceContext = Field(description="Context in which the preference applies.")
    authority: PreferenceAuthority = Field(description="Authorizing role or policy.")
    priority: int = Field(ge=1, le=100, description="Conflict-resolution priority.")
    tolerance: NonNegativeFloat = Field(description="Permitted numeric deviation.")
    frequency_cap: UnitInterval | None = Field(
        default=None, description="Maximum frequency for a preferred behavior."
    )
    actor_id: UUID = Field(description="Authorizing actor.")
    rationale_category: NonEmptyStr = Field(description="Controlled rationale category.")
    effective_range: TimeRange = Field(description="Effective preference interval.")
    created_at: UtcDatetime = Field(description="UTC preference creation time.")


class DriftState(ContractModel):
    """Reviewable temporal-regime assertion produced by a future drift estimator."""

    id: UUID = Field(description="Stable drift-state identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Target writing identity.")
    features: tuple[FeatureReference, ...] = Field(
        min_length=1, description="Features implicated in the regime assertion."
    )
    status: DriftStatus = Field(description="Governed drift review state.")
    candidate_regime: NonEmptyStr = Field(description="Candidate temporal-regime identifier.")
    comparison_range: TimeRange = Field(description="Time interval being compared.")
    evidence_unit_ids: tuple[UUID, ...] = Field(
        min_length=1, description="Evidence supporting or refuting drift."
    )
    confidence: ConfidenceVector = Field(description="Complete drift uncertainty.")
    created_at: UtcDatetime = Field(description="UTC drift-state creation time.")

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Reject duplicate features or evidence references."""

        _require_unique(self.features, field_name="drift-state feature references")
        _require_unique(self.evidence_unit_ids, field_name="drift-state evidence-unit IDs")
        return self


class ProfileComponents(ContractModel):
    """Complete immutable component bundle passed between compilation stages."""

    aggregates: tuple[Aggregate, ...] = Field(default_factory=tuple)
    residuals: tuple[Residual, ...] = Field(default_factory=tuple)
    conditional_residuals: tuple[ConditionalResidual, ...] = Field(default_factory=tuple)
    interactions: tuple[Interaction, ...] = Field(default_factory=tuple)
    drift_states: tuple[DriftState, ...] = Field(default_factory=tuple)
