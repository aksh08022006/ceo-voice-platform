"""Targeted repair cannot overwrite human wording outside reviewed blocking spans."""

import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest

from ceo_voice.generation.editor_revision import revise_flagged_spans
from tests.unit.generation.test_engine import FakeProvider
from tests.unit.generation.test_fidelity import SOURCES, ReviewProvider, run_review

CONTENT = "🚀 Keep this human wording.\n\nAn unsupported causal claim."


def blocked_review() -> Any:
    def flag_second(payload: dict[str, Any]) -> None:
        payload["units"][1]["claims"][0]["verdict"] = "unsupported"

    return run_review(ReviewProvider(mutate=flag_second), CONTENT)


def proposal(text: str) -> Any:
    provider = FakeProvider((text,))
    result = asyncio.run(
        revise_flagged_spans(
            provider,
            model="test-model",
            maximum_output_tokens=800,
            request_id=uuid4(),
            content=CONTENT,
            review=blocked_review(),
            sources=SOURCES,
        )
    )
    assert len(provider.requests) == 1
    return result


def test_repair_only_changes_flagged_current_text() -> None:
    result = proposal(
        json.dumps(
            {"replacements": [{"id": "span-0", "text": "A qualified editorial suggestion."}]}
        )
    )
    assert result.applied
    assert result.content == "🚀 Keep this human wording.\n\nA qualified editorial suggestion."


@pytest.mark.parametrize(
    "payload",
    [
        "not JSON",
        '{"replacements":[{"id":"span-9","text":"replace protected text"}]}',
        '{"replacements":[{"id":"span-0","text":"x"},{"id":"span-0","text":"y"}]}',
        '{"replacements":[{"id":"span-0","text":"x","start":0}]}',
    ],
)
def test_invalid_proposals_keep_every_original_character(payload: str) -> None:
    result = proposal(payload)
    assert not result.applied and result.content == CONTENT


def test_a_different_candidate_cannot_reuse_a_blocked_review() -> None:
    provider = FakeProvider(("must not run",))
    with pytest.raises(ValueError, match="exact text"):
        asyncio.run(
            revise_flagged_spans(
                provider,
                model="test-model",
                maximum_output_tokens=800,
                request_id=uuid4(),
                content=CONTENT + " edited",
                review=blocked_review(),
                sources=SOURCES,
            )
        )
    assert not provider.requests
