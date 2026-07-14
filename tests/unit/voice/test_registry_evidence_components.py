"""Behavior tests for registry, evidence, observations, and HVM components."""

from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.core.exceptions import FeatureRegistryError
from ceo_voice.voice import (
    Aggregate,
    AggregationStrategyReference,
    ConditionalResidual,
    ConfidenceModelDefinition,
    ConfidenceVector,
    ConstraintBasis,
    ConstraintSeverity,
    CopyRisk,
    DecisionState,
    DriftState,
    DriftStatus,
    EvidenceReference,
    EvidenceRequirements,
    EvidenceRole,
    EvidenceSnapshot,
    EvidenceUnit,
    ExplicitPreference,
    FeatureDefinition,
    FeatureRegistry,
    FeatureValueType,
    Interaction,
    InteractionType,
    IntervalValue,
    MeasurementClass,
    NegativeConstraint,
    Observation,
    ObservationState,
    PreferenceAuthority,
    ProducerReference,
    ProducerType,
    ProfileComponents,
    Prototype,
    PrototypeKind,
    ScalarValue,
    SemanticVersion,
    SourceModality,
    TimeRange,
    VoiceContext,
    VoiceDimension,
)
from tests.unit.voice.factories import (
    ACTOR_ID,
    EVIDENCE_ID,
    IDENTITY_ID,
    NOW,
    OBSERVATION_ID,
    RESIDUAL_ID,
    TENANT_ID,
    aggregate,
    confidence,
    context,
    evidence_reference,
    evidence_snapshot,
    evidence_unit,
    feature_definition,
    observation,
    registry,
    residual,
    semver,
)


def test_feature_definition_is_complete_and_serializable() -> None:
    definition = feature_definition()

    assert definition.reference.feature_id == "lexical.function-word-rate"
    assert FeatureDefinition.model_validate_json(definition.model_dump_json()) == definition
    with pytest.raises(ValidationError):
        definition.__setattr__("display_name", "Changed")


def test_feature_definition_rejects_incompatible_contracts() -> None:
    definition = feature_definition()

    with pytest.raises(ValidationError, match="output type"):
        FeatureDefinition.model_validate(
            {
                **definition.model_dump(),
                "aggregation_strategy": AggregationStrategyReference(
                    strategy_id="wrong",
                    version=semver(),
                    output_value_type=FeatureValueType.INTERVAL,
                ),
            }
        )
    with pytest.raises(ValidationError, match="measurement pipeline"):
        FeatureDefinition.model_validate(
            {
                **definition.model_dump(),
                "measurement_pipeline": (
                    MeasurementClass.DETERMINISTIC,
                    MeasurementClass.DETERMINISTIC,
                ),
            }
        )
    with pytest.raises(ValidationError, match="unsupported modalities"):
        FeatureDefinition.model_validate(
            {
                **definition.model_dump(),
                "evidence_requirements": EvidenceRequirements(
                    minimum_evidence_units=1,
                    minimum_independent_clusters=1,
                    required_roles=(EvidenceRole.SUPPORT,),
                    allowed_modalities=(SourceModality.PREPARED_SPOKEN,),
                    requires_target_attribution=True,
                    requires_rights_admissibility=True,
                ),
            }
        )


def test_confidence_and_evidence_requirements_reject_inconsistent_counts() -> None:
    with pytest.raises(ValidationError, match="must not exceed"):
        ConfidenceVector(**{**confidence().model_dump(), "independent_cluster_count": 2})
    with pytest.raises(ValidationError, match="cannot exceed"):
        EvidenceRequirements(
            minimum_evidence_units=1,
            minimum_independent_clusters=2,
            required_roles=(EvidenceRole.SUPPORT,),
            allowed_modalities=(SourceModality.AUTHORED_WRITTEN,),
            requires_target_attribution=True,
            requires_rights_admissibility=True,
        )
    with pytest.raises(ValidationError, match="must be unique"):
        ConfidenceModelDefinition(
            model_id="confidence",
            version=semver(),
            required_components=(
                feature_definition().confidence_model.required_components[0],
                feature_definition().confidence_model.required_components[0],
            ),
            calibration_required=True,
        )


def test_registry_resolves_exact_latest_dimension_and_evolves_immutably() -> None:
    version_one = feature_definition()
    version_two = FeatureDefinition.model_validate(
        {**version_one.model_dump(), "semantic_version": SemanticVersion.parse("1.1.0")}
    )
    feature_registry = FeatureRegistry.build(
        registry_id=registry().id,
        version=SemanticVersion.parse("2.0.0"),
        definitions=(version_two, version_one),
        created_at=NOW,
    )

    assert feature_registry.get(version_one.reference) == version_one
    assert feature_registry.resolve_latest(version_one.feature_id) == version_two
    assert feature_registry.contains(version_two.reference)
    assert feature_registry.for_dimension(VoiceDimension.LEXICAL) == (version_one, version_two)
    assert len(feature_registry.snapshot_hash) == 64
    assert feature_registry.reference.snapshot_hash == feature_registry.snapshot_hash

    evolved = feature_registry.evolve(
        version=SemanticVersion.parse("2.1.0"),
        definitions=feature_registry.definitions,
        created_at=NOW + timedelta(seconds=1),
    )
    assert evolved.id == feature_registry.id
    assert evolved.version == SemanticVersion.parse("2.1.0")
    assert feature_registry.version == SemanticVersion.parse("2.0.0")


