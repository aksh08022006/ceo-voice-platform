"""Deterministic construction helpers for HVM behavior tests."""

from datetime import UTC, datetime
from uuid import UUID

from ceo_voice.models.enums import DocumentSourceType, DocumentType, Platform
from ceo_voice.voice import (
    Aggregate,
    AggregationStrategyReference,
    BaselineReference,
    ConfidenceComponent,
    ConfidenceModelDefinition,
    ConfidenceVector,
    DecisionState,
    DownstreamPermission,
    EvidenceReference,
    EvidenceRequirements,
    EvidenceRole,
    EvidenceSnapshot,
    EvidenceUnit,
    EvidenceUnitType,
    EvidenceWeightComponents,
    FeatureDefinition,
    FeatureRegistry,
    FeatureValueType,
    HVMRelease,
    LanguageApplicability,
    MeasurementClass,
    Observation,
    ObservationState,
    PlatformApplicability,
    ProducerReference,
    ProducerType,
    ProfileComponents,
    ProfileLineage,
    Residual,
    ScalarValue,
    SemanticVersion,
    SourceModality,
    StructuralReleaseValidator,
    TargetIdentityType,
    ValidationReport,
    VoiceContext,
    VoiceDimension,
    VoiceIdentity,
)

NOW = datetime(2026, 7, 14, 0, 0, tzinfo=UTC)
TENANT_ID = UUID(int=1)
LEADER_ID = UUID(int=2)
IDENTITY_ID = UUID(int=3)
LINEAGE_ID = UUID(int=4)
REGISTRY_ID = UUID(int=5)
EVIDENCE_ID = UUID(int=6)
DOCUMENT_ID = UUID(int=7)
OBSERVATION_ID = UUID(int=8)
AGGREGATE_ID = UUID(int=9)
RESIDUAL_ID = UUID(int=10)
RELEASE_ID = UUID(int=11)
REPORT_ID = UUID(int=12)
BUILD_ID = UUID(int=13)
ACTOR_ID = UUID(int=14)


def semver(value: str = "1.0.0") -> SemanticVersion:
    """Return a parsed semantic version."""

    return SemanticVersion.parse(value)


def confidence(*, evidence_count: int = 1) -> ConfidenceVector:
    """Return a complete confidence vector with internally consistent counts."""

    return ConfidenceVector(
        measurement_reliability=0.9,
        attribution_reliability=0.9,
        coverage=0.8,
        effective_support=float(evidence_count),
        context_diversity=0.7,
        stability=0.8,
        cross_context_robustness=0.7,
        nuisance_robustness=0.8,
        distinctiveness=0.75,
        freshness=0.9,
        calibration=0.85,
        conflict=0.1,
        evidence_count=evidence_count,
        independent_cluster_count=evidence_count,
        variance=0.05,
    )


def feature_definition() -> FeatureDefinition:
    """Return one scalar lexical definition with complete registry metadata."""

    return FeatureDefinition(
        feature_id="lexical.function-word-rate",
        semantic_version=semver(),
        display_name="Function word rate",
        description="Opportunity-adjusted use of a registered function word.",
        dimension=VoiceDimension.LEXICAL,
        observation_scope=EvidenceUnitType.SENTENCE,
        opportunity_unit="token",
        measurement_pipeline=(MeasurementClass.DETERMINISTIC, MeasurementClass.STATISTICAL),
        supported_languages=LanguageApplicability(all_languages=False, languages=("en",)),
        supported_platforms=PlatformApplicability(
            all_platforms=False, platforms=(Platform.LINKEDIN,)
        ),
        supported_modalities=(SourceModality.AUTHORED_WRITTEN,),
        value_type=FeatureValueType.SCALAR,
        confidence_model=ConfidenceModelDefinition(
            model_id="confidence.complete-vector",
            version=semver(),
            required_components=tuple(ConfidenceComponent),
            calibration_required=True,
        ),
        aggregation_strategy=AggregationStrategyReference(
            strategy_id="aggregation.opportunity-rate",
            version=semver(),
            output_value_type=FeatureValueType.SCALAR,
        ),
        downstream_permissions=tuple(DownstreamPermission),
        evidence_requirements=EvidenceRequirements(
            minimum_evidence_units=1,
            minimum_independent_clusters=1,
            required_roles=(EvidenceRole.SUPPORT,),
            allowed_modalities=(SourceModality.AUTHORED_WRITTEN,),
            requires_target_attribution=True,
            requires_rights_admissibility=True,
        ),
        nuisance_controls=("topic", "campaign"),
        minimum_text_characters=5,
    )


def registry(*, definition: FeatureDefinition | None = None) -> FeatureRegistry:
    """Return a canonical one-definition registry."""

    return FeatureRegistry.build(
        registry_id=REGISTRY_ID,
        version=semver(),
        definitions=(definition or feature_definition(),),
        created_at=NOW,
    )


def identity() -> VoiceIdentity:
    """Return a governed personal-authorship identity."""

    return VoiceIdentity(
        id=IDENTITY_ID,
        tenant_id=TENANT_ID,
        leader_id=LEADER_ID,
        display_name="Example Leader",
        target_type=TargetIdentityType.PERSONAL_AUTHORSHIP,
        policy_version=semver(),
        created_at=NOW,
    )


def lineage() -> ProfileLineage:
    """Return the profile lineage for the test identity."""

    return ProfileLineage(
        id=LINEAGE_ID,
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        lineage_policy_version=semver(),
        created_at=NOW,
    )


