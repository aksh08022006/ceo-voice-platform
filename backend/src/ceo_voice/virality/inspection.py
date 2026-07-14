"""Human inspection projection for published structural intelligence."""

from ceo_voice.models.base import UtcDatetime
from ceo_voice.virality.contracts import (
    InspectionPattern,
    InspectionReport,
    ViralityCorpus,
    ViralityRelease,
)
from ceo_voice.virality.enums import PatternAuthority


def build_inspection_report(
    release: ViralityRelease,
    corpus: ViralityCorpus,
    *,
    generated_at: UtcDatetime,
) -> InspectionReport:
    """Summarize scope, support, associations, and limitations without source wording."""

    leaders = {item.document.ceo_id for item in corpus.items}
    comparable = sum(
        item.performance.impressions is not None and item.performance.impressions > 0
        for item in corpus.items
    )
    limitations = [
        "Observed performance differences are associations, not causal lift estimates.",
        "The library stores structural categories and evidence addresses, not reusable wording.",
    ]
    if comparable < len(corpus.items):
        limitations.append(
            "Some posts lack impression denominators and are performance-confounded."
        )
    if any(item.authority is PatternAuthority.INSUFFICIENT for item in release.patterns):
        limitations.append(
            "Some patterns lack the configured cross-document or cross-leader support."
        )
    patterns = tuple(
        InspectionPattern(
            feature_id=item.feature.feature_id,
            dimension=item.dimension,
            pattern_key=item.pattern_key,
            label=item.label,
            platform=item.platform,
            support_count=item.support_count,
            leader_count=item.leader_count,
            prevalence=item.prevalence,
            observed_relative_difference=item.observed_relative_difference,
            authority=item.authority,
        )
        for item in sorted(
            release.patterns,
            key=lambda value: (
                value.authority is PatternAuthority.DESCRIPTIVE,
                value.support_count,
                value.comparable_fraction,
            ),
            reverse=True,
        )
    )
    return InspectionReport(
        release_id=release.id,
        release_version=release.version,
        summary=(
            f"Virality Knowledge Release v{release.version} describes {len(release.patterns)} "
            f"platform-aware structural patterns across {len(corpus.items)} posts and "
            f"{len(leaders)} leaders. It contains no personal voice representation."
        ),
        corpus_documents=len(corpus.items),
        corpus_leaders=len(leaders),
        comparable_documents=comparable,
        platforms=tuple(
            sorted(
                {item.document.platform for item in corpus.items if item.document.platform}, key=str
            )
        ),
        patterns=patterns,
        limitations=tuple(limitations),
        generated_at=generated_at,
    )
