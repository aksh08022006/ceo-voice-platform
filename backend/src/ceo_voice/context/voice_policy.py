"""Authority, applicability, and confidence policy for voice compilation."""

from ceo_voice.context.contracts import ConfidenceThresholds, VoiceConfidence
from ceo_voice.context.enums import IgnoredReason
from ceo_voice.models.enums import DocumentType, Platform
from ceo_voice.voice.components import ConfidenceVector
from ceo_voice.voice.enums import DecisionState, DownstreamPermission
from ceo_voice.voice.features import FeatureDefinition
from ceo_voice.voice.primitives import VoiceContext

_ACTIONABLE_STATES = {
    DecisionState.ACTIONABLE_SOFT,
    DecisionState.ACTIONABLE_STRONG,
    DecisionState.EXPLICIT_POLICY,
}


class VoiceEligibilityPolicy:
    """Apply versioned generation authority, context, and confidence gates."""

    def __init__(self, thresholds: ConfidenceThresholds) -> None:
        self._thresholds = thresholds

    @property
    def minimum_transfer_confidence(self) -> float:
        """Return the conditional-inheritance transfer gate."""

        return self._thresholds.minimum_transfer_confidence

    def definition_rejection(
        self, definition: FeatureDefinition, *, platform: Platform, language: str
    ) -> tuple[IgnoredReason, str] | None:
        """Explain why a registry definition cannot govern generation."""

        if DownstreamPermission.GENERATE not in definition.downstream_permissions:
            return (
                IgnoredReason.NOT_GENERATION_AUTHORIZED,
                "feature registry does not grant generation permission",
            )
        if not definition.supported_platforms.all_platforms and (
            platform not in definition.supported_platforms.platforms
        ):
            return IgnoredReason.PLATFORM_MISMATCH, "feature does not support the target platform"
        if not definition.supported_languages.all_languages and (
            language not in definition.supported_languages.languages
        ):
            return IgnoredReason.LANGUAGE_MISMATCH, "feature does not support the target language"
        return None

    def component_rejection(
        self,
        state: DecisionState,
        confidence: ConfidenceVector,
        context: VoiceContext,
        *,
        platform: Platform,
        language: str,
        audience: str,
    ) -> tuple[IgnoredReason, str] | None:
        """Explain why a modeled HVM component cannot cross the boundary."""

        if state not in _ACTIONABLE_STATES:
            return IgnoredReason.NON_ACTIONABLE, "component authority is below actionable"
        if not self.context_matches(
            context, platform=platform, language=language, audience=audience
        ):
            reason = (
                IgnoredReason.LANGUAGE_MISMATCH
                if context.language != language
                else IgnoredReason.PLATFORM_MISMATCH
            )
            return reason, "component context does not match the requested generation context"
        if not self._passes_confidence(confidence):
            return IgnoredReason.LOW_CONFIDENCE, "component does not meet confidence policy"
        return None

    @staticmethod
    def context_matches(
        context: VoiceContext, *, platform: Platform, language: str, audience: str
    ) -> bool:
        """Return whether all represented context dimensions are safely resolvable."""

        if context.language != language:
            return False
        if context.platform is not None and context.platform is not platform:
            return False
        if context.content_form not in {None, DocumentType.SOCIAL_POST}:
            return False
        if context.audience is not None and context.audience != audience:
            return False
        return context.mode is None and context.time_regime is None

    @staticmethod
    def specificity(context: VoiceContext) -> int:
        """Count governed context dimensions for deterministic tie-breaking."""

        return sum(
            value is not None
            for value in (
                context.platform,
                context.content_form,
                context.audience,
                context.mode,
                context.time_regime,
            )
        )

    @staticmethod
    def score(value: ConfidenceVector, *, transfer: float | None = None) -> float:
        """Compress decision-relevant confidence only for deterministic ranking."""

        parts = (
            value.measurement_reliability,
            value.attribution_reliability,
            value.coverage,
            value.distinctiveness,
            value.calibration,
            value.stability,
            1 - value.conflict,
        )
        score = sum(parts) / len(parts)
        if transfer is not None:
            score = score * 0.8 + transfer * 0.2
        return round(score, 6)

    @classmethod
    def confidence(
        cls,
        value: ConfidenceVector,
        *,
        score: float,
        transfer: float | None = None,
    ) -> VoiceConfidence:
        """Project the confidence fields a generation consumer may inspect."""

        return VoiceConfidence(
            measurement_reliability=value.measurement_reliability,
            attribution_reliability=value.attribution_reliability,
            coverage=value.coverage,
            effective_support=value.effective_support,
            distinctiveness=value.distinctiveness,
            calibration=value.calibration,
            conflict=value.conflict,
            transfer_confidence=transfer,
            selection_score=score,
        )

    def _passes_confidence(self, value: ConfidenceVector) -> bool:
        threshold = self._thresholds
        return (
            value.measurement_reliability >= threshold.minimum_measurement_reliability
            and value.attribution_reliability >= threshold.minimum_attribution_reliability
            and value.coverage >= threshold.minimum_coverage
            and value.effective_support >= threshold.minimum_effective_support
            and value.distinctiveness >= threshold.minimum_distinctiveness
            and value.calibration >= threshold.minimum_calibration
            and value.conflict <= threshold.maximum_conflict
        )
