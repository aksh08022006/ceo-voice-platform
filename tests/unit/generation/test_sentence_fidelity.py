"""Protocol validation for a sentence reviewer; fake verdicts do not prove semantic accuracy."""

import asyncio
import json
from uuid import UUID

import pytest

from ceo_voice.generation.fidelity import FidelityReviewer
from ceo_voice.generation.fidelity_contracts import BriefSource, FidelityPolicy, FidelityReview
from tests.unit.generation.test_engine import FakeProvider


def review(
    units: list[dict[str, object]], *, authority: str = "brief"
) -> tuple[FidelityReview, FakeProvider]:
    provider = FakeProvider((json.dumps({"units": units}),))
    reviewer = FidelityReviewer(
        provider,
        policy=FidelityPolicy(
            enabled=True,
            model="test-model",
            review_format="sentence_verdicts",
        ),
    )
    sources: tuple[BriefSource, ...] = (
        BriefSource(source_id="brief", authority="brief", text="Systems may help."),
    )
    if authority == "parent":
        sources += (
            BriefSource(source_id="parent", authority="attributed_context", text="Systems help."),
        )
    result = asyncio.run(
        reviewer.review_sources(
            "Systems may help.",
            request_id=UUID(int=1),
            sources=sources,
        )
    )
    return result, provider


def verdict(**updates: object) -> dict[str, object]:
    return {
        "unit_id": "u000",
        "verdict": "supported",
        "kind": "factual",
        "source_ids": ["brief"],
        "reason": "The brief explicitly supplies this possibility.",
        **updates,
    }


def test_sentence_verdict_is_bound_to_exact_server_owned_text_and_usage() -> None:
    result, provider = review([verdict()])
    assert result.status == "clear"
    assert result.assessment is not None
    claim = result.assessment.units[0].claims[0]
    assert claim.span.text == "Systems may help."
    assert claim.span.end == len(claim.span.text)
    assert claim.citations[0].text == "Systems may help."
    assert result.input_tokens == 100 and result.output_tokens == 30
    assert result.aligned_span_count == 0
    request = json.loads(provider.requests[0].user)
    assert "candidate" not in request
    assert request["units"] == [{"unit_id": "u000", "text": "Systems may help."}]


def test_unsupported_sentence_remains_blocked_without_fabricated_citations() -> None:
    result, _ = review([verdict(verdict="unsupported", source_ids=[])])
    assert result.status == "blocked"
    assert result.assessment is not None
    assert result.assessment.units[0].claims[0].citations == ()


@pytest.mark.parametrize(
    "units",
    [
        [],
        [verdict(), verdict()],
        [verdict(unit_id="u001")],
        [verdict(source_ids=["missing"])],
        [verdict(source_ids=[])],
        [verdict(source_ids=["brief", "brief"])],
        [verdict(verdict="approved")],
        [verdict(kind="factual", source_ids=["parent"])],
    ],
)
def test_missing_coverage_bad_citations_and_parent_authority_fail_closed(
    units: list[dict[str, object]],
) -> None:
    result, _ = review(units, authority="parent")
    assert result.status == "error"
    assert result.error_code == "review_invalid"


def test_parent_source_is_only_accepted_as_attributed_material() -> None:
    result, _ = review(
        [verdict(kind="attributed_statement", source_ids=["parent"])], authority="parent"
    )
    assert result.status == "clear"


def test_thread_separator_is_formatting_and_sentence_offsets_still_bind() -> None:
    from ceo_voice.generation.fidelity import candidate_units
    from ceo_voice.utils.hashing import sha256_text

    candidate = "Systems may help.\n---\nEvaluation matters."
    units = candidate_units(candidate)
    assert [u.text for u in units] == ["Systems may help.", "Evaluation matters."]
    assert units[1].start == candidate.index("Evaluation")
    provider = FakeProvider((json.dumps({"units": [verdict(), verdict(unit_id="u001")]}),))
    reviewer = FidelityReviewer(
        provider,
        policy=FidelityPolicy(enabled=True, model="test-model", review_format="sentence_verdicts"),
    )
    result = asyncio.run(
        reviewer.review_sources(
            candidate,
            request_id=UUID(int=1),
            sources=(
                BriefSource(
                    source_id="brief",
                    authority="brief",
                    text="Systems may help. Evaluation matters.",
                ),
            ),
        )
    )
    assert result.status == "clear"
    assert result.candidate_sha256 == sha256_text(candidate)
    # Arbitrary punctuation and embedded dashes cannot disappear from assessment.
    assert [u.text for u in candidate_units("Systems---may help.")] == ["Systems---may help."]
    assert [u.text for u in candidate_units("---")] == ["---"]


@pytest.mark.parametrize("status", [400, 429])
def test_review_reports_safe_provider_status_without_error_body(status: int) -> None:
    from ceo_voice.core.exceptions import ProviderError

    provider = FakeProvider(
        (ProviderError("private provider diagnostic", details={"status_code": status}),)
    )
    reviewer = FidelityReviewer(
        provider,
        policy=FidelityPolicy(enabled=True, model="test-model", review_format="sentence_verdicts"),
    )
    result = asyncio.run(
        reviewer.review_sources(
            "Systems may help.",
            request_id=UUID(int=1),
            sources=(BriefSource(source_id="brief", authority="brief", text="Systems may help."),),
        )
    )
    assert result.status == "error"
    assert result.provider_http_status == status
    assert "private provider" not in result.model_dump_json()
