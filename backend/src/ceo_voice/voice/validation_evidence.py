"""Evidence and observation passes for HVM structural validation."""

from collections import defaultdict
from uuid import UUID

from ceo_voice.voice.enums import ObservationState, ValidationCode
from ceo_voice.voice.evidence import EvidenceReference, EvidenceUnit
from ceo_voice.voice.features import FeatureDefinition
from ceo_voice.voice.observations import Observation
from ceo_voice.voice.primitives import FeatureReference
from ceo_voice.voice.validation_support import StructuralChecks
from ceo_voice.voice.validation_types import ReleaseValidationSubject


def validate_evidence(
    subject: ReleaseValidationSubject, checks: StructuralChecks
) -> dict[UUID, EvidenceUnit]:
    """Validate evidence ownership and exact evidence-snapshot membership."""

    evidence_by_id = {unit.id: unit for unit in subject.evidence_units}
    if len(evidence_by_id) != len(subject.evidence_units):
        checks.add(
            ValidationCode.SCHEMA_INTEGRITY,
            "evidence_units",
            "evidence-unit IDs must be unique",
        )
    expected_member_by_id = {
        member.evidence_unit_id: member for member in subject.evidence_snapshot.members
    }
    if set(evidence_by_id) != set(expected_member_by_id):
        checks.add(
            ValidationCode.EVIDENCE_COMPLETENESS,
            "evidence_snapshot.members",
            "provided evidence units must exactly match manifest membership",
            tuple(
                sorted(set(evidence_by_id) ^ set(expected_member_by_id), key=lambda item: item.int)
            ),
        )
    for evidence_id, unit in evidence_by_id.items():
        if (
            unit.tenant_id != subject.release.tenant_id
            or unit.voice_identity_id != subject.release.voice_identity_id
        ):
            checks.add(
                ValidationCode.TENANT_IDENTITY_CONSISTENCY,
                f"evidence_units.{evidence_id}",
                "evidence unit tenant or identity does not match the release",
                (evidence_id,),
            )
        member = expected_member_by_id.get(evidence_id)
        if member is not None and unit.to_member() != member:
            checks.add(
                ValidationCode.REFERENCE_INTEGRITY,
                f"evidence_units.{evidence_id}",
                "evidence-unit immutable identity differs from the manifest",
                (evidence_id,),
            )
    return evidence_by_id


def validate_observations(
    subject: ReleaseValidationSubject,
    evidence_by_id: dict[UUID, EvidenceUnit],
    checks: StructuralChecks,
) -> dict[UUID, Observation]:
    """Validate observation ownership, content pinning, registry use, and evidence links."""

    observations_by_id = {observation.id: observation for observation in subject.observations}
    if len(observations_by_id) != len(subject.observations):
        checks.add(
            ValidationCode.SCHEMA_INTEGRITY,
            "observations",
            "observation IDs must be unique",
        )
    expected_by_id = {
        reference.observation_id: reference for reference in subject.release.observation_references
    }
    if set(observations_by_id) != set(expected_by_id):
        checks.add(
            ValidationCode.REFERENCE_INTEGRITY,
            "release.observation_references",
            "release observations must exactly match the validation bundle",
            tuple(sorted(set(observations_by_id) ^ set(expected_by_id), key=lambda item: item.int)),
        )
    for observation in subject.observations:
        path = f"observations.{observation.id}"
        expected = expected_by_id.get(observation.id)
        if expected is not None and observation.reference != expected:
            checks.add(
                ValidationCode.REFERENCE_INTEGRITY,
                path,
                "observation content differs from the release-pinned reference",
                (observation.id,),
            )
        if (
            observation.tenant_id != subject.release.tenant_id
            or observation.voice_identity_id != subject.release.voice_identity_id
        ):
            checks.add(
                ValidationCode.TENANT_IDENTITY_CONSISTENCY,
                path,
                "observation tenant or identity does not match the release",
                (observation.id,),
            )
        definition = checks.definition(observation.feature, path)
        if definition is not None:
            _validate_observation_definition(observation, definition, evidence_by_id, path, checks)
        for reference in observation.evidence:
            if reference.evidence_unit_id not in evidence_by_id:
                checks.add(
                    ValidationCode.REFERENCE_INTEGRITY,
                    f"{path}.evidence",
                    "observation references an unknown evidence unit",
                    (observation.id, reference.evidence_unit_id),
                )
    return observations_by_id


