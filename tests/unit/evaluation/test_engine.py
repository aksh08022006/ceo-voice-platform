"""Independent dimension scoring, failures, batches, benchmarks, and regressions."""

import asyncio
from typing import Any, cast
from uuid import UUID

import pytest

from ceo_voice.context import CompiledConstraint
from ceo_voice.context.enums import (
    ConstraintCategory,
    ConstraintOperator,
    ConstraintStrength,
)
from ceo_voice.core.exceptions import EvaluationError
from ceo_voice.evaluation import (
    BenchmarkCase,
    BenchmarkExpectation,
    BenchmarkSuite,
    EvaluationEngine,
    EvaluationInput,
    EvaluationPolicy,
    HumanReview,
    RegressionComparator,
    render_evaluation_report,
)
from ceo_voice.evaluation.contracts import EvaluationVersion, HumanDimensionRating
from ceo_voice.evaluation.enums import (
    BenchmarkStatus,
    EvaluationDimension,
    FailureCategory,
    MetricSource,
    ReviewRecommendation,
)
from ceo_voice.generation import GeneratedDraft
from ceo_voice.generation.contracts import GenerationReport, OutputValidation
from ceo_voice.models.enums import EvaluationStatus
from ceo_voice.retrieval import InMemoryEvidenceMaterialReader, RetrievalIntelligenceEngine
from tests.unit.retrieval.test_engine import _input as retrieval_input
from tests.unit.revoice.test_engine import FakeProvider, revoice_input
from tests.unit.revoice.test_engine import engine as revoice_engine

GOOD_CONTENT = (
    "Why does ownership matter?\n\n"
    "The problem is delay.\n\n"
    "The solution is clarity.\n\n"
    "What would you change?"
)


def evaluation_input(content: str = GOOD_CONTENT) -> EvaluationInput:
    source, materials = retrieval_input(with_supplied_evidence=True)
    bundle = asyncio.run(
        RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(materials)).retrieve(source)
    )
    validation = OutputValidation(
        valid=True,
        findings=(),
        character_count=len(content),
        thread_posts=1,
    )
    report = GenerationReport.model_construct(
        **cast(
            Any,
            {
                "retrieval_bundle_id": bundle.bundle_id,
                "final_validation": validation,
            },
        )
    )
    draft = GeneratedDraft(
        id=UUID(int=9801),
        request_id=source.request.request_id,
        content=content,
        thread=(content,),
        report=report,
        created_at=source.retrieved_at,
    )
    return EvaluationInput(
        draft=draft,
        context=source.context,
        retrieval=bundle,
        voice_profile=source.voice_profile,
        virality_profile=source.virality_profile,
        evaluated_at=source.retrieved_at,
    )


def test_single_evaluation_is_repeatable_explainable_and_traceable() -> None:
    value = evaluation_input()
    evaluator = EvaluationEngine()

    first = asyncio.run(evaluator.evaluate(value))
    second = asyncio.run(evaluator.evaluate(value))

    assert first == second
    assert first.report_id == second.report_id
    assert tuple(item.dimension for item in first.dimensions) == tuple(EvaluationDimension)
    assert first.context_id == value.context.context_id
    assert first.retrieval_bundle_id == value.retrieval.bundle_id
    assert first.evidence_references
    assert first.judge_review is None
    assert any(
        item.category is FailureCategory.VOICE_DRIFT for item in first.failures
    ), "fixture HVM feature is intentionally unsupported by Tier-1 stylometry"
    structure = next(
        item
        for item in first.dimensions
        if item.dimension is EvaluationDimension.STRUCTURAL_FIDELITY
    )
    assert structure.score == 1
    rendered = render_evaluation_report(first)
    assert "# Evaluation" in rendered
    assert "HVM release" in rendered


def test_platform_and_constraint_failures_are_blocking_and_actionable() -> None:
    value = evaluation_input("x" * 3001)
    required = CompiledConstraint(
        constraint_id="test.must-include",
        category=ConstraintCategory.USER,
        strength=ConstraintStrength.HARD,
        operator=ConstraintOperator.INSTRUCTION,
        key="user.instruction.test",
        value="must include: flywheel",
        priority=100,
        source="test",
        rationale="test",
    )
    context = value.context.model_copy(
        update={
            "constraints": value.context.constraints.model_copy(
                update={"constraints": (*value.context.constraints.constraints, required)}
            )
        }
    )

    report = asyncio.run(EvaluationEngine().evaluate(value.model_copy(update={"context": context})))

    assert report.status is EvaluationStatus.FAIL
    categories = {item.category for item in report.failures}
    assert FailureCategory.PLATFORM_VIOLATION in categories
    assert FailureCategory.CONSTRAINT_VIOLATION in categories
    assert report.recommended_improvements


