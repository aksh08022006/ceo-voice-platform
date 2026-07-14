"""Independent single, batch, benchmark, and regression evaluation orchestration."""

import asyncio
from statistics import fmean
from uuid import NAMESPACE_URL, uuid5

from ceo_voice.core.exceptions import EvaluationError
from ceo_voice.models.enums import EvaluationStatus
from ceo_voice.revoice import ReVoicedDraft
from ceo_voice.utils.hashing import sha256_text

from .compliance import ComplianceEvaluator
from .contracts import (
    BatchEvaluationReport,
    BenchmarkCaseResult,
    BenchmarkReport,
    BenchmarkSuite,
    DimensionScore,
    EvaluationInput,
    EvaluationMetric,
    EvaluationPolicy,
    EvaluationReport,
    RegressionDelta,
    RegressionReport,
)
from .enums import BenchmarkStatus, EvaluationDimension, MetricSource
from .failures import FailureAnalyzer
from .judge import StructuredLLMJudge
from .metrics import dimension_score, metric
from .preservation import PreservationEvaluator
from .structure import StructuralFidelityEvaluator
from .voice import VoiceFidelityEvaluator


class EvaluationEngine:
    """Evaluate outputs without writing to or influencing generation subsystems."""

    def __init__(
        self,
        *,
        policy: EvaluationPolicy | None = None,
        judge: StructuredLLMJudge | None = None,
    ) -> None:
        self._policy = policy or EvaluationPolicy()
        self._judge = judge
        self._voice = VoiceFidelityEvaluator()
        self._structure = StructuralFidelityEvaluator()
        self._compliance = ComplianceEvaluator()
        self._preservation = PreservationEvaluator()
        self._failures = FailureAnalyzer()

    async def evaluate(self, value: EvaluationInput) -> EvaluationReport:
        self._validate_input(value)
        judge_review = await self._judge.evaluate(value) if self._judge is not None else None
        measurements = [
            *self._voice.evaluate(value, self._policy),
            *self._structure.evaluate(value, self._policy),
            *self._compliance.evaluate(value, self._policy),
            *self._preservation.evaluate(value, self._policy),
            *self._human_metrics(value),
        ]
        if judge_review is not None and self._policy.judge_contributes_to_score:
            measurements.extend(
                metric(
                    f"judge.{item.dimension.value}",
                    item.dimension,
                    item.score,
                    item.rationale,
                    self._policy,
                    source=MetricSource.LLM_JUDGE,
                    evidence=item.evidence_references,
                )
                for item in judge_review.dimensions
            )
        dimensions = tuple(
            dimension_score(
                dimension,
                (item for item in measurements if item.dimension is dimension),
                self._policy,
            )
            for dimension in EvaluationDimension
        )
        overall = self._overall(dimensions)
        failures = self._failures.classify(dimensions)
        status = self._status(overall, dimensions, failures)
        hvm = value.voice_profile.managed_release.release
        vkr = value.virality_profile.publication.release
        report_id = uuid5(
            NAMESPACE_URL,
            ":".join(
                (
                    "evaluation",
                    str(value.draft.id),
                    str(value.context.context_id),
                    str(self._policy.version),
                    sha256_text(value.draft.content),
                )
            ),
        )
        evidence = tuple(
            sorted(
                {
                    reference
                    for dimension in dimensions
                    for item in dimension.metrics
                    for reference in item.evidence_references
                },
                key=lambda item: item.int,
            )
        )
        improvements = tuple(dict.fromkeys(item.recommended_action for item in failures))
        return EvaluationReport(
            report_id=report_id,
            candidate_id=value.draft.id,
            evaluator_version=self._policy.version,
            status=status,
            overall_score=overall,
            dimensions=dimensions,
            judge_review=judge_review,
            human_reviews=value.human_reviews,
            failures=failures,
            evidence_references=evidence,
            context_id=value.context.context_id,
            retrieval_bundle_id=value.retrieval.bundle_id,
            hvm_release_id=hvm.id,
            vkr_release_id=vkr.id,
            recommended_improvements=improvements,
            evaluated_at=value.evaluated_at,
        )

    async def evaluate_batch(self, values: tuple[EvaluationInput, ...]) -> BatchEvaluationReport:
        reports = tuple(await asyncio.gather(*(self.evaluate(item) for item in values)))
        return BatchEvaluationReport(
            reports=reports,
            mean_score=fmean(item.overall_score for item in reports) if reports else 0,
            passed=sum(item.status is EvaluationStatus.PASS for item in reports),
            warned=sum(item.status is EvaluationStatus.WARNING for item in reports),
            failed=sum(item.status is EvaluationStatus.FAIL for item in reports),
        )

    async def evaluate_benchmark(self, suite: BenchmarkSuite) -> BenchmarkReport:
        case_reports = await self.evaluate_batch(
            tuple(item.evaluation_input for item in suite.cases)
        )
        results = []
        for case, report in zip(suite.cases, case_reports.reports, strict=True):
            regressions = []
            if report.overall_score < case.expectation.minimum_overall_score:
                regressions.append("overall_score")
            scores = {item.dimension: item.score for item in report.dimensions}
            regressions.extend(
                dimension.value
                for dimension, minimum in case.expectation.minimum_dimension_scores.items()
                if scores[dimension] < minimum
            )
            status = BenchmarkStatus.REGRESSED if regressions else BenchmarkStatus.PASSED
            results.append(
                BenchmarkCaseResult(
                    case_id=case.case_id,
                    leader_label=case.leader_label,
                    report=report,
                    status=status,
                    regressions=tuple(regressions),
                )
            )
        status = (
            BenchmarkStatus.REGRESSED
            if any(item.status is BenchmarkStatus.REGRESSED for item in results)
            else BenchmarkStatus.PASSED
        )
        return BenchmarkReport(
            suite_id=suite.suite_id,
            suite_version=suite.version,
            cases=tuple(results),
            status=status,
            mean_score=fmean(item.report.overall_score for item in results),
        )

    def _human_metrics(self, value: EvaluationInput) -> tuple[EvaluationMetric, ...]:
        return tuple(
            metric(
                f"human.{review.review_id}.{rating.dimension.value}",
                rating.dimension,
                rating.score,
                rating.rationale,
                self._policy,
                source=MetricSource.HUMAN_REVIEW,
            )
            for review in value.human_reviews
            for rating in review.ratings
        )

    def _overall(self, dimensions: tuple[DimensionScore, ...]) -> float:
        applicable = tuple(
            item
            for item in dimensions
            if any(metric_value.applicable for metric_value in item.metrics)
        )
        mass = sum(self._policy.dimension_weights[item.dimension] for item in applicable)
        return (
            sum(item.score * self._policy.dimension_weights[item.dimension] for item in applicable)
            / mass
            if mass
            else 0
        )

    def _status(
        self,
        overall: float,
        dimensions: tuple[DimensionScore, ...],
        failures: tuple[object, ...],
    ) -> EvaluationStatus:
        del failures
        blocking = {
            EvaluationDimension.CONSTRAINT_COMPLIANCE,
            EvaluationDimension.PLATFORM_COMPLIANCE,
            EvaluationDimension.FACTUAL_PRESERVATION,
        }
        if any(not item.passed and item.dimension in blocking for item in dimensions):
            return EvaluationStatus.FAIL
        if overall < self._policy.warning_score:
            return EvaluationStatus.FAIL
        if overall < self._policy.minimum_overall_score or any(
            not item.passed
            for item in dimensions
            if any(metric.applicable for metric in item.metrics)
        ):
            return EvaluationStatus.WARNING
        return EvaluationStatus.PASS

    @staticmethod
    def _validate_input(value: EvaluationInput) -> None:
        hvm = value.voice_profile.managed_release.release
        vkr = value.virality_profile.publication.release
        draft_bundle = value.draft.report.retrieval_bundle_id
        draft_checks = (
            (
                (
                    value.draft.report.context_id == value.context.context_id,
                    "revoice_context",
                ),
                (
                    value.draft.report.hvm_release_id == hvm.id,
                    "revoice_hvm_release",
                ),
                (
                    value.draft.report.vkr_release_id == vkr.id,
                    "revoice_vkr_release",
                ),
            )
            if isinstance(value.draft, ReVoicedDraft)
            else ((value.draft.request_id == value.context.intent.request_id, "draft_request"),)
        )
        checks = (
            (draft_bundle == value.retrieval.bundle_id, "draft_retrieval"),
            (value.retrieval.source_context_id == value.context.context_id, "context"),
            (value.retrieval.source_context_hash == value.context.content_hash, "context_hash"),
            (value.context.voice.release_id == hvm.id, "hvm_release"),
            (value.context.voice.release_content_hash == hvm.content_hash, "hvm_hash"),
            (value.context.virality.release_id == vkr.id, "vkr_release"),
            (value.context.virality.release_content_hash == vkr.content_hash, "vkr_hash"),
            (
                all(review.candidate_id == value.draft.id for review in value.human_reviews),
                "human_review_candidate",
            ),
            *draft_checks,
        )
        for valid, boundary in checks:
            if not valid:
                raise EvaluationError(
                    "evaluation artifacts are incompatible", details={"boundary": boundary}
                )


