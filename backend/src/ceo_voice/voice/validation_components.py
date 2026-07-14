"""Component-graph pass for HVM structural validation."""

from uuid import UUID

from ceo_voice.voice.enums import ValidationCode
from ceo_voice.voice.evidence import EvidenceUnit
from ceo_voice.voice.observations import Observation
from ceo_voice.voice.validation_support import StructuralChecks
from ceo_voice.voice.validation_types import ReleaseValidationSubject


def validate_components(
    subject: ReleaseValidationSubject,
    evidence_by_id: dict[UUID, EvidenceUnit],
    observations_by_id: dict[UUID, Observation],
    checks: StructuralChecks,
) -> None:
    """Validate hierarchy, references, registry compatibility, and confidence shape."""

    components = subject.release.components
    aggregates_by_id = {aggregate.id: aggregate for aggregate in components.aggregates}
    residuals_by_id = {residual.id: residual for residual in components.residuals}
    interactions_by_id = {interaction.id: interaction for interaction in components.interactions}

    for aggregate in components.aggregates:
        path = f"components.aggregates.{aggregate.id}"
        definition = checks.validate_component_common(
            aggregate.feature,
            aggregate.value,
            aggregate.context,
            aggregate.confidence,
            aggregate.evidence_unit_ids,
            evidence_by_id,
            path,
        )
        if any(item not in observations_by_id for item in aggregate.observation_ids):
            checks.add(
                ValidationCode.REFERENCE_INTEGRITY,
                f"{path}.observation_ids",
                "aggregate references an unknown observation",
                (aggregate.id,),
            )
        if (
            definition is not None
            and aggregate.aggregation_strategy != definition.aggregation_strategy
        ):
            checks.add(
                ValidationCode.FEATURE_REGISTRY_CONSISTENCY,
                f"{path}.aggregation_strategy",
                "aggregate strategy differs from the feature definition",
                (aggregate.id,),
            )

    for residual in components.residuals:
        path = f"components.residuals.{residual.id}"
        checks.validate_component_common(
            residual.feature,
            residual.value,
            residual.context,
            residual.confidence,
            residual.evidence_unit_ids,
            evidence_by_id,
            path,
        )
        parent_aggregate = aggregates_by_id.get(residual.aggregate_id)
        if parent_aggregate is None or parent_aggregate.feature != residual.feature:
            checks.add(
                ValidationCode.REFERENCE_INTEGRITY,
                f"{path}.aggregate_id",
                "residual must reference an aggregate of the same feature",
                (residual.id, residual.aggregate_id),
            )

    for conditional in components.conditional_residuals:
        path = f"components.conditional_residuals.{conditional.id}"
        checks.validate_component_common(
            conditional.feature,
            conditional.delta,
            conditional.condition,
            conditional.confidence,
            conditional.evidence_unit_ids,
            evidence_by_id,
            path,
        )
        parent = residuals_by_id.get(conditional.parent_residual_id)
        if parent is None or parent.feature != conditional.feature:
            checks.add(
                ValidationCode.REFERENCE_INTEGRITY,
                f"{path}.parent_residual_id",
                "conditional residual must reference a core residual of the same feature",
                (conditional.id, conditional.parent_residual_id),
            )

    for interaction in components.interactions:
        path = f"components.interactions.{interaction.id}"
        for feature in interaction.features:
            checks.definition(feature, f"{path}.features")
        checks.validate_evidence_ids(interaction.evidence_unit_ids, evidence_by_id, path)
        checks.validate_confidence(interaction.confidence, len(interaction.evidence_unit_ids), path)

    for drift in components.drift_states:
        path = f"components.drift_states.{drift.id}"
        for feature in drift.features:
            checks.definition(feature, f"{path}.features")
        checks.validate_evidence_ids(drift.evidence_unit_ids, evidence_by_id, path)
        checks.validate_confidence(drift.confidence, len(drift.evidence_unit_ids), path)

    for prototype in subject.release.prototypes:
        path = f"prototypes.{prototype.id}"
        if prototype.evidence_unit_id not in evidence_by_id:
            checks.add(
                ValidationCode.REFERENCE_INTEGRITY,
                f"{path}.evidence_unit_id",
                "prototype references an unknown evidence unit",
                (prototype.id, prototype.evidence_unit_id),
            )
        for feature in prototype.represented_features:
            checks.definition(feature, f"{path}.represented_features")
        if any(item not in interactions_by_id for item in prototype.represented_interaction_ids):
            checks.add(
                ValidationCode.REFERENCE_INTEGRITY,
                f"{path}.represented_interaction_ids",
                "prototype references an unknown interaction",
                (prototype.id,),
            )

    for constraint in subject.release.negative_constraints:
        path = f"negative_constraints.{constraint.id}"
        definition = checks.definition(constraint.feature, f"{path}.feature")
        if (
            definition is not None
            and constraint.prohibited_value is not None
            and constraint.prohibited_value.kind is not definition.value_type
        ):
            checks.add(
                ValidationCode.FEATURE_REGISTRY_CONSISTENCY,
                f"{path}.prohibited_value",
                "constraint value type differs from its feature definition",
                (constraint.id,),
            )
        for link in constraint.evidence:
            if link.evidence_unit_id not in evidence_by_id:
                checks.add(
                    ValidationCode.REFERENCE_INTEGRITY,
                    f"{path}.evidence",
                    "constraint references an unknown evidence unit",
                    (constraint.id, link.evidence_unit_id),
                )

    for preference in subject.release.explicit_preferences:
        path = f"explicit_preferences.{preference.id}"
        definition = checks.definition(preference.feature, f"{path}.feature")
        if definition is not None and preference.target.kind is not definition.value_type:
            checks.add(
                ValidationCode.FEATURE_REGISTRY_CONSISTENCY,
                f"{path}.target",
                "preference target type differs from its feature definition",
                (preference.id,),
            )