def test_registry_rejects_missing_noncanonical_and_nonincreasing_versions() -> None:
    definition = feature_definition()
    feature_registry = registry()

    with pytest.raises(FeatureRegistryError, match="not found"):
        feature_registry.resolve_latest("lexical.unknown-rate")
    with pytest.raises(FeatureRegistryError, match="not found"):
        feature_registry.get(
            definition.reference.model_copy(update={"version": SemanticVersion.parse("9.0.0")})
        )
    with pytest.raises(FeatureRegistryError, match="must increase"):
        feature_registry.evolve(
            version=feature_registry.version,
            definitions=feature_registry.definitions,
            created_at=NOW,
        )

    version_two = FeatureDefinition.model_validate(
        {**definition.model_dump(), "semantic_version": SemanticVersion.parse("1.1.0")}
    )
    with pytest.raises(ValidationError, match="canonical"):
        FeatureRegistry(
            id=feature_registry.id,
            version=SemanticVersion.parse("2.0.0"),
            definitions=(version_two, definition),
            created_at=NOW,
        )


def test_evidence_unit_snapshot_and_reference_are_content_addressed() -> None:
    unit = evidence_unit()
    snapshot = evidence_snapshot(unit=unit)

    assert snapshot.members == (unit.to_member(),)
    assert snapshot.members[0].unit_content_hash == unit.content_hash
    assert snapshot.reference.snapshot_hash == snapshot.snapshot_hash
    assert EvidenceSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
    with pytest.raises(ValidationError, match="greater than"):
        EvidenceUnit.model_validate({**unit.model_dump(), "end_offset": 0})
    with pytest.raises(ValueError, match="share the snapshot tenant"):
        EvidenceSnapshot.build(
            snapshot_id=UUID(int=100),
            tenant_id=UUID(int=999),
            voice_identity_id=IDENTITY_ID,
            evidence_units=(unit,),
            created_at=NOW,
        )
    with pytest.raises(ValueError, match="at least one"):
        EvidenceSnapshot.build(
            snapshot_id=UUID(int=100),
            tenant_id=TENANT_ID,
            voice_identity_id=IDENTITY_ID,
            evidence_units=(),
            created_at=NOW,
        )


def test_evidence_reference_requires_opportunity_and_observation_requires_traceability() -> None:
    with pytest.raises(ValidationError, match="positive opportunity"):
        EvidenceReference.model_validate(
            {
                **evidence_reference(role=EvidenceRole.OPPORTUNITY).model_dump(),
                "opportunity_count": 0,
            }
        )
    observed = observation()
    assert Observation.model_validate_json(observed.model_dump_json()) == observed
    with pytest.raises(ValidationError, match="require a typed value"):
        Observation.model_validate({**observed.model_dump(), "value": None})
    with pytest.raises(ValidationError, match="must not contain"):
        Observation.model_validate({**observed.model_dump(), "state": ObservationState.ABSTAINED})
    with pytest.raises(ValidationError, match="producer type"):
        Observation.model_validate(
            {
                **observed.model_dump(),
                "producer": ProducerReference(
                    producer_id="wrong",
                    producer_type=ProducerType.LLM_ANNOTATOR,
                    version=semver(),
                    configuration_hash="d" * 64,
                ),
            }
        )


def test_human_observation_requires_actor_and_evidence_links_are_unique() -> None:
    observed = observation()
    human_producer = ProducerReference(
        producer_id="rubric.voice",
        producer_type=ProducerType.HUMAN_REVIEWER,
        version=semver(),
        configuration_hash="e" * 64,
        actor_id=ACTOR_ID,
    )
    human = Observation.model_validate(
        {
            **observed.model_dump(),
            "measurement_class": MeasurementClass.HUMAN_ANNOTATED,
            "producer": human_producer,
        }
    )
    assert human.producer.actor_id == ACTOR_ID
    with pytest.raises(ValidationError, match="actor identifier"):
        Observation.model_validate(
            {
                **human.model_dump(),
                "producer": human_producer.model_copy(update={"actor_id": None}),
            }
        )
    with pytest.raises(ValidationError, match="unique by unit and role"):
        Observation.model_validate({**observed.model_dump(), "evidence": observed.evidence * 2})