class RegressionComparator:
    """Compare current reports with exact candidate baselines under an explicit tolerance."""

    def compare(
        self,
        previous: tuple[EvaluationReport, ...],
        current: tuple[EvaluationReport, ...],
        *,
        tolerance: float = 0.02,
    ) -> RegressionReport:
        if not 0 <= tolerance <= 1:
            raise ValueError("regression tolerance must be between zero and one")
        baseline = {item.candidate_id: item for item in previous}
        deltas = []
        for report in current:
            old = baseline.get(report.candidate_id)
            if old is None:
                raise EvaluationError(
                    "regression baseline is missing a candidate",
                    details={"candidate_id": str(report.candidate_id)},
                )
            old_dimensions = {item.dimension: item.score for item in old.dimensions}
            regressed = tuple(
                item.dimension
                for item in report.dimensions
                if item.score < old_dimensions[item.dimension] - tolerance
            )
            deltas.append(
                RegressionDelta(
                    candidate_id=report.candidate_id,
                    previous_score=old.overall_score,
                    current_score=report.overall_score,
                    delta=report.overall_score - old.overall_score,
                    regressed_dimensions=regressed,
                )
            )
        status = (
            BenchmarkStatus.REGRESSED
            if any(item.delta < -tolerance or item.regressed_dimensions for item in deltas)
            else BenchmarkStatus.PASSED
        )
        return RegressionReport(status=status, tolerance=tolerance, deltas=tuple(deltas))
