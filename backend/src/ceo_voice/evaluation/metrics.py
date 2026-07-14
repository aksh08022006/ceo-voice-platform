"""Small helpers for consistent metric construction and aggregation."""

from collections.abc import Iterable
from statistics import fmean
from uuid import UUID

from pydantic import JsonValue

from .contracts import DimensionScore, EvaluationMetric, EvaluationPolicy
from .enums import EvaluationDimension, MetricSource


def metric(
    metric_id: str,
    dimension: EvaluationDimension,
    score: float,
    explanation: str,
    policy: EvaluationPolicy,
    *,
    source: MetricSource = MetricSource.DETERMINISTIC,
    applicable: bool = True,
    evidence: tuple[UUID, ...] = (),
    diagnostics: dict[str, JsonValue] | None = None,
) -> EvaluationMetric:
    normalized = max(0.0, min(1.0, score))
    return EvaluationMetric(
        metric_id=metric_id,
        dimension=dimension,
        source=source,
        score=normalized,
        passed=(not applicable) or normalized >= policy.metric_pass_score,
        applicable=applicable,
        explanation=explanation,
        evidence_references=evidence,
        diagnostics=diagnostics or {},
    )


def dimension_score(
    dimension: EvaluationDimension,
    metrics: Iterable[EvaluationMetric],
    policy: EvaluationPolicy,
) -> DimensionScore:
    values = tuple(metrics)
    applicable = tuple(item for item in values if item.applicable)
    score = fmean(item.score for item in applicable) if applicable else 1.0
    return DimensionScore(
        dimension=dimension,
        score=score,
        passed=score >= policy.dimension_pass_score and all(item.passed for item in applicable),
        metrics=values,
        summary=(
            f"{len(applicable)} applicable metrics produced a deterministic score of {score:.3f}."
        ),
    )