def test_core_components_reject_duplicate_and_unconditioned_references() -> None:
    base_aggregate = aggregate()
    with pytest.raises(ValidationError, match="observation IDs"):
        Aggregate.model_validate(
            {
                **base_aggregate.model_dump(),
                "observation_ids": (OBSERVATION_ID, OBSERVATION_ID),
            }
        )
    with pytest.raises(ValidationError, match="context beyond language"):
        ConditionalResidual(
            id=UUID(int=20),
            tenant_id=TENANT_ID,
            voice_identity_id=IDENTITY_ID,
            feature=feature_definition().reference,
            parent_residual_id=RESIDUAL_ID,
            condition=VoiceContext(language="en"),
            delta=ScalarValue(value=0.1, unit="residual"),
            transfer_confidence=0.8,
            evidence_unit_ids=(EVIDENCE_ID,),
            confidence=confidence(),
            decision_state=DecisionState.DESCRIPTIVE,
            created_at=NOW,
        )


def test_interaction_prototype_drift_and_profile_component_serialization() -> None:
    feature = feature_definition().reference
    other = feature.model_copy(update={"feature_id": "rhythmic.sentence-length-rate"})
    interaction = Interaction(
        id=UUID(int=21),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        features=(feature, other),
        interaction_type=InteractionType.CROSS_LAYER,
        context=context(),
        value=ScalarValue(value=0.3, unit="association"),
        evidence_unit_ids=(EVIDENCE_ID,),
        confidence=confidence(),
        decision_state=DecisionState.EXPLORATORY,
        selection_policy_version="selection-1",
        created_at=NOW,
    )
    prototype = Prototype(
        id=UUID(int=22),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        kind=PrototypeKind.PROTOTYPE,
        evidence_unit_id=EVIDENCE_ID,
        represented_features=(feature,),
        represented_interaction_ids=(interaction.id,),
        representativeness=0.9,
        diversity_cluster_id="prototype-cluster",
        copy_risk=CopyRisk.LOW,
        approved_by=ACTOR_ID,
        approved_at=NOW,
    )
    drift = DriftState(
        id=UUID(int=23),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        features=(feature,),
        status=DriftStatus.CANDIDATE,
        candidate_regime="post-2026",
        comparison_range=TimeRange(starts_at=NOW, ends_at=NOW + timedelta(days=1)),
        evidence_unit_ids=(EVIDENCE_ID,),
        confidence=confidence(),
        created_at=NOW,
    )
    components = ProfileComponents(
        aggregates=(aggregate(),),
        residuals=(residual(),),
        interactions=(interaction,),
        drift_states=(drift,),
    )

    assert prototype.represented_interaction_ids == (interaction.id,)
    assert ProfileComponents.model_validate_json(components.model_dump_json()) == components
    with pytest.raises(ValidationError, match="interaction feature references"):
        Interaction.model_validate({**interaction.model_dump(), "features": (feature, feature)})


def test_negative_constraints_keep_statistical_and_explicit_semantics_separate() -> None:
    statistical = NegativeConstraint(
        id=UUID(int=24),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        feature=feature_definition().reference,
        basis=ConstraintBasis.STATISTICAL_AVOIDANCE,
        severity=ConstraintSeverity.SOFT,
        scope=context(),
        frequency_ceiling=0.1,
        evidence=(evidence_reference(role=EvidenceRole.OPPORTUNITY),),
        effective_range=TimeRange(starts_at=NOW),
    )
    explicit = NegativeConstraint(
        id=UUID(int=25),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        feature=feature_definition().reference,
        basis=ConstraintBasis.EXPLICIT_POLICY,
        severity=ConstraintSeverity.HARD,
        scope=context(),
        prohibited_value=ScalarValue(value=1, unit="presence"),
        authority=PreferenceAuthority.TARGET_LEADER,
        actor_id=ACTOR_ID,
        effective_range=TimeRange(starts_at=NOW),
    )

    assert statistical.evidence[0].role is EvidenceRole.OPPORTUNITY
    assert explicit.authority is PreferenceAuthority.TARGET_LEADER
    with pytest.raises(ValidationError, match="require evidence"):
        NegativeConstraint.model_validate({**statistical.model_dump(), "evidence": ()})
    with pytest.raises(ValidationError, match="require authority"):
        NegativeConstraint.model_validate(
            {**explicit.model_dump(), "authority": None, "actor_id": None}
        )
    with pytest.raises(ValidationError, match="requires a prohibited value"):
        NegativeConstraint.model_validate(
            {
                **explicit.model_dump(),
                "prohibited_value": None,
                "frequency_ceiling": None,
            }
        )


def test_explicit_preference_is_typed_scoped_and_immutable() -> None:
    preference = ExplicitPreference(
        id=UUID(int=26),
        tenant_id=TENANT_ID,
        voice_identity_id=IDENTITY_ID,
        feature=feature_definition().reference,
        target=IntervalValue(
            lower=0.1,
            upper=0.4,
            lower_inclusive=True,
            upper_inclusive=True,
            unit="rate",
        ),
        scope=context(),
        authority=PreferenceAuthority.TARGET_LEADER,
        priority=90,
        tolerance=0.05,
        frequency_cap=0.5,
        actor_id=ACTOR_ID,
        rationale_category="authenticity",
        effective_range=TimeRange(starts_at=NOW),
        created_at=NOW,
    )

    assert preference.priority == 90
    with pytest.raises(ValidationError):
        preference.__setattr__("priority", 1)
