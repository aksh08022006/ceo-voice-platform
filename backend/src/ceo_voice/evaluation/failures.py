"""Stable failure classification from independent dimension metrics."""

from ceo_voice.models.enums import EvaluationStatus

from .contracts import DimensionScore, EvaluationFailure
from .enums import EvaluationDimension, FailureCategory

_FAILURES = {
    EvaluationDimension.VOICE_FIDELITY: (
        FailureCategory.VOICE_DRIFT,
        "Review low-scoring HVM features and selected voice evidence.",
    ),
    EvaluationDimension.STRUCTURAL_FIDELITY: (
        FailureCategory.STRUCTURAL_MISALIGNMENT,
        "Inspect the mismatched VKR pattern classifications.",
    ),
    EvaluationDimension.CONSTRAINT_COMPLIANCE: (
        FailureCategory.CONSTRAINT_VIOLATION,
        "Repair the listed enforceable constraints before publication.",
    ),
    EvaluationDimension.PLATFORM_COMPLIANCE: (
        FailureCategory.PLATFORM_VIOLATION,
        "Regenerate or edit to the pinned platform contract.",
    ),
    EvaluationDimension.FACTUAL_PRESERVATION: (
        FailureCategory.FACTUAL_RISK,
        "Verify unsupported anchors against approved factual evidence.",
    ),
    EvaluationDimension.EDIT_PRESERVATION: (
        FailureCategory.EDIT_DRIFT,
        "Reduce Re-Voice changes and inspect protected regions.",
    ),
    EvaluationDimension.READABILITY: (
        FailureCategory.READABILITY_DEGRADATION,
        "Inspect sentence length and whitespace diagnostics.",
    ),
}


class FailureAnalyzer:
    def classify(self, dimensions: tuple[DimensionScore, ...]) -> tuple[EvaluationFailure, ...]:
        failures = []
        for dimension in dimensions:
            if dimension.passed:
                continue
            category, action = _FAILURES[dimension.dimension]
            failed = tuple(item.metric_id for item in dimension.metrics if not item.passed)
            severity = (
                EvaluationStatus.FAIL
                if dimension.dimension
                in {
                    EvaluationDimension.CONSTRAINT_COMPLIANCE,
                    EvaluationDimension.PLATFORM_COMPLIANCE,
                    EvaluationDimension.FACTUAL_PRESERVATION,
                }
                else EvaluationStatus.WARNING
            )
            failures.append(
                EvaluationFailure(
                    category=category,
                    severity=severity,
                    message=f"{dimension.dimension.value} did not meet its evaluation threshold.",
                    metric_ids=failed,
                    recommended_action=action,
                )
            )
            failed_ids = set(failed)
            if "voice.evidence_coverage" in failed_ids:
                failures.append(
                    EvaluationFailure(
                        category=FailureCategory.INSUFFICIENT_EVIDENCE,
                        severity=EvaluationStatus.WARNING,
                        message="Selected voice evidence does not cover the compiled feature set.",
                        metric_ids=("voice.evidence_coverage",),
                        recommended_action="Improve retrieval coverage before making a fidelity claim.",
                    )
                )
            if "voice.feature_target_observability" in failed_ids:
                failures.append(
                    EvaluationFailure(
                        category=FailureCategory.UNSUPPORTED_GENERATION,
                        severity=EvaluationStatus.WARNING,
                        message="The evaluator cannot measure one or more generated voice targets.",
                        metric_ids=("voice.feature_target_observability",),
                        recommended_action="Add a validated analyzer before scoring this voice feature.",
                    )
                )
        return tuple(failures)
