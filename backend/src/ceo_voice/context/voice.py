"""Generation-authorized projection of an HVM release."""

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from ceo_voice.context.contracts import (
    CompiledVoiceFeature,
    CompiledVoiceInteraction,
    ConfidenceThresholds,
    IgnoredKnowledge,
    VoiceTarget,
)
from ceo_voice.context.enums import IgnoredReason
from ceo_voice.context.voice_policy import VoiceEligibilityPolicy
from ceo_voice.context.voice_resolution import (
    VoiceFeatureResolver,
    ignored_knowledge,
    ignored_residuals,
    json_voice_value,
)
from ceo_voice.core.exceptions import ContextCompilationError, FeatureRegistryError
from ceo_voice.models.enums import Platform
from ceo_voice.voice.components import Interaction, Residual
from ceo_voice.voice.registry import FeatureRegistry
from ceo_voice.voice.releases import HVMRelease

# Resolve confidence ties by writing utility, not the alphabetical order of IDs.
# Eligibility, context-specific resolution and confidence remain authoritative.
_WRITING_FEATURES = (
    "analysis.sentence-median-words",
    "analysis.short-sentence-ratio",
    "analysis.paragraph-median-words",
    "analysis.single-sentence-paragraph-ratio",
    "analysis.first-person-plural-ratio",
    "analysis.opening-first-person-indicator",
    "analysis.apostrophized-word-ratio",
    "analysis.hedge-marker-rate",
    "analysis.opening-question-indicator",
    "analysis.closing-question-indicator",
    "analysis.second-person-pronoun-ratio",
    "analysis.function-word-ratio",
)
_WRITING_PRIORITY = {key: index for index, key in enumerate(_WRITING_FEATURES)}


class VoiceCompilationResult:
    """Internal pair of compiled output and audit decisions."""

    def __init__(self, target: VoiceTarget, ignored: tuple[IgnoredKnowledge, ...]) -> None:
        self.target = target
        self.ignored = ignored


