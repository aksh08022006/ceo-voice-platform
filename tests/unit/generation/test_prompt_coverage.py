"""Prompt compression must retain evidence for every governed generation decision."""

import asyncio
from uuid import UUID

import pytest

from ceo_voice.core.exceptions import PromptBudgetError
from ceo_voice.generation import (
    GenerationEngine,
    GenerationPolicy,
    OutputValidator,
    PromptBuilder,
    PromptRenderer,
    TokenBudgetManager,
)
from ceo_voice.generation.enums import PromptSectionKind, ProviderName
from ceo_voice.retrieval.enums import EvidencePurpose
from ceo_voice.utils.hashing import sha256_text
from tests.unit.generation.test_engine import FakeProvider, _generation_input


def _policy(context_tokens: int = 20_000) -> GenerationPolicy:
    return GenerationPolicy(
        provider=ProviderName.OPENAI,
        model="test-model",
        model_context_tokens=context_tokens,
        maximum_output_tokens=100,
    )


def test_tight_prompt_keeps_every_voice_structure_and_factual_requirement() -> None:
    value = _generation_input()
    generous_budget = TokenBudgetManager(_policy())
    generous = PromptBuilder(generous_budget).build(value)
    mandatory = tuple(section for section in generous.sections if section.mandatory)
    required_cost = sum(generous_budget.section_cost(section) for section in mandatory)
    budget = TokenBudgetManager(_policy(required_cost + 100))
    prompt = PromptBuilder(budget).build(value)
    retained = set(prompt.included_evidence_ids)
    required = {
        *(f"voice:{item.feature_id}" for item in value.retrieval.voice_features),
        *(f"structure:{item.pattern_id}" for item in value.retrieval.structural_guidance),
        *(f"request:{lane.role.value}" for lane in value.context.evidence.lanes if lane.items),
    }
    supported = {
        requirement
        for item in value.retrieval.evidence
        if item.evidence_id in retained
        for requirement in item.explanation.requirements
    }
    assert required <= supported
    assert prompt.pruned_evidence_ids, "optional material should be pruned by this tight budget"
    assert len(retained) < len(required), "shared support should avoid one span per requirement"
    assert all(section.mandatory for section in prompt.sections)
    rendered = PromptRenderer(budget).render(prompt)
    assert rendered.estimated_input_tokens <= required_cost


def test_unaffordable_required_coverage_stops_before_the_provider_call() -> None:
    value = _generation_input()
    generous_budget = TokenBudgetManager(_policy())
    generous = PromptBuilder(generous_budget).build(value)
    required_cost = sum(
        generous_budget.section_cost(section) for section in generous.sections if section.mandatory
    )
    policy = _policy(required_cost + 99)
    budget = TokenBudgetManager(policy)
    provider = FakeProvider(("unused",))
    engine = GenerationEngine(
        provider,
        PromptBuilder(budget),
        PromptRenderer(budget),
        OutputValidator(),
        policy=policy,
    )
    with pytest.raises(PromptBudgetError, match="mandatory"):
        asyncio.run(engine.generate(value))
    assert provider.requests == []


def test_prompt_rejects_missing_fact_lane_support_even_when_other_purposes_exist() -> None:
    value = _generation_input()
    value = value.model_copy(
        update={
            "retrieval": value.retrieval.model_copy(
                update={
                    "evidence": tuple(
                        item
                        for item in value.retrieval.evidence
                        if EvidencePurpose.FACTUAL_SUPPORT not in item.purposes
                    )
                }
            )
        }
    )
    with pytest.raises(PromptBudgetError, match="missing") as caught:
        PromptBuilder(TokenBudgetManager(_policy())).build(value)
    requirements = caught.value.details["requirements"]
    assert isinstance(requirements, list)
    assert "request:factual_evidence" in requirements


def test_prompt_preserves_multiple_required_voice_examples_and_prefers_compact_support() -> None:
    value = _generation_input()
    voice = next(
        item for item in value.retrieval.evidence if EvidencePurpose.VOICE_SUPPORT in item.purposes
    )
    compact = voice.model_copy(
        update={
            "evidence_id": UUID(int=999_001),
            "content": "Compact voice example.",
            "content_hash": sha256_text("Compact voice example."),
            "rank": len(value.retrieval.evidence) + 1,
        }
    )
    bundle = value.retrieval.model_copy(update={"evidence": (*value.retrieval.evidence, compact)})
    prompt = PromptBuilder(TokenBudgetManager(_policy())).build(
        value.model_copy(update={"retrieval": bundle})
    )
    reserved = {
        section.source_ids[0]
        for section in prompt.sections
        if section.kind is PromptSectionKind.EVIDENCE and section.mandatory
    }
    assert compact.evidence_id in reserved and voice.evidence_id not in reserved
    bundle = bundle.model_copy(
        update={
            "metadata": bundle.metadata.model_copy(
                update={
                    "budget": bundle.metadata.budget.model_copy(
                        update={"minimum_voice_evidence_per_feature": 2}
                    )
                }
            )
        }
    )
    prompt = PromptBuilder(TokenBudgetManager(_policy())).build(
        value.model_copy(update={"retrieval": bundle})
    )
    reserved = {
        section.source_ids[0]
        for section in prompt.sections
        if section.kind is PromptSectionKind.EVIDENCE and section.mandatory
    }
    assert {compact.evidence_id, voice.evidence_id} <= reserved
