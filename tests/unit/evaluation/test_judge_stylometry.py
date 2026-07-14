"""Structured judge isolation and supported stylometric primitive tests."""

import asyncio
import json
from collections.abc import Iterable

import pytest

from ceo_voice.core.exceptions import EvaluationError, ProviderError
from ceo_voice.evaluation import EvaluationEngine, JudgePolicy, StructuredLLMJudge
from ceo_voice.evaluation.enums import EvaluationDimension, MetricSource
from ceo_voice.evaluation.stylometry import (
    factual_anchors,
    lexical_overlap,
    ngram_overlap,
    numeric_target,
    proportional_similarity,
    style_measurements,
)
from ceo_voice.generation.contracts import ProviderRequest, ProviderResult, TokenUsage
from ceo_voice.generation.enums import ProviderName
from tests.unit.evaluation.test_engine import evaluation_input


class JudgeProvider:
    name = ProviderName.OPENAI

    def __init__(self, outcomes: Iterable[str | ProviderError]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, ProviderError):
            raise outcome
        return ProviderResult(
            text=outcome,
            provider=self.name,
            model=request.model,
            provider_request_id="judge-1",
            usage=TokenUsage(input_tokens=120, output_tokens=40),
            latency_ms=8,
        )


def judge_json(*, evidence_references: list[str] | None = None) -> str:
    return json.dumps(
        {
            "dimensions": [
                {
                    "dimension": dimension.value,
                    "score": 0.75,
                    "rationale": "Observable evidence is broadly aligned.",
                    "evidence_references": evidence_references or [],
                }
                for dimension in EvaluationDimension
            ],
            "recommendation": "revise",
            "limitations": ["No human authenticity review was supplied."],
        }
    )


def test_structured_judge_is_provider_neutral_separate_and_traceable() -> None:
    provider = JudgeProvider((judge_json(),))
    judge = StructuredLLMJudge(
        provider,
        policy=JudgePolicy(provider=ProviderName.OPENAI, model="judge-model"),
    )
    report = asyncio.run(EvaluationEngine(judge=judge).evaluate(evaluation_input()))

    assert report.judge_review is not None
    assert report.judge_review.dimensions[0].score == 0.75
    assert report.judge_review.input_tokens == 120
    assert all(
        item.source is not MetricSource.LLM_JUDGE
        for dimension in report.dimensions
        for item in dimension.metrics
    ), "judge does not affect authoritative score by default"
    assert "hidden chain-of-thought" in provider.requests[0].system
    assert "voice_targets" in provider.requests[0].user


def test_judge_can_be_explicitly_included_and_retries_transient_failure() -> None:
    provider = JudgeProvider((ProviderError("temporary", retryable=True), judge_json()))
    judge = StructuredLLMJudge(
        provider,
        policy=JudgePolicy(
            provider=ProviderName.OPENAI,
            model="judge-model",
            maximum_retries=1,
        ),
    )
    from ceo_voice.evaluation import EvaluationPolicy

    report = asyncio.run(
        EvaluationEngine(
            judge=judge,
            policy=EvaluationPolicy(judge_contributes_to_score=True),
        ).evaluate(evaluation_input())
    )

    assert len(provider.requests) == 2
    assert any(
        item.source is MetricSource.LLM_JUDGE
        for dimension in report.dimensions
        for item in dimension.metrics
    )


def test_invalid_judge_output_and_policy_mismatch_fail_closed() -> None:
    provider = JudgeProvider(("not json",))
    judge = StructuredLLMJudge(
        provider,
        policy=JudgePolicy(provider=ProviderName.OPENAI, model="judge-model"),
    )
    with pytest.raises(EvaluationError, match="invalid structured"):
        asyncio.run(judge.evaluate(evaluation_input()))
    with pytest.raises(ValueError, match="agree"):
        StructuredLLMJudge(
            provider,
            policy=JudgePolicy(provider=ProviderName.ANTHROPIC, model="judge-model"),
        )


def test_judge_cannot_cite_evidence_outside_the_bundle() -> None:
    payload = judge_json(evidence_references=["00000000-0000-0000-0000-000000000001"])
    judge = StructuredLLMJudge(
        JudgeProvider((payload,)),
        policy=JudgePolicy(provider=ProviderName.OPENAI, model="judge-model"),
    )
    with pytest.raises(EvaluationError, match="outside"):
        asyncio.run(judge.evaluate(evaluation_input()))


def test_stylometric_primitives_are_bounded_and_observable() -> None:
    text = "Acme Corp grew 42%.\n\nWHY now? Visit https://example.com #launch @team."
    values = style_measurements(text, thread_posts=2)

    assert values["analysis.thread-length"] == 2
    assert values["analysis.paragraph-count"] == 2
    assert values["analysis.question-frequency"] > 0
    assert values["analysis.uppercase-word-ratio"] > 0
    assert proportional_similarity(10, 10) == 1
    assert proportional_similarity(0, 10) == 0
    assert numeric_target({"value": 2, "unit": "x"}) == 2
    assert numeric_target(True) is None
    assert lexical_overlap("clear ownership", ("ownership matters",)) == 0.5
    assert ngram_overlap("a b c d", ("a b c d",)) == 1
    anchors = factual_anchors(text)
    assert "Acme Corp" in anchors
    assert "42%" in anchors
    assert "https://example.com" in anchors
