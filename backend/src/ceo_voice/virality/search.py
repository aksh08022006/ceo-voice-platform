"""Exact faceted search over published structural patterns."""

from ceo_voice.virality.contracts import (
    PatternSearchHit,
    PatternSearchQuery,
    ViralityRelease,
)
from ceo_voice.virality.enums import PatternAuthority


class PatternSearcher:
    """Find reusable patterns by governed facets; no semantic retrieval is performed."""

    def search(
        self, release: ViralityRelease, query: PatternSearchQuery
    ) -> tuple[PatternSearchHit, ...]:
        """Return supported matches ordered by authority, support, and comparability."""

        matches = tuple(
            item
            for item in release.patterns
            if (query.platform is None or item.platform is query.platform)
            and (not query.dimensions or item.dimension in query.dimensions)
            and (not query.feature_ids or item.feature.feature_id in query.feature_ids)
            and item.support_count >= query.minimum_support
            and (query.authority is None or item.authority is query.authority)
        )
        ordered = sorted(
            matches,
            key=lambda item: (
                item.authority is PatternAuthority.DESCRIPTIVE,
                item.support_count,
                item.comparable_fraction,
                item.prevalence,
                item.feature.feature_id,
                item.pattern_key,
            ),
            reverse=True,
        )[: query.limit]
        return tuple(
            PatternSearchHit(
                pattern=item,
                explanation=(
                    f"Matched {item.dimension.value} on {item.platform.value}; supported by "
                    f"{item.support_count} posts from {item.leader_count} leaders with "
                    f"{item.comparable_fraction:.0%} exposure-comparable performance data."
                ),
            )
            for item in ordered
        )