class VoiceCompiler:
    """Resolve a compact voice target while enforcing HVM downstream authority."""

    def __init__(
        self,
        *,
        registry: FeatureRegistry,
        thresholds: ConfidenceThresholds | None = None,
        maximum_features: int = 12,
    ) -> None:
        if maximum_features < 1:
            raise ValueError("maximum features must be positive")
        self._registry = registry
        self._policy = VoiceEligibilityPolicy(thresholds or ConfidenceThresholds())
        self._resolver = VoiceFeatureResolver(self._policy)
        self._maximum_features = maximum_features

    def compile(
        self,
        release: HVMRelease,
        *,
        leader_id: UUID,
        platform: Platform,
        language: str,
        audience: str,
        compiled_at: datetime,
    ) -> VoiceCompilationResult:
        """Compile authorized residuals with conditional inheritance and preferences."""

        if release.registry != self._registry.reference:
            raise ContextCompilationError(
                "HVM release and feature registry do not match",
                details={"reason": "registry_mismatch", "release_id": str(release.id)},
            )
        candidates: list[tuple[float, CompiledVoiceFeature]] = []
        ignored: list[IgnoredKnowledge] = []
        residuals_by_feature: dict[str, list[Residual]] = {}
        for residual in release.components.residuals:
            residuals_by_feature.setdefault(residual.feature.feature_id, []).append(residual)

        for feature_id in sorted(residuals_by_feature):
            residuals = residuals_by_feature[feature_id]
            try:
                definition = self._registry.get(residuals[0].feature)
            except FeatureRegistryError as error:
                raise ContextCompilationError(
                    "HVM component references an unavailable feature definition",
                    details={"reason": "registry_mismatch", **error.details},
                ) from error
            rejection = self._policy.definition_rejection(
                definition, platform=platform, language=language
            )
            if rejection is not None:
                ignored.extend(ignored_residuals(residuals, *rejection))
                continue
            eligible: list[tuple[float, Residual]] = []
            for residual in residuals:
                rejection = self._policy.component_rejection(
                    residual.decision_state,
                    residual.confidence,
                    residual.context,
                    platform=platform,
                    language=language,
                    audience=audience,
                )
                if rejection is not None:
                    ignored.append(ignored_knowledge(residual.id, "residual", *rejection))
                    continue
                eligible.append((self._policy.score(residual.confidence), residual))
            if not eligible:
                continue
            eligible.sort(
                key=lambda item: (
                    -item[0],
                    -self._policy.specificity(item[1].context),
                    item[1].id.int,
                )
            )
            core_score, core = eligible[0]
            for _, residual in eligible[1:]:
                ignored.append(
                    ignored_knowledge(
                        residual.id,
                        "residual",
                        IgnoredReason.SUPERSEDED_BY_CONTEXT,
                        "a higher-confidence or more specific residual was selected",
                    )
                )
            conditional = self._resolver.select_conditional(
                release.components.conditional_residuals,
                parent=core,
                platform=platform,
                language=language,
                audience=audience,
                ignored=ignored,
            )
            preference = self._resolver.select_preference(
                release.explicit_preferences,
                feature_id=feature_id,
                platform=platform,
                language=language,
                audience=audience,
                compiled_at=compiled_at,
                ignored=ignored,
            )
            compiled = self._resolver.compile_feature(
                definition,
                core,
                core_score=core_score,
                conditional=conditional,
                preference=preference,
            )
            candidates.append((compiled.confidence.selection_score, compiled))

        candidates.sort(
            key=lambda item: (
                -item[0],
                _WRITING_PRIORITY.get(item[1].feature_id, len(_WRITING_PRIORITY)),
                item[1].feature_id,
            )
        )
        selected = candidates[: self._maximum_features]
        for _, feature in candidates[self._maximum_features :]:
            ignored.append(
                IgnoredKnowledge(
                    knowledge_id=feature.feature_id,
                    knowledge_type="voice_feature",
                    reason=IgnoredReason.SELECTION_LIMIT,
                    detail="feature ranked below the configured compactness limit",
                )
            )
        if not selected:
            ignored_reasons = {item.reason for item in ignored}
            failure_reason = (
                "platform_mismatch"
                if ignored_reasons == {IgnoredReason.PLATFORM_MISMATCH}
                else (
                    "language_mismatch"
                    if ignored_reasons == {IgnoredReason.LANGUAGE_MISMATCH}
                    else "insufficient_voice_guidance"
                )
            )
            raise ContextCompilationError(
                "HVM release contains no generation-authorized voice features",
                details={
                    "reason": failure_reason,
                    "release_id": str(release.id),
                    "ignored_count": len(ignored),
                },
            )
        ranked_features = tuple(
            feature.model_copy(update={"rank": rank})
            for rank, (_, feature) in enumerate(selected, start=1)
        )
        interactions = self._compile_interactions(
            release.components.interactions,
            selected_feature_ids={item.feature_id for item in ranked_features},
            platform=platform,
            language=language,
            audience=audience,
            ignored=ignored,
        )
        return VoiceCompilationResult(
            VoiceTarget(
                identity_id=release.voice_identity_id,
                leader_id=leader_id,
                release_id=release.id,
                release_version=release.version,
                release_content_hash=release.content_hash,
                registry_hash=release.registry.snapshot_hash,
                language=language,
                platform=platform,
                features=ranked_features,
                interactions=interactions,
            ),
            tuple(sorted(ignored, key=lambda item: (item.knowledge_type, item.knowledge_id))),
        )

    def _compile_interactions(
        self,
        interactions: Iterable[Interaction],
        *,
        selected_feature_ids: set[str],
        platform: Platform,
        language: str,
        audience: str,
        ignored: list[IgnoredKnowledge],
    ) -> tuple[CompiledVoiceInteraction, ...]:
        selected: list[CompiledVoiceInteraction] = []
        for item in interactions:
            feature_ids = tuple(feature.feature_id for feature in item.features)
            if not set(feature_ids).issubset(selected_feature_ids):
                ignored.append(
                    ignored_knowledge(
                        item.id,
                        "interaction",
                        IgnoredReason.DEPENDENCY_NOT_SELECTED,
                        "one or more marginal voice features were not selected",
                    )
                )
                continue
            rejection = self._policy.component_rejection(
                item.decision_state,
                item.confidence,
                item.context,
                platform=platform,
                language=language,
                audience=audience,
            )
            if rejection is not None:
                ignored.append(ignored_knowledge(item.id, "interaction", *rejection))
                continue
            score = self._policy.score(item.confidence)
            selected.append(
                CompiledVoiceInteraction(
                    interaction_id=item.id,
                    feature_ids=feature_ids,
                    interaction_type=item.interaction_type.value,
                    value=json_voice_value(item.value),
                    component_evidence_ids=item.evidence_unit_ids,
                    confidence=self._policy.confidence(item.confidence, score=score),
                )
            )
        return tuple(sorted(selected, key=lambda item: item.interaction_id.int))
