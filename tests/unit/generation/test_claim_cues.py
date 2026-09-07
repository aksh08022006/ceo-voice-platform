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
