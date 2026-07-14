"""Conditional inheritance and explicit-preference resolution for voice targets."""

from collections.abc import Iterable
from datetime import datetime
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from ceo_voice.context.contracts import CompiledVoiceFeature, IgnoredKnowledge
from ceo_voice.context.enums import IgnoredReason, VoiceResolutionSource
from ceo_voice.context.voice_policy import VoiceEligibilityPolicy
from ceo_voice.models.enums import Platform
from ceo_voice.voice.components import ConditionalResidual, ExplicitPreference, Residual
from ceo_voice.voice.enums import DecisionState
from ceo_voice.voice.features import FeatureDefinition
from ceo_voice.voice.values import ScalarValue, VoiceValue


def ignored_knowledge(
    identifier: UUID,
    knowledge_type: str,
    reason: IgnoredReason,
    detail: str,
) -> IgnoredKnowledge:
    """Build one canonical ignored-component decision."""

    return IgnoredKnowledge(
        knowledge_id=str(identifier),
        knowledge_type=knowledge_type,
        reason=reason,
        detail=detail,
    )


def ignored_residuals(
    residuals: Iterable[Residual], reason: IgnoredReason, detail: str
) -> list[IgnoredKnowledge]:
    """Build the same rejection for a feature's residual candidates."""

    return [ignored_knowledge(item.id, "residual", reason, detail) for item in residuals]


def json_voice_value(value: VoiceValue) -> JsonValue:
    """Project an HVM value into model-neutral JSON data."""

    return cast(JsonValue, value.model_dump(mode="json"))


class VoiceFeatureResolver:
    """Resolve inherited and explicitly governed targets for one eligible feature."""

    def __init__(self, policy: VoiceEligibilityPolicy) -> None:
        self._policy = policy

    def select_conditional(
        self,
        conditionals: Iterable[ConditionalResidual],
        *,
        parent: Residual,
        platform: Platform,
        language: str,
        audience: str,
        ignored: list[IgnoredKnowledge],
    ) -> ConditionalResidual | None:
        """Select the strongest applicable conditional delta for a core residual."""

        eligible: list[tuple[float, ConditionalResidual]] = []
        for item in conditionals:
            if item.parent_residual_id != parent.id:
                continue
            rejection = self._policy.component_rejection(
                item.decision_state,
                item.confidence,
                item.condition,
                platform=platform,
                language=language,
                audience=audience,
            )
            if (
                rejection is None
                and item.transfer_confidence < self._policy.minimum_transfer_confidence
            ):
                rejection = (
                    IgnoredReason.LOW_CONFIDENCE,
                    "conditional inheritance does not meet transfer-confidence policy",
                )
            if rejection is not None:
                ignored.append(ignored_knowledge(item.id, "conditional_residual", *rejection))
                continue
            score = self._policy.score(item.confidence, transfer=item.transfer_confidence)
            eligible.append((score, item))
        if not eligible:
            return None
        eligible.sort(
            key=lambda item: (
                -item[0],
                -self._policy.specificity(item[1].condition),
                item[1].id.int,
            )
        )
        selected = eligible[0][1]
        for _, item in eligible[1:]:
            ignored.append(
                ignored_knowledge(
                    item.id,
                    "conditional_residual",
                    IgnoredReason.SUPERSEDED_BY_CONTEXT,
                    "a higher-confidence conditional adaptation was selected",
                )
            )
        return selected

    def select_preference(
        self,
        preferences: Iterable[ExplicitPreference],
        *,
        feature_id: str,
        platform: Platform,
        language: str,
        audience: str,
        compiled_at: datetime,
        ignored: list[IgnoredKnowledge],
    ) -> ExplicitPreference | None:
        """Select the highest-priority active explicit preference."""

        eligible = [
            item
            for item in preferences
            if item.feature.feature_id == feature_id
            and item.effective_range.contains(compiled_at)
            and self._policy.context_matches(
                item.scope, platform=platform, language=language, audience=audience
            )
        ]
        if not eligible:
            return None
        eligible.sort(
            key=lambda item: (
                -item.priority,
                -self._policy.specificity(item.scope),
                item.id.int,
            )
        )
        selected = eligible[0]
        for item in eligible[1:]:
            ignored.append(
                ignored_knowledge(
                    item.id,
                    "explicit_preference",
                    IgnoredReason.SUPERSEDED_BY_PREFERENCE,
                    "a higher-priority explicit preference was selected",
                )
            )
        return selected

    def compile_feature(
        self,
        definition: FeatureDefinition,
        core: Residual,
        *,
        core_score: float,
        conditional: ConditionalResidual | None,
        preference: ExplicitPreference | None,
    ) -> CompiledVoiceFeature:
        """Resolve the final target while retaining every inheritance layer."""

        target = self._resolve_value(core.value, conditional.delta if conditional else None)
        source = VoiceResolutionSource.CORE_RESIDUAL
        state = core.decision_state
        component_ids = [core.id]
        evidence_ids = set(core.evidence_unit_ids)
        confidence = core.confidence
        transfer: float | None = None
        if conditional is not None:
            source = VoiceResolutionSource.PLATFORM_CONDITIONAL
            state = conditional.decision_state
            component_ids.append(conditional.id)
            evidence_ids.update(conditional.evidence_unit_ids)
            confidence = conditional.confidence
            transfer = conditional.transfer_confidence
        if preference is not None:
            source = VoiceResolutionSource.EXPLICIT_PREFERENCE
            state = DecisionState.EXPLICIT_POLICY
            component_ids.append(preference.id)
            target = json_voice_value(preference.target)
        score = self._policy.score(confidence, transfer=transfer) if conditional else core_score
        if preference is not None:
            score = max(score, 0.95)
        return CompiledVoiceFeature(
            feature_id=definition.feature_id,
            feature_version=str(definition.semantic_version),
            display_name=definition.display_name,
            dimension=definition.dimension,
            rank=1,
            resolution_source=source,
            decision_state=state,
            target_value=target,
            core_value=json_voice_value(core.value),
            conditional_delta=(json_voice_value(conditional.delta) if conditional else None),
            confidence=self._policy.confidence(confidence, score=score, transfer=transfer),
            component_ids=tuple(component_ids),
            evidence_unit_ids=tuple(sorted(evidence_ids, key=lambda value: value.int)),
        )

    @staticmethod
    def _resolve_value(core: VoiceValue, delta: VoiceValue | None) -> JsonValue:
        if delta is None:
            return json_voice_value(core)
        if (
            isinstance(core, ScalarValue)
            and isinstance(delta, ScalarValue)
            and core.unit == delta.unit
        ):
            return cast(
                JsonValue,
                {"kind": "scalar", "value": core.value + delta.value, "unit": core.unit},
            )
        return cast(
            JsonValue,
            {
                "kind": "inherited_target",
                "base": json_voice_value(core),
                "conditional_delta": json_voice_value(delta),
            },
        )