def test_revoice_output_receives_edit_and_factual_preservation_dimensions() -> None:
    source = revoice_input(
        original="We build quickly.\n\nOwnership drives progress.\n\nTell me what you think?",
        edited="We build quickly.\n\nOwnership creates momentum.\n\nTell me what you think?",
    )
    provider = FakeProvider(
        ("We build quickly.\n\nOwnership compounds momentum.\n\nTell me what you think?",)
    )
    draft = asyncio.run(revoice_engine(provider).restore(source))
    value = EvaluationInput(
        draft=draft,
        context=source.context,
        retrieval=source.retrieval,
        voice_profile=source.voice_profile,
        virality_profile=source.virality_profile,
        edited_draft=source.edited_draft,
        evaluated_at=source.requested_at,
    )

    report = asyncio.run(EvaluationEngine().evaluate(value))

    edit = next(
        item
        for item in report.dimensions
        if item.dimension is EvaluationDimension.EDIT_PRESERVATION
    )
    factual = next(
        item
        for item in report.dimensions
        if item.dimension is EvaluationDimension.FACTUAL_PRESERVATION
    )
    assert edit.score > 0.9
    assert factual.score == 1
    assert any(item.metric_id == "edit.protected_region_preservation" for item in edit.metrics)


def test_batch_benchmark_and_regression_workflows() -> None:
    evaluator = EvaluationEngine()
    values = tuple(
        evaluation_input().model_copy(
            update={
                "draft": evaluation_input().draft.model_copy(update={"id": UUID(int=9900 + index)})
            }
        )
        for index in range(3)
    )
    batch = asyncio.run(evaluator.evaluate_batch(values))

    assert len(batch.reports) == 3
    assert batch.passed + batch.warned + batch.failed == 3
    suite = BenchmarkSuite(
        suite_id="ceo-core-regression",
        version=EvaluationVersion(major=1, minor=0, patch=0),
        cases=tuple(
            BenchmarkCase(
                case_id=f"case-{index}",
                leader_label=leader,
                evaluation_input=value,
                expectation=BenchmarkExpectation(
                    minimum_overall_score=0 if index < 2 else 1,
                ),
            )
            for index, (leader, value) in enumerate(
                zip(("Ali Ghodsi", "Matei Zaharia", "Jensen Huang"), values, strict=True)
            )
        ),
    )
    benchmark = asyncio.run(evaluator.evaluate_benchmark(suite))

    assert benchmark.status is BenchmarkStatus.REGRESSED
    assert tuple(item.leader_label for item in benchmark.cases) == (
        "Ali Ghodsi",
        "Matei Zaharia",
        "Jensen Huang",
    )
    assert benchmark.cases[-1].regressions == ("overall_score",)
    previous = batch.reports
    current = tuple(
        item.model_copy(update={"overall_score": max(0, item.overall_score - 0.1)})
        for item in previous
    )
    regression = RegressionComparator().compare(previous, current, tolerance=0.02)
    assert regression.status is BenchmarkStatus.REGRESSED
    assert all(item.delta < 0 for item in regression.deltas)


def test_empty_batch_and_regression_validation_are_explicit() -> None:
    batch = asyncio.run(EvaluationEngine().evaluate_batch(()))
    assert batch.mean_score == 0
    with pytest.raises(ValueError, match="tolerance"):
        RegressionComparator().compare((), (), tolerance=2)
    with pytest.raises(EvaluationError, match="missing"):
        RegressionComparator().compare(
            (), (asyncio.run(EvaluationEngine().evaluate(evaluation_input())),)
        )


def test_evaluation_rejects_mismatched_lineage() -> None:
    value = evaluation_input()
    invalid = value.context.model_copy(
        update={"voice": value.context.voice.model_copy(update={"release_id": UUID(int=123456)})}
    )
    with pytest.raises(EvaluationError, match="incompatible"):
        asyncio.run(EvaluationEngine().evaluate(value.model_copy(update={"context": invalid})))


def test_policy_requires_complete_nonnegative_weights() -> None:
    with pytest.raises(ValueError, match="every dimension"):
        EvaluationPolicy(dimension_weights={EvaluationDimension.VOICE_FIDELITY: 1})
    weights = dict.fromkeys(EvaluationDimension, 0.1)
    weights[EvaluationDimension.VOICE_FIDELITY] = -1
    with pytest.raises(ValueError, match="negative"):
        EvaluationPolicy(dimension_weights=weights)
    with pytest.raises(ValueError, match="warning"):
        EvaluationPolicy(warning_score=0.9, minimum_overall_score=0.8)


def test_candidate_bound_human_review_contributes_an_independent_metric() -> None:
    value = evaluation_input()
    review = HumanReview(
        review_id=UUID(int=77701),
        candidate_id=value.draft.id,
        reviewer_reference="reviewer:calibrated-panel-1",
        ratings=(
            HumanDimensionRating(
                dimension=EvaluationDimension.VOICE_FIDELITY,
                score=0.8,
                rationale="Cadence is recognizable without copying source phrases.",
            ),
        ),
        recommendation=ReviewRecommendation.ACCEPT,
        notes="Blind rubric review completed.",
        reviewed_at=value.evaluated_at,
    )
    report = asyncio.run(
        EvaluationEngine().evaluate(value.model_copy(update={"human_reviews": (review,)}))
    )
    voice = next(
        item for item in report.dimensions if item.dimension is EvaluationDimension.VOICE_FIDELITY
    )
    assert any(item.source is MetricSource.HUMAN_REVIEW for item in voice.metrics)
    with pytest.raises(ValueError, match="evaluated candidate"):
        EvaluationInput(
            draft=value.draft,
            context=value.context,
            retrieval=value.retrieval,
            voice_profile=value.voice_profile,
            virality_profile=value.virality_profile,
            evaluated_at=value.evaluated_at,
            human_reviews=(review.model_copy(update={"candidate_id": UUID(int=1)}),),
        )
