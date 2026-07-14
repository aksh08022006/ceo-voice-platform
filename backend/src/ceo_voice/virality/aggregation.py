"""Cross-post aggregation with transparent support and uncertainty statistics."""

from collections import defaultdict
from math import sqrt
from statistics import fmean, stdev
from uuid import NAMESPACE_URL, UUID, uuid5

from ceo_voice.models.enums import Platform
from ceo_voice.virality.contracts import (
    AggregationPolicy,
    PatternAggregate,
    StructuralObservation,
    publication_window,
)
from ceo_voice.virality.enums import PatternAuthority
from ceo_voice.virality.registry import StructuralFeatureRegistry


class PatternAggregator:
    """Aggregate structural classifications without claiming causal performance effects."""

    def __init__(
        self,
        *,
        registry: StructuralFeatureRegistry,
        policy: AggregationPolicy,
    ) -> None:
        self._registry = registry
        self._policy = policy

    def aggregate(
        self,
        observations: tuple[StructuralObservation, ...],
        *,
        release_id: UUID,
    ) -> tuple[PatternAggregate, ...]:
        """Produce platform-specific categorical prevalence and performance associations."""

        groups: dict[tuple[Platform, object, str], list[StructuralObservation]] = defaultdict(list)
        platform_documents: dict[Platform, dict[UUID, StructuralObservation]] = defaultdict(dict)
        for observation in observations:
            groups[(observation.platform, observation.feature, observation.pattern_key)].append(
                observation
            )
            platform_documents[observation.platform].setdefault(
                observation.document_id, observation
            )
        platform_means = {
            platform: fmean(item.performance.score_per_thousand for item in documents.values())
            for platform, documents in platform_documents.items()
        }
        aggregates: list[PatternAggregate] = []
        for (platform, _feature, pattern_key), items in groups.items():
            typed_feature = items[0].feature
            definition = self._registry.get(typed_feature)
            scores = tuple(item.performance.score_per_thousand for item in items)
            mean = fmean(scores)
            platform_mean = platform_means[platform]
            leaders = {item.leader_id for item in items}
            comparable = sum(not item.performance.confounded for item in items) / len(items)
            earliest, latest = publication_window(tuple(items))
            sampled = tuple(sorted(items, key=lambda value: value.id.int)[:25])
            authority = (
                PatternAuthority.DESCRIPTIVE
                if len(items) >= self._policy.minimum_documents
                and len(leaders) >= self._policy.minimum_leaders
                else PatternAuthority.INSUFFICIENT
            )
            aggregates.append(
                PatternAggregate(
                    id=uuid5(
                        NAMESPACE_URL,
                        f"{release_id}:{platform}:{typed_feature.feature_id}:{pattern_key}",
                    ),
                    tenant_id=items[0].tenant_id,
                    feature=typed_feature,
                    dimension=definition.dimension,
                    pattern_key=pattern_key,
                    label=items[0].label,
                    platform=platform,
                    supporting_observation_ids=tuple(item.id for item in sampled),
                    supporting_evidence_ids=tuple(
                        sorted(
                            {evidence_id for item in sampled for evidence_id in item.evidence_ids},
                            key=lambda value: value.int,
                        )[:25]
                    ),
                    support_count=len(items),
                    leader_count=len(leaders),
                    prevalence=len(items) / len(platform_documents[platform]),
                    mean_performance=mean,
                    platform_mean_performance=platform_mean,
                    observed_relative_difference=(
                        (mean - platform_mean) / platform_mean if platform_mean > 0 else None
                    ),
                    standard_error=(stdev(scores) / sqrt(len(scores)) if len(scores) > 1 else None),
                    comparable_fraction=comparable,
                    earliest_publication=earliest,
                    latest_publication=latest,
                    authority=authority,
                )
            )
        return tuple(sorted(aggregates, key=lambda item: item.id.int))
