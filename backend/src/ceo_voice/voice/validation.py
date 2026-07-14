"""Deterministic orchestration for complete HVM structural validation."""

from uuid import UUID

from ceo_voice.models.base import UtcDatetime
from ceo_voice.voice.enums import ValidationCode
from ceo_voice.voice.ports import FeatureRegistryReader
from ceo_voice.voice.primitives import SemanticVersion
from ceo_voice.voice.releases import ValidationReport
from ceo_voice.voice.validation_components import validate_components
from ceo_voice.voice.validation_evidence import (
    validate_evidence,
    validate_evidence_requirements,
    validate_observations,
)
from ceo_voice.voice.validation_support import StructuralChecks
from ceo_voice.voice.validation_types import ReleaseValidationSubject


class StructuralReleaseValidator:
    """Validate HVM references, versions, ownership, registry use, and confidence shape.

    This validator performs no stylometry, thresholds, statistics, or quality heuristics. It is
    deterministic for one subject and injected registry snapshot.
    """

    def __init__(self, *, registry: FeatureRegistryReader, version: SemanticVersion) -> None:
        self._registry = registry
        self._version = version

    @property
    def version(self) -> SemanticVersion:
        """Return the exact validator contract version."""

        return self._version

    def validate(
        self,
        subject: ReleaseValidationSubject,
        *,
        report_id: UUID,
        validated_at: UtcDatetime,
    ) -> ValidationReport:
        """Return all structural findings in deterministic path/code order."""

        checks = StructuralChecks(registry=self._registry)
        self._validate_ownership(subject, checks)
        self._validate_versions(subject, checks)
        evidence_by_id = validate_evidence(subject, checks)
        observations_by_id = validate_observations(subject, evidence_by_id, checks)
        validate_evidence_requirements(subject.observations, evidence_by_id, checks)
        validate_components(subject, evidence_by_id, observations_by_id, checks)
        ordered = tuple(
            sorted(checks.issues, key=lambda item: (item.path, item.code, item.message))
        )
        return ValidationReport(
            id=report_id,
            release_id=subject.release.id,
            release_content_hash=subject.release.content_hash,
            validator_version=self.version,
            issues=ordered,
            validated_at=validated_at,
        )

    @staticmethod
    def _validate_ownership(subject: ReleaseValidationSubject, checks: StructuralChecks) -> None:
        release = subject.release
        expected_tenant = release.tenant_id
        expected_identity = release.voice_identity_id
        ownership = (
            ("identity", subject.identity.tenant_id, subject.identity.id),
            ("lineage", subject.lineage.tenant_id, subject.lineage.voice_identity_id),
            (
                "evidence_snapshot",
                subject.evidence_snapshot.tenant_id,
                subject.evidence_snapshot.voice_identity_id,
            ),
        )
        for path, tenant_id, identity_id in ownership:
            if tenant_id != expected_tenant or identity_id != expected_identity:
                checks.add(
                    ValidationCode.TENANT_IDENTITY_CONSISTENCY,
                    path,
                    "artifact tenant or identity does not match the release",
                    (release.id,),
                )
        if subject.lineage.id != release.lineage_id:
            checks.add(
                ValidationCode.REFERENCE_INTEGRITY,
                "lineage.id",
                "release references a different profile lineage",
                (release.id, subject.lineage.id),
            )

    def _validate_versions(
        self, subject: ReleaseValidationSubject, checks: StructuralChecks
    ) -> None:
        release = subject.release
        if release.registry != self._registry.reference:
            checks.add(
                ValidationCode.VERSION_CONSISTENCY,
                "release.registry",
                "release does not pin the injected feature-registry snapshot",
                (release.id,),
            )
        if release.evidence_snapshot != subject.evidence_snapshot.reference:
            checks.add(
                ValidationCode.VERSION_CONSISTENCY,
                "release.evidence_snapshot",
                "release does not pin the supplied evidence snapshot",
                (release.id, subject.evidence_snapshot.id),
            )
        previous = subject.previous_release
        if release.version == 1:
            if previous is not None:
                checks.add(
                    ValidationCode.VERSION_CONSISTENCY,
                    "previous_release",
                    "first release must not supply a predecessor",
                    (release.id, previous.id),
                )
            return
        if previous is None:
            checks.add(
                ValidationCode.VERSION_CONSISTENCY,
                "previous_release",
                "later release requires its immediate predecessor",
                (release.id,),
            )
            return
        if (
            previous.id != release.previous_release_id
            or previous.version + 1 != release.version
            or previous.lineage_id != release.lineage_id
            or previous.tenant_id != release.tenant_id
            or previous.voice_identity_id != release.voice_identity_id
        ):
            checks.add(
                ValidationCode.VERSION_CONSISTENCY,
                "previous_release",
                "predecessor identity, lineage, or version is inconsistent",
                (release.id, previous.id),
            )


__all__ = ["ReleaseValidationSubject", "StructuralReleaseValidator"]
