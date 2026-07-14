"""Deterministic comparison of structural patterns across immutable releases."""

from ceo_voice.models.base import UtcDatetime
from ceo_voice.virality.contracts import (
    ComparisonReport,
    PatternAggregate,
    PatternChange,
    ViralityRelease,
)
from ceo_voice.virality.enums import PatternChangeStatus


def compare_releases(
    previous: ViralityRelease,
    current: ViralityRelease,
    *,
    compared_at: UtcDatetime,
) -> ComparisonReport:
    """Compare compatible libraries without conflating pattern identity and performance."""

    if previous.tenant_id != current.tenant_id or previous.library_id != current.library_id:
        raise ValueError("virality release comparison requires one tenant and library")
    old = {_key(item): item for item in previous.patterns}
    new = {_key(item): item for item in current.patterns}
    changes: list[PatternChange] = []
    for key in sorted(set(old) | set(new), key=str):
        before = old.get(key)
        after = new.get(key)
        representative = after or before
        assert representative is not None
        if before is None:
            status = PatternChangeStatus.ADDED
        elif after is None:
            status = PatternChangeStatus.REMOVED
        elif _statistics(before) == _statistics(after):
            status = PatternChangeStatus.UNCHANGED
        else:
            status = PatternChangeStatus.CHANGED
        changes.append(
            PatternChange(
                feature=representative.feature,
                pattern_key=representative.pattern_key,
                platform=representative.platform,
                status=status,
                support_delta=(after.support_count if after else 0)
                - (before.support_count if before else 0),
                prevalence_delta=(after.prevalence if after else 0)
                - (before.prevalence if before else 0),
                performance_difference_delta=_optional_delta(
                    after.observed_relative_difference if after else None,
                    before.observed_relative_difference if before else None,
                ),
            )
        )
    return ComparisonReport(
        previous_release_id=previous.id,
        current_release_id=current.id,
        changes=tuple(changes),
        compared_at=compared_at,
    )


def _key(pattern: PatternAggregate) -> tuple[str, str, str, str]:
    return (
        pattern.feature.feature_id,
        str(pattern.feature.version),
        pattern.pattern_key,
        pattern.platform.value,
    )


def _statistics(pattern: PatternAggregate) -> tuple[object, ...]:
    return (
        pattern.support_count,
        pattern.leader_count,
        pattern.prevalence,
        pattern.mean_performance,
        pattern.platform_mean_performance,
        pattern.observed_relative_difference,
        pattern.comparable_fraction,
        pattern.authority,
    )


def _optional_delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return current - previous
