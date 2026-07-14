"""Structural integrity validation for immutable Virality Knowledge Releases."""

from uuid import NAMESPACE_URL, uuid5

from ceo_voice.core.exceptions import ViralityError
from ceo_voice.models.base import UtcDatetime
from ceo_voice.virality.contracts import (
    CorpusAnalysis,
    ValidationIssue,
    ValidationReport,
    Version,
    ViralityRelease,
)
from ceo_voice.virality.enums import (
    PatternAuthority,
    ValidationCode,
    ValidationSeverity,
)
from ceo_voice.virality.registry import StructuralFeatureRegistry
from ceo_voice.virality.releases import build_analysis_snapshot, release_content_hash

VALIDATOR_VERSION = Version(major=1, minor=0, patch=0)


class ViralityReleaseValidator:
    """Validate ownership, registry, evidence, aggregate, and version invariants."""

    def __init__(self, registry: StructuralFeatureRegistry) -> None:
        self._registry = registry

    def validate(
        self,
        release: ViralityRelease,
        analysis: CorpusAnalysis,
        *,
        validated_at: UtcDatetime,
    ) -> ValidationReport:
        """Return all findings without short-circuiting at the first issue."""

        issues: list[ValidationIssue] = []
        if release.registry != self._registry.reference:
            issues.append(
                self._error(
                    ValidationCode.REGISTRY,
                    "release.registry",
                    "Registry snapshot differs from the validator.",
                )
            )
        if release.content_hash != release_content_hash(release):
            issues.append(
                self._error(
                    ValidationCode.VERSION,
                    "release.content_hash",
                    "Release content hash is invalid.",
                )
            )
        rebuilt_snapshot = build_analysis_snapshot(
            snapshot_id=release.analysis_snapshot.id,
            analysis=analysis,
            corpus_id=release.corpus_id,
        )
        if rebuilt_snapshot != release.analysis_snapshot:
            issues.append(
                self._error(
                    ValidationCode.VERSION,
                    "release.analysis_snapshot",
                    "Analysis content does not match the release snapshot.",
                )
            )
        evidence = {item.id: item for item in analysis.evidence}
        observations = {item.id: item for item in analysis.observations}
        if len(evidence) != len(analysis.evidence):
            issues.append(
                self._error(
                    ValidationCode.EVIDENCE, "release.evidence", "Evidence IDs must be unique."
                )
            )
        if len(observations) != len(analysis.observations):
            issues.append(
                self._error(
                    ValidationCode.OBSERVATION,
                    "release.observations",
                    "Observation IDs must be unique.",
                )
            )
        for observation in analysis.observations:
            path = f"observations.{observation.id}"
            if (
                observation.tenant_id != release.tenant_id
                or observation.corpus_id != release.corpus_id
            ):
                issues.append(
                    self._error(
                        ValidationCode.OWNERSHIP,
                        path,
                        "Observation ownership differs from the release.",
                    )
                )
            try:
                definition = self._registry.get(observation.feature)
                if observation.pattern_key not in definition.allowed_patterns:
                    issues.append(
                        self._error(
                            ValidationCode.REGISTRY,
                            path,
                            "Observation pattern is not registry-approved.",
                        )
                    )
                if observation.extractor_id != definition.extractor_id:
                    issues.append(
                        self._error(
                            ValidationCode.REGISTRY,
                            path,
                            "Observation producer does not own the feature.",
                        )
                    )
            except ViralityError:
                issues.append(
                    self._error(
                        ValidationCode.REGISTRY,
                        path,
                        "Observation feature is absent from the registry.",
                    )
                )
            for evidence_id in observation.evidence_ids:
                item = evidence.get(evidence_id)
                if (
                    item is None
                    or item.document_id != observation.document_id
                    or item.document_version != observation.document_version
                    or item.tenant_id != release.tenant_id
                    or item.corpus_id != release.corpus_id
                ):
                    issues.append(
                        self._error(
                            ValidationCode.EVIDENCE,
                            path,
                            "Observation evidence is missing or belongs to another document.",
                        )
                    )
        for pattern in release.patterns:
            path = f"patterns.{pattern.id}"
            if pattern.tenant_id != release.tenant_id:
                issues.append(
                    self._error(
                        ValidationCode.OWNERSHIP,
                        path,
                        "Pattern ownership differs from the release.",
                    )
                )
            contributing = tuple(
                observations.get(item) for item in pattern.supporting_observation_ids
            )
            if any(item is None for item in contributing):
                issues.append(
                    self._error(
                        ValidationCode.AGGREGATE, path, "Pattern references an unknown observation."
                    )
                )
                continue
            typed = tuple(item for item in contributing if item is not None)
            matching = tuple(
                item
                for item in analysis.observations
                if item.feature == pattern.feature
                and item.pattern_key == pattern.pattern_key
                and item.platform == pattern.platform
            )
            if pattern.support_count != len(matching):
                issues.append(
                    self._error(
                        ValidationCode.AGGREGATE,
                        path,
                        "Pattern support count does not match references.",
                    )
                )
            if any(
                item.feature != pattern.feature
                or item.pattern_key != pattern.pattern_key
                or item.platform != pattern.platform
                for item in typed
            ):
                issues.append(
                    self._error(
                        ValidationCode.AGGREGATE, path, "Pattern mixes incompatible observations."
                    )
                )
            expected_evidence = {evidence_id for item in typed for evidence_id in item.evidence_ids}
            if set(pattern.supporting_evidence_ids) != expected_evidence:
                issues.append(
                    self._error(
                        ValidationCode.EVIDENCE,
                        path,
                        "Pattern evidence does not match contributing observations.",
                    )
                )
            expected_leaders = len({item.leader_id for item in matching})
            if pattern.leader_count != expected_leaders:
                issues.append(
                    self._error(
                        ValidationCode.AGGREGATE, path, "Pattern leader support is inconsistent."
                    )
                )
            eligible = (
                pattern.support_count >= release.aggregation_policy.minimum_documents
                and pattern.leader_count >= release.aggregation_policy.minimum_leaders
            )
            if (pattern.authority is PatternAuthority.DESCRIPTIVE) != eligible:
                issues.append(
                    self._error(
                        ValidationCode.AGGREGATE, path, "Pattern authority violates support policy."
                    )
                )
        if any(item.performance.confounded for item in analysis.observations):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.OBSERVATION,
                    severity=ValidationSeverity.WARNING,
                    message="Some performance observations lack impression denominators.",
                    path="release.observations",
                )
            )
        return ValidationReport(
            id=uuid5(NAMESPACE_URL, f"{release.id}:virality-validation:{VALIDATOR_VERSION}"),
            release_id=release.id,
            validator_version=VALIDATOR_VERSION,
            issues=tuple(issues),
            validated_at=validated_at,
        )

    @staticmethod
    def _error(code: ValidationCode, path: str, message: str) -> ValidationIssue:
        return ValidationIssue(
            code=code,
            severity=ValidationSeverity.ERROR,
            message=message,
            path=path,
        )
