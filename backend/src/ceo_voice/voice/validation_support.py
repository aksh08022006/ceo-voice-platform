"""Shared structural checks used by focused HVM validation passes."""

from uuid import UUID

from ceo_voice.core.exceptions import FeatureRegistryError
from ceo_voice.voice.components import ConfidenceVector
from ceo_voice.voice.enums import ValidationCode, ValidationSeverity
from ceo_voice.voice.evidence import EvidenceUnit
from ceo_voice.voice.features import FeatureDefinition
from ceo_voice.voice.ports import FeatureRegistryReader
from ceo_voice.voice.primitives import FeatureReference, VoiceContext
from ceo_voice.voice.releases import ValidationIssue
from ceo_voice.voice.values import VoiceValue


class StructuralChecks:
    """Accumulate deterministic findings and provide reusable registry-aware checks."""

    def __init__(self, *, registry: FeatureRegistryReader) -> None:
        self.registry = registry
        self.issues: list[ValidationIssue] = []

    def add(
        self,
        code: ValidationCode,
        path: str,
        message: str,
        reference_ids: tuple[UUID, ...] = (),
    ) -> None:
        """Append one structural error without interrupting the remaining audit."""

        self.issues.append(
            ValidationIssue(
                code=code,
                severity=ValidationSeverity.ERROR,
                path=path,
                message=message,
                reference_ids=reference_ids,
            )
        )

    def definition(self, reference: FeatureReference, path: str) -> FeatureDefinition | None:
        """Resolve an exact feature definition and record a stable finding on failure."""

        try:
            return self.registry.get(reference)
        except FeatureRegistryError:
            self.add(
                ValidationCode.FEATURE_REGISTRY_CONSISTENCY,
                path,
                "exact feature definition is absent from the pinned registry",
            )
            return None

    def validate_context(
        self, definition: FeatureDefinition, context: VoiceContext, path: str
    ) -> None:
        """Validate language and platform applicability for one registered feature."""

        languages = definition.supported_languages
        if not languages.all_languages and context.language not in languages.languages:
            self.add(
                ValidationCode.FEATURE_REGISTRY_CONSISTENCY,
                f"{path}.context.language",
                "context language is unsupported by the feature definition",
            )
        platforms = definition.supported_platforms
        if not platforms.all_platforms and context.platform not in platforms.platforms:
            self.add(
                ValidationCode.FEATURE_REGISTRY_CONSISTENCY,
                f"{path}.context.platform",
                "context platform is unsupported by the feature definition",
            )

    def validate_evidence_ids(
        self,
        evidence_ids: tuple[UUID, ...],
        evidence_by_id: dict[UUID, EvidenceUnit],
        path: str,
    ) -> None:
        """Record component references that do not resolve in the pinned evidence bundle."""

        unknown = tuple(item for item in evidence_ids if item not in evidence_by_id)
        if unknown:
            self.add(
                ValidationCode.REFERENCE_INTEGRITY,
                f"{path}.evidence_unit_ids",
                "component references unknown evidence units",
                unknown,
            )

    def validate_confidence(
        self, confidence: ConfidenceVector, evidence_count: int, path: str
    ) -> None:
        """Require confidence support counts to match component evidence references."""

        if confidence.evidence_count != evidence_count:
            self.add(
                ValidationCode.CONFIDENCE_COMPLETENESS,
                f"{path}.confidence.evidence_count",
                "confidence evidence count must match component evidence references",
            )

    def validate_component_common(
        self,
        feature: FeatureReference,
        value: VoiceValue,
        context: VoiceContext,
        confidence: ConfidenceVector,
        evidence_ids: tuple[UUID, ...],
        evidence_by_id: dict[UUID, EvidenceUnit],
        path: str,
    ) -> FeatureDefinition | None:
        """Validate fields shared by aggregate, residual, and conditional components."""

        definition = self.definition(feature, f"{path}.feature")
        if definition is not None:
            if value.kind is not definition.value_type:
                self.add(
                    ValidationCode.FEATURE_REGISTRY_CONSISTENCY,
                    f"{path}.value",
                    "component value type differs from its feature definition",
                )
            self.validate_context(definition, context, path)
        self.validate_evidence_ids(evidence_ids, evidence_by_id, path)
        self.validate_confidence(confidence, len(evidence_ids), path)
        return definition
