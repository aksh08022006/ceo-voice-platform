"""A study must exclude held-out source, event, content, and future evidence leakage."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ceo_voice.experiments import ExperimentManifest, prepare

from .factories import make_manifest


@pytest.mark.parametrize("attribute", ["group_id", "content_sha256"])
def test_rejects_duplicate_evidence_across_split(attribute: str) -> None:
    payload = make_manifest().model_dump()
    payload["sources"][1][attribute] = payload["sources"][0][attribute]
    with pytest.raises(ValidationError, match=attribute):
        ExperimentManifest.model_validate(payload)


def test_rejects_test_source_seen_by_another_case() -> None:
    payload = make_manifest().model_dump()
    payload["cases"][0]["as_of"] = datetime(2025, 1, 1, tzinfo=UTC)
    payload["sources"][1]["published_at"] = datetime(2026, 1, 1, tzinfo=UTC)
    payload["cases"][0]["context_source_ids"] = ["source-2"]
    with pytest.raises(ValidationError, match="held-out source IDs overlap"):
        ExperimentManifest.model_validate(payload)


@pytest.mark.parametrize("year", [2022, 2023])
def test_holdouts_must_follow_the_generation_cutoff(year: int) -> None:
    payload = make_manifest().model_dump()
    payload["cases"][0]["as_of"] = datetime(2023, 1, 1, tzinfo=UTC)
    payload["sources"][1]["published_at"] = datetime(year, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="strictly after case as_of"):
        ExperimentManifest.model_validate(payload)


@pytest.mark.parametrize("role", ["training_source_ids", "context_source_ids"])
def test_rejects_future_evidence(role: str) -> None:
    payload = make_manifest().model_dump()
    payload["cases"][0][role] = ["source-3"]
    with pytest.raises(ValidationError, match="after case as_of"):
        ExperimentManifest.model_validate(payload)


def test_rejects_unknown_duplicate_sources_and_case_ids() -> None:
    original = make_manifest().model_dump()
    payload = make_manifest().model_dump()
    payload["cases"][0]["context_source_ids"] = ["unknown"]
    with pytest.raises(ValidationError, match="source registry"):
        ExperimentManifest.model_validate(payload)
    payload = make_manifest().model_dump()
    payload["sources"] = [*payload["sources"], payload["sources"][0]]
    with pytest.raises(ValidationError, match="source IDs must be unique"):
        ExperimentManifest.model_validate(payload)
    payload = make_manifest().model_dump()
    payload["cases"][1]["case_id"] = payload["cases"][0]["case_id"]
    with pytest.raises(ValidationError, match="case IDs must be unique"):
        ExperimentManifest.model_validate(payload)
    payload = make_manifest().model_dump()
    payload["cases"] = list(payload["cases"])
    payload["cases"][1] = {**original["cases"][0], "case_id": "different-id"}
    with pytest.raises(ValidationError, match="not independent trials"):
        ExperimentManifest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("arms", ("generic",), "two distinct"),
        ("arms", ("generic", "generic"), "two distinct"),
        ("baseline_arm", "absent", "baseline arm"),
        ("dimensions", (), "dimensions"),
        ("dimensions", ("voice", "voice"), "dimensions"),
    ],
)
def test_rejects_ambiguous_design(field: str, value: object, message: str) -> None:
    payload = make_manifest().model_dump()
    payload[field] = value
    with pytest.raises(ValidationError, match=message):
        ExperimentManifest.model_validate(payload)


def test_rejects_missing_arms_duplicate_references_and_naive_time() -> None:
    payload = make_manifest().model_dump()
    del payload["cases"][0]["outputs"]["hybrid"]
    with pytest.raises(ValidationError, match="every arm"):
        ExperimentManifest.model_validate(payload)
    payload = make_manifest().model_dump()
    payload["cases"][0]["held_out_source_ids"] = ["source-1", "source-1"]
    with pytest.raises(ValidationError, match="unique within each role"):
        ExperimentManifest.model_validate(payload)
    payload = make_manifest().model_dump()
    payload["cases"][0]["as_of"] = "2025-01-01T00:00:00"
    with pytest.raises(ValidationError, match="timezone"):
        ExperimentManifest.model_validate(payload)


def test_prepare_is_reproducible_preserves_text_and_separates_private_key() -> None:
    manifest = make_manifest()
    ballots, key = prepare(manifest)
    assert prepare(manifest) == (ballots, key)
    assert len(ballots.ballots) == 9
    assert len({ballot.ballot_id for ballot in ballots.ballots}) == 9
    assert "arm_a" not in ballots.model_dump_json()
    assert "case_id" not in ballots.model_dump_json()
    for ballot in ballots.ballots:
        assert ballot.candidate_a.endswith(".\n")
        assert ballot.candidate_b.endswith(".\n")
    assert {assignment.arm_a == manifest.baseline_arm for assignment in key.assignments} == {
        True,
        False,
    }
    payload = manifest.model_dump()
    payload["cases"][0]["outputs"]["hybrid"] = "Changed real output."
    edited = ExperimentManifest.model_validate(payload)
    new_ballots, _ = prepare(edited)
    assert new_ballots.manifest_sha256 != ballots.manifest_sha256
    assert not {ballot.ballot_id for ballot in ballots.ballots} & {
        ballot.ballot_id for ballot in new_ballots.ballots
    }


def test_prepare_revalidates_nested_mutation() -> None:
    manifest = make_manifest()
    manifest.cases[0].outputs.pop("hybrid")
    with pytest.raises(ValidationError, match="every arm"):
        prepare(manifest)
