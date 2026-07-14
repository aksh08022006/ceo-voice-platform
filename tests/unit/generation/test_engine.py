"""Prompt-last orchestration, retry, validation, and reporting tests."""

import asyncio
from collections.abc import Iterable

import pytest

from ceo_voice.core.exceptions import GenerationValidationError, PromptBudgetError, ProviderError
from ceo_voice.generation import (
    GenerationEngine,
    GenerationInput,
    GenerationPolicy,
    OutputValidator,
    PromptBuilder,
    PromptRenderer,
    TokenBudgetManager,
)
from ceo_voice.generation.contracts import (
    PromptSection,
    ProviderRequest,
    ProviderResult,
    TokenUsage,
)
from ceo_voice.generation.enums import AttemptKind, PromptSectionKind, ProviderName, ValidationCode
from ceo_voice.retrieval import InMemoryEvidenceMaterialReader, RetrievalIntelligenceEngine
from tests.unit.retrieval.test_engine import _input as retrieval_input


class FakeProvider:
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
            provider_request_id="provider-1",
            usage=TokenUsage(input_tokens=100, output_tokens=30),
            latency_ms=20,
        )


def _generation_input() -> GenerationInput:
    source, materials = retrieval_input(with_supplied_evidence=True)
    bundle = asyncio.run(
        RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(materials)).retrieve(source)
    )
    return GenerationInput(
        request=source.request,
        context=source.context,
        retrieval=bundle,
        generated_at=source.retrieved_at,
    )


def _engine(provider: FakeProvider, **changes: object) -> GenerationEngine:
    policy = GenerationPolicy(
        provider=ProviderName.OPENAI,
        model="test-model",
        model_context_tokens=10_000,
        maximum_output_tokens=500,
        **changes,
    )
    budget = TokenBudgetManager(policy)
    return GenerationEngine(
        provider,
        PromptBuilder(budget),
        PromptRenderer(budget),
        OutputValidator(),
        policy=policy,
    )


def test_generation_uses_bundle_without_persona_impersonation_and_reports_lineage() -> None:
    provider = FakeProvider(("Ownership creates speed.\n\nClear decisions compound.",))
    value = _generation_input()

    draft = asyncio.run(_engine(provider).generate(value))

    assert draft.content.startswith("Ownership")
    assert draft.report.retrieval_bundle_id == value.retrieval.bundle_id
    assert draft.report.selected_evidence_ids
    assert draft.report.voice_feature_ids
    assert draft.report.structural_pattern_ids
    assert draft.report.total_usage == TokenUsage(input_tokens=100, output_tokens=30)
    assert "You are" not in provider.requests[0].system
    assert "impersonate" in provider.requests[0].system
    assert "[VOICE]" in provider.requests[0].user
    assert "[STRUCTURE]" in provider.requests[0].user
    assert "[EVIDENCE]" in provider.requests[0].user


def test_transient_provider_retry_reuses_the_same_prompt() -> None:
    provider = FakeProvider(
        (ProviderError("rate limited", retryable=True), "A concise valid post.")
    )
    draft = asyncio.run(_engine(provider).generate(_generation_input()))

    assert len(provider.requests) == 2
    assert provider.requests[0] == provider.requests[1]
    assert draft.report.attempts[1].kind is AttemptKind.PROVIDER_RETRY


def test_validation_retry_adds_only_targeted_repair_feedback() -> None:
    provider = FakeProvider(("x" * 4000, "A valid repaired post."))
    draft = asyncio.run(_engine(provider).generate(_generation_input()))

    assert draft.report.attempts[0].validation is not None
    assert draft.report.attempts[0].validation.valid is False
    assert draft.report.attempts[1].kind is AttemptKind.VALIDATION_REPAIR
    assert "[REPAIR]" not in provider.requests[0].user
    assert "[REPAIR]" in provider.requests[1].user


def test_invalid_output_fails_after_configured_repair_limit() -> None:
    provider = FakeProvider(("x" * 4000,))
    with pytest.raises(GenerationValidationError, match="valid draft"):
        asyncio.run(_engine(provider, maximum_validation_retries=0).generate(_generation_input()))


def test_mismatched_context_is_rejected_before_provider_call() -> None:
    provider = FakeProvider(("unused",))
    value = _generation_input()
    invalid = value.model_copy(
        update={
            "request": value.request.model_copy(update={"request_id": value.retrieval.bundle_id})
        }
    )
    with pytest.raises(Exception, match="incompatible"):
        asyncio.run(_engine(provider).generate(invalid))
    assert not provider.requests


def test_budget_and_output_policy_fail_closed() -> None:
    policy = GenerationPolicy(
        provider=ProviderName.OPENAI,
        model="test-model",
        model_context_tokens=512,
        maximum_output_tokens=100,
    )
    budget = TokenBudgetManager(policy)
    mandatory = PromptSection(
        kind=PromptSectionKind.SYSTEM,
        content="x" * 2000,
        mandatory=True,
        priority=100,
    )
    with pytest.raises(PromptBudgetError, match="mandatory"):
        budget.fit((mandatory,), ())

    value = _generation_input()
    constrained = value.model_copy(
        update={
            "request": value.request.model_copy(update={"constraints": ("must include: flywheel",)})
        }
    )
    result = OutputValidator().validate("first\n---\nsecond", constrained, policy)
    assert result.valid is False
    assert {item.code for item in result.findings} >= {
        ValidationCode.THREAD_NOT_SUPPORTED,
        ValidationCode.REQUIRED_CONSTRAINT,
    }


def test_nonretryable_provider_failure_is_propagated() -> None:
    provider = FakeProvider((ProviderError("bad request", retryable=False),))
    with pytest.raises(ProviderError, match="bad request"):
        asyncio.run(_engine(provider).generate(_generation_input()))
