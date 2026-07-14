"""Transparent v1 normalization of post-performance observations."""

from ceo_voice.virality.contracts import NormalizedPerformance, PerformanceMetrics, Version
from ceo_voice.virality.enums import PerformanceBasis

NORMALIZER_VERSION = Version(major=1, minor=0, patch=0)


class PerformanceNormalizer:
    """Normalize exposure where possible while reporting every confound explicitly."""

    def normalize(self, metrics: PerformanceMetrics) -> NormalizedPerformance:
        """Return a deterministic weighted-engagement rate or an explicit raw fallback."""

        weighted = float(
            metrics.reactions
            + 2 * metrics.comments
            + 3 * metrics.shares
            + 2 * metrics.saves
            + metrics.clicks
        )
        limitations: list[str] = []
        if metrics.impressions:
            denominator = metrics.impressions
            basis = PerformanceBasis.IMPRESSIONS
            confounded = False
        elif metrics.audience_size:
            denominator = metrics.audience_size
            basis = PerformanceBasis.AUDIENCE
            confounded = True
            limitations.append("Impressions are unavailable; audience size is an exposure proxy.")
        else:
            denominator = None
            basis = PerformanceBasis.RAW_ENGAGEMENT
            confounded = True
            limitations.append("No exposure or audience denominator is available.")
        if metrics.impressions == 0:
            limitations.append("Reported impressions are zero and cannot be used as a denominator.")
        score = weighted if denominator is None else weighted * 1_000 / denominator
        return NormalizedPerformance(
            weighted_engagement=weighted,
            score_per_thousand=score,
            basis=basis,
            denominator=denominator,
            confounded=confounded,
            limitations=tuple(limitations),
            normalizer_version=NORMALIZER_VERSION,
        )
