"""Brief fidelity guidance survives routing, evidence pruning, and targeted repair.

These contract tests do not measure a model's semantic compliance.
"""

import json
from uuid import UUID

import pytest

from ceo_voice.generation import PromptBuilder, PromptRenderer, TokenBudgetManager
from ceo_voice.generation.enums import PromptSectionKind
from tests.unit.generation.test_engine import _generation_input
from tests.unit.generation.test_prompt_coverage import _policy

_BRIEF = (
    "Reflect on the historical February 9, 2026 Databricks disclosure. "
    "Databricks reported surpassing a $5.4 billion revenue run-rate. "
    "This is NOT recognized annual revenue or today's results. "
    "Angle: durable engineering value matters behind a business milestone. "
    "Do not add causal proof, measured benefits, or firsthand memories."
)


@pytest.mark.parametrize("request_index", range(5))
def test_brief_prohibitions_remain_mandatory_across_request_ids_and_repair(
    request_index: int,
) -> None:
    value = _generation_input()
    explicit = ("Preserve reported attribution and historical status.", "Do not invent causality.")
    value = value.model_copy(
        update={
            "request": value.request.model_copy(
                update={
                    "topic": _BRIEF,
                    "constraints": explicit,
                    "request_id": UUID(int=request_index),
                }
            )
        }
    )
    feedback = ("output must contain at most 100 words",)
    generous_budget = TokenBudgetManager(_policy())
    generous = PromptBuilder(generous_budget).build(value, repair_feedback=feedback)
    required_cost = sum(
        generous_budget.section_cost(section) for section in generous.sections if section.mandatory
    )
    budget = TokenBudgetManager(_policy(required_cost + 100))
    prompt = PromptBuilder(budget).build(value, repair_feedback=feedback)
    assert prompt.pruned_evidence_ids
    request_section = next(s for s in prompt.sections if s.kind is PromptSectionKind.REQUEST)
    request = json.loads(request_section.content)
    assert request_section.mandatory
    assert request["topic"] == _BRIEF
    assert request["explicit_constraints"] == list(explicit)
    assert request["variation"]["variation_key"] == str(UUID(int=request_index))
    assert "composition_route" not in request["variation"]
    repair = json.loads(
        next(s.content for s in prompt.sections if s.kind is PromptSectionKind.REPAIR)
    )
    assert repair["preserve_all_other_requirements"] is True
    assert repair["repair_only_these_validation_failures"] == list(feedback)
    rendered = PromptRenderer(budget).render(prompt)
    assert "post for editorial review" in rendered.system
    assert "An argument is not proof of a result" in rendered.system
    assert "remove any sentence that introduces an unsupported real-world claim" in rendered.system
    assert "uncertainty, attribution, timing, negation and explicit exclusions" in rendered.system


def test_uncertain_attributed_claim_is_preserved_without_promoting_it_to_a_fact() -> None:
    value = _generation_input()
    brief = (
        "The research team suggests compound systems may improve this particular benchmark. "
        "We have not measured our own system. Attribute the claim and retain may; "
        "do not promise universal gains or suggest we ran the experiment."
    )
    value = value.model_copy(update={"request": value.request.model_copy(update={"topic": brief})})
    budget = TokenBudgetManager(_policy())
    prompt = PromptBuilder(budget).build(value)
    request = json.loads(
        next(s.content for s in prompt.sections if s.kind is PromptSectionKind.REQUEST)
    )
    assert request["topic"] == brief
    rendered = PromptRenderer(budget).render(prompt)
    assert "Keep may as may" in rendered.system
    assert "agreement as agreement" in rendered.system