def _validate_observation_definition(
    observation: Observation,
    definition: FeatureDefinition,
    evidence_by_id: dict[UUID, EvidenceUnit],
    path: str,
    checks: StructuralChecks,
) -> None:
    """Validate one observation against its exact feature definition."""

    if observation.measurement_class not in definition.measurement_pipeline:
        checks.add(
            ValidationCode.FEATURE_REGISTRY_CONSISTENCY,
            f"{path}.measurement_class",
            "measurement class is not allowed by the feature definition",
            (observation.id,),
        )
    if observation.value is not None and observation.value.kind is not definition.value_type:
        checks.add(
            ValidationCode.FEATURE_REGISTRY_CONSISTENCY,
            f"{path}.value",
            "observation value type does not match the feature definition",
            (observation.id,),
        )
    checks.validate_context(definition, observation.context, path)
    for reference in observation.evidence:
        unit = evidence_by_id.get(reference.evidence_unit_id)
        if unit is None:
            continue
        if (
            unit.source_modality not in definition.supported_modalities
            or unit.source_modality not in definition.evidence_requirements.allowed_modalities
        ):
            checks.add(
                ValidationCode.FEATURE_REGISTRY_CONSISTENCY,
                f"{path}.evidence",
                "evidence modality is unsupported or inadmissible for the feature",
                (observation.id, unit.id),
            )
        if unit.end_offset - unit.start_offset < definition.minimum_text_characters:
            checks.add(
                ValidationCode.EVIDENCE_COMPLETENESS,
                f"{path}.evidence",
                "evidence unit is shorter than the feature minimum",
                (observation.id, unit.id),
            )


def validate_evidence_requirements(
    observations: tuple[Observation, ...],
    evidence_by_id: dict[UUID, EvidenceUnit],
    checks: StructuralChecks,
) -> None:
    """Validate feature-level evidence sufficiency and admissibility gates."""

    links_by_feature: dict[FeatureReference, list[EvidenceReference]] = defaultdict(list)
    for observation in observations:
        if observation.state is ObservationState.OBSERVED:
            links_by_feature[observation.feature].extend(observation.evidence)
    for reference, links in links_by_feature.items():
        definition = checks.definition(reference, f"features.{reference.feature_id}")
        if definition is None:
            continue
        requirements = definition.evidence_requirements
        evidence_ids = {
            link.evidence_unit_id for link in links if link.evidence_unit_id in evidence_by_id
        }
        clusters = {link.independence_cluster_id for link in links}
        roles = {link.role for link in links}
        path = f"features.{reference.feature_id}@{reference.version}.evidence"
        if len(evidence_ids) < requirements.minimum_evidence_units:
            checks.add(
                ValidationCode.EVIDENCE_COMPLETENESS,
                path,
                "feature does not meet its minimum evidence-unit requirement",
                tuple(sorted(evidence_ids, key=lambda item: item.int)),
            )
        if len(clusters) < requirements.minimum_independent_clusters:
            checks.add(
                ValidationCode.EVIDENCE_COMPLETENESS,
                path,
                "feature does not meet its independent-cluster requirement",
            )
        if not set(requirements.required_roles).issubset(roles):
            checks.add(
                ValidationCode.EVIDENCE_COMPLETENESS,
                path,
                "feature is missing one or more required evidence roles",
            )
        if requirements.requires_target_attribution and any(
            link.weight_components.target_attribution == 0 for link in links
        ):
            checks.add(
                ValidationCode.EVIDENCE_COMPLETENESS,
                path,
                "feature includes evidence with no target attribution support",
            )
        if requirements.requires_rights_admissibility and any(
            not link.weight_components.rights_admissible for link in links
        ):
            checks.add(
                ValidationCode.EVIDENCE_COMPLETENESS,
                path,
                "feature includes evidence that is not rights-admissible",
            )
