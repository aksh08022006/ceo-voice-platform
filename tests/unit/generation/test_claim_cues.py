"""Known live false claims become bounded regressions without claiming full semantic coverage."""

import pytest

from ceo_voice.generation.claim_cues import unsupported_claim_cues


@pytest.mark.parametrize(
    "candidate",
    [
        "This architecture drives superior performance.",
        "We are seeing real gains by combining models and retrieval.",
        "The projects work seamlessly together for all users.",
        "This creates more capable, reliable applications.",
        "We can accelerate interoperability and build more unified and resilient architectures.",
        "This gives lower latency and reduced costs.",
        "Compound systems often outperform monolithic models on complex tasks.",
        "Openness drives the best outcomes for the customer.",
        "This will accelerate development across the stack.",
        "Open infrastructure prevents lock-in.",
        "This helps every organization manage its data.",
        "The system can reason reliably over proprietary data.",
        "Adding complexity introduces new failure modes.",
        "We have always believed in open standards.",
        "The community benefits from accelerated development.",
        "This is an opportunity to drive compatibility and design more integrated formats.",
        "This acquisition moves the entire industry in that direction.",
    ],
)
def test_novel_outcome_cues_are_flagged(candidate: str) -> None:
    assert unsupported_claim_cues(
        candidate, "The company acquired a team working on open data formats."
    )


def test_explicit_support_negation_and_ordinary_opinion_are_distinguished() -> None:
    text = "We measured lower latency in this experiment"
    assert unsupported_claim_cues(text, text) == ()
    assert (
        unsupported_claim_cues("This does not guarantee better performance or lower costs.", "")
        == ()
    )
    assert unsupported_claim_cues("I think compound systems may help some applications.", "") == ()
    assert unsupported_claim_cues(
        "We want better performance. We want better performance.", ""
    ) == ("better performance",)


@pytest.mark.parametrize("wording", ["can certainly help", "can improve", "will benefit"])
def test_tentative_benefit_is_not_upgraded_by_an_emotional_rewrite(wording: str) -> None:
    assert wording in unsupported_claim_cues(
        f"Compound systems {wording} some applications.",
        "Compound systems may help some applications, but not all.",
    )


def test_modality_check_allows_qualified_text_and_explicitly_supplied_capability() -> None:
    assert unsupported_claim_cues("Compound systems may help some applications.", "") == ()
    assert (
        unsupported_claim_cues(
            "Compound systems can help some applications.",
            "Compound systems can help some applications. Retrieval may improve others.",
        )
        == ()
    )
