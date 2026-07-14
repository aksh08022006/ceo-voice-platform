"""Platform-specific projection of descriptive Virality Knowledge Releases."""

from ceo_voice.context.contracts import (
    IgnoredKnowledge,
    StructuralGuidance,
    StructuralSelectionPolicy,
    ViralityTarget,
)
from ceo_voice.context.enums import IgnoredReason
from ceo_voice.core.exceptions import ContextCompilationError
from ceo_voice.models.enums import Platform
from ceo_voice.virality.contracts import PatternAggregate, ViralityProfile
from ceo_voice.virality.enums import PatternAuthority, PublicationStatus, StructuralDimension


class ViralityCompilationResult:
    """Internal pair of structural guidance and audit decisions."""

    def __init__(self, target: ViralityTarget, ignored: tuple[IgnoredKnowledge, ...]) -> None:
        self.target = target
        self.ignored = ignored


class ViralityCompiler:
    """Select compact, support-qualified structure without introducing voice rules."""

    def __init__(self, *, policy: StructuralSelectionPolicy | None = None) -> None:
        self._policy = policy or StructuralSelectionPolicy()

    def compile(self, profile: ViralityProfile, *, platform: Platform) -> ViralityCompilationResult:
        """Compile the strongest descriptive patterns for each structural dimension."""

        publication = profile.publication
        release = publication.release
        if publication.status is not PublicationStatus.ACTIVE:
            raise ContextCompilationError(
                "VKR release is not active",
                details={"reason": "inactive_virality_profile", "release_id": str(release.id)},
            )
        matching_platform = tuple(item for item in release.patterns if item.platform is platform)
        if not matching_platform:
            raise ContextCompilationError(
                "VKR release does not contain guidance for the target platform",
                details={
                    "reason": "platform_mismatch",
                    "platform": platform.value,
                    "release_id": str(release.id),
                },
            )

        eligible: dict[StructuralDimension, list[PatternAggregate]] = {}
        ignored: list[IgnoredKnowledge] = []
        for item in release.patterns:
            if item.platform is not platform:
                ignored.append(
                    self._ignored(
                        item,
                        IgnoredReason.PLATFORM_MISMATCH,
                        "pattern belongs to a different platform",
                    )
                )
                continue
            if item.authority is not PatternAuthority.DESCRIPTIVE:
                ignored.append(
                    self._ignored(
                        item,
                        IgnoredReason.INSUFFICIENT_AUTHORITY,
                        "pattern is not authorized for descriptive use",
                    )
                )
                continue
            if (
                item.support_count < self._policy.minimum_documents
                or item.leader_count < self._policy.minimum_leaders
                or item.comparable_fraction < self._policy.minimum_comparable_fraction
            ):
                ignored.append(
                    self._ignored(
                        item,
                        IgnoredReason.INSUFFICIENT_SUPPORT,
                        "pattern does not meet structural support and comparability policy",
                    )
                )
                continue
            eligible.setdefault(item.dimension, []).append(item)

        guidance: list[StructuralGuidance] = []
        for dimension in sorted(eligible, key=lambda value: value.value):
            patterns = sorted(eligible[dimension], key=self._rank_key)
            selected = patterns[: self._policy.maximum_patterns_per_dimension]
            for rank, item in enumerate(selected, start=1):
                guidance.append(self._guidance(item, rank=rank))
            for item in patterns[self._policy.maximum_patterns_per_dimension :]:
                ignored.append(
                    self._ignored(
                        item,
                        IgnoredReason.SELECTION_LIMIT,
                        "a higher-ranked pattern was selected for this structural dimension",
                    )
                )
        if not guidance:
            raise ContextCompilationError(
                "VKR release contains no patterns that meet compilation policy",
                details={
                    "reason": "insufficient_structural_guidance",
                    "release_id": str(release.id),
                    "platform": platform.value,
                },
            )
        guidance.sort(
            key=lambda item: (item.dimension.value, item.rank_within_dimension, item.pattern_id.int)
        )
        return ViralityCompilationResult(
            ViralityTarget(
                library_id=release.library_id,
                release_id=release.id,
                release_version=release.version,
                release_content_hash=release.content_hash,
                platform=platform,
                guidance=tuple(guidance),
                causal_claims_permitted=False,
            ),
            tuple(sorted(ignored, key=lambda item: item.knowledge_id)),
        )

    @staticmethod
    def _rank_key(item: PatternAggregate) -> tuple[float, int, int, float, int]:
        association = item.observed_relative_difference
        return (
            -item.comparable_fraction,
            -item.support_count,
            -item.leader_count,
            -(association if association is not None else float("-inf")),
            item.id.int,
        )

    @staticmethod
    def _guidance(item: PatternAggregate, *, rank: int) -> StructuralGuidance:
        return StructuralGuidance(
            pattern_id=item.id,
            feature_id=item.feature.feature_id,
            feature_version=str(item.feature.version),
            dimension=item.dimension,
            pattern_key=item.pattern_key,
            label=item.label,
            rank_within_dimension=rank,
            support_count=item.support_count,
            leader_count=item.leader_count,
            prevalence=item.prevalence,
            comparable_fraction=item.comparable_fraction,
            observed_relative_difference=item.observed_relative_difference,
            supporting_observation_ids=item.supporting_observation_ids,
            supporting_evidence_ids=item.supporting_evidence_ids,
        )

    @staticmethod
    def _ignored(item: PatternAggregate, reason: IgnoredReason, detail: str) -> IgnoredKnowledge:
        return IgnoredKnowledge(
            knowledge_id=str(item.id),
            knowledge_type="structural_pattern",
            reason=reason,
            detail=detail,
        )