def evidence_unit(*, evidence_id: UUID = EVIDENCE_ID) -> EvidenceUnit:
    """Return one immutable sentence-level evidence unit."""

    return EvidenceUnit(
        id=evidence_id,
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        document_id=DOCUMENT_ID,
        document_version=1,
        segmentation_version=semver(),
        unit_type=EvidenceUnitType.SENTENCE,
        start_offset=0,
        end_offset=20,
        span_checksum="a" * 64,
        structural_position="opening",
        language="en",
        source=DocumentSourceType.LINKEDIN,
        source_modality=SourceModality.AUTHORED_WRITTEN,
        document_type=DocumentType.SOCIAL_POST,
        platform=Platform.LINKEDIN,
        publication_time=NOW,
    )


def evidence_weights() -> EvidenceWeightComponents:
    """Return fully admissible decomposed evidence weights."""

    return EvidenceWeightComponents(
        target_attribution=1,
        speaker_attribution=1,
        source_reliability=1,
        modality_admissibility=1,
        observation_quality=1,
        independence=1,
        context_relevance=1,
        temporal_relevance=1,
        rights_admissible=True,
    )


def evidence_reference(
    *, role: EvidenceRole = EvidenceRole.SUPPORT, evidence_id: UUID = EVIDENCE_ID
) -> EvidenceReference:
    """Return one fully traceable observation evidence link."""

    return EvidenceReference(
        evidence_unit_id=evidence_id,
        role=role,
        weight_components=evidence_weights(),
        independence_cluster_id="cluster-1",
        opportunity_count=1,
    )


def context() -> VoiceContext:
    """Return the supported LinkedIn context."""

    return VoiceContext(
        language="en",
        platform=Platform.LINKEDIN,
        content_form=DocumentType.SOCIAL_POST,
    )


def observation(*, definition: FeatureDefinition | None = None) -> Observation:
    """Return one deterministic scalar observation."""

    selected = definition or feature_definition()
    return Observation(
        id=OBSERVATION_ID,
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        feature=selected.reference,
        context=context(),
        measurement_class=MeasurementClass.DETERMINISTIC,
        state=ObservationState.OBSERVED,
        value=ScalarValue(value=0.4, unit="per_token"),
        quality=0.95,
        evidence=(evidence_reference(),),
        producer=ProducerReference(
            producer_id="extractor.function-word",
            producer_type=ProducerType.DETERMINISTIC_SYSTEM,
            version=semver(),
            configuration_hash="b" * 64,
        ),
        event_time=NOW,
        created_at=NOW,
    )


def aggregate(*, definition: FeatureDefinition | None = None) -> Aggregate:
    """Return one structurally complete aggregate."""

    selected = definition or feature_definition()
    return Aggregate(
        id=AGGREGATE_ID,
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        feature=selected.reference,
        context=context(),
        value=ScalarValue(value=0.4, unit="per_token"),
        observation_ids=(OBSERVATION_ID,),
        evidence_unit_ids=(EVIDENCE_ID,),
        aggregation_strategy=selected.aggregation_strategy,
        confidence=confidence(),
        decision_state=DecisionState.ACTIONABLE_SOFT,
        created_at=NOW,
    )


def residual(*, definition: FeatureDefinition | None = None) -> Residual:
    """Return one baseline-relative leader residual."""

    selected = definition or feature_definition()
    return Residual(
        id=RESIDUAL_ID,
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        feature=selected.reference,
        aggregate_id=AGGREGATE_ID,
        baseline=BaselineReference(
            baseline_id=UUID(int=15),
            version=semver(),
            cohort_definition_hash="c" * 64,
        ),
        context=context(),
        value=ScalarValue(value=0.1, unit="residual"),
        evidence_unit_ids=(EVIDENCE_ID,),
        confidence=confidence(),
        decision_state=DecisionState.ACTIONABLE_SOFT,
        created_at=NOW,
    )


def evidence_snapshot(*, unit: EvidenceUnit | None = None) -> EvidenceSnapshot:
    """Return a canonical manifest for one evidence unit."""

    return EvidenceSnapshot.build(
        snapshot_id=UUID(int=16),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        evidence_units=(unit or evidence_unit(),),
        created_at=NOW,
    )


def release(
    *,
    feature: FeatureDefinition | None = None,
    release_id: UUID = RELEASE_ID,
    report_id: UUID = REPORT_ID,
    version: int = 1,
    previous_release_id: UUID | None = None,
) -> HVMRelease:
    """Return one minimal sealed HVM release."""

    selected = feature or feature_definition()
    return HVMRelease(
        id=release_id,
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        lineage_id=LINEAGE_ID,
        version=version,
        previous_release_id=previous_release_id,
        registry=registry(definition=selected).reference,
        evidence_snapshot=evidence_snapshot().reference,
        observation_references=(observation(definition=selected).reference,),
        components=ProfileComponents(
            aggregates=(aggregate(definition=selected),),
            residuals=(residual(definition=selected),),
        ),
        validation_report_id=report_id,
        compiler_version=semver(),
        created_at=NOW,
    )


def validation_report(
    *, release_value: HVMRelease | None = None, report_id: UUID = REPORT_ID
) -> ValidationReport:
    """Return a successful structural report for an exact release."""

    selected = release_value or release(report_id=report_id)
    return ValidationReport(
        id=report_id,
        release_id=selected.id,
        release_content_hash=selected.content_hash,
        validator_version=semver(),
        issues=(),
        validated_at=NOW,
    )


def structural_validator(
    *, feature_registry: FeatureRegistry | None = None
) -> StructuralReleaseValidator:
    """Return the production structural validator over a test registry."""

    return StructuralReleaseValidator(registry=feature_registry or registry(), version=semver())
