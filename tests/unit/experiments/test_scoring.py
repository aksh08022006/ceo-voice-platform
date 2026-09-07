"""Verify statistics against explicit preferences and reject invalid human review records."""

from uuid import uuid4

import pytest

from ceo_voice.core.exceptions import EvaluationError
from ceo_voice.experiments import (
    ExperimentManifest,
    HumanRating,
    RatingSubmission,
    render_report,
    score,
)

from .factories import make_manifest, make_ratings


@pytest.mark.parametrize(
    ("preference", "expected"), [("arm", 1.0), ("tie", 0.5), ("baseline", 0.0)]
)
def test_unblinds_each_dimension_and_reports_rates(preference: str, expected: float) -> None:
    manifest = make_manifest()
    ratings = make_ratings(manifest, preference)
    report = score(manifest, ratings, bootstrap_samples=100)
    assert report == score(manifest, ratings, bootstrap_samples=100)
    assert report.status == "complete"
    assert report.rated_ballots == report.expected_ballots == 9
    assert len(report.results) == 27
    for row in report.results:
        assert row.preference_rate == expected
        assert row.win_rate + row.tie_rate + row.loss_rate == 1.0
        if row.independent_groups > 1:
            assert row.preference_ci95 == (expected, expected)
        else:
            assert row.preference_ci95 is None
    rendered = render_report(report)
    assert "Synthetic fixture" in rendered
    assert "Preference (95% CI)" in rendered


def test_zero_ratings_never_produces_scores() -> None:
    manifest = make_manifest()
    empty = make_ratings(manifest).model_copy(update={"ratings": ()})
    report = score(manifest, empty, bootstrap_samples=100)
    assert report.status == "awaiting_human_ratings"
    assert report.results == ()
    assert "No quality scores" in render_report(report)


def test_case_average_prevents_extra_reviewers_from_reweighting_briefs() -> None:
    manifest = make_manifest()
    arm_votes = make_ratings(manifest)
    baseline_votes = make_ratings(manifest, "baseline")
    ratings = [arm_votes.ratings[0], baseline_votes.ratings[3]]
    ratings.extend(
        arm_votes.ratings[0].model_copy(update={"reviewer_id": f"extra-{index}"})
        for index in range(9)
    )
    submission = arm_votes.model_copy(update={"ratings": tuple(ratings)})
    report = score(manifest, submission, bootstrap_samples=100)
    assert report.status == "partial"
    overall = [row for row in report.results if row.author_id is None]
    assert len(overall) == 3
    for row in overall:
        assert row.rated_cases == 2
        assert row.ratings == 11
        assert row.preference_rate == 0.5
        assert row.win_rate == row.loss_rate == 0.5
        assert row.preference_ci95 == (0.0, 1.0)


def test_transitively_shared_event_groups_count_as_one_independent_unit() -> None:
    payload = make_manifest().model_dump()
    payload["cases"][2]["held_out_source_ids"] = ("source-1", "source-2")
    manifest = ExperimentManifest.model_validate(payload)
    report = score(manifest, make_ratings(manifest), bootstrap_samples=100)
    for row in report.results:
        assert row.independent_groups == 1
        assert row.preference_ci95 is None


@pytest.mark.parametrize("count", [99, 100001])
def test_bootstrap_bounds(count: int) -> None:
    manifest = make_manifest()
    with pytest.raises(EvaluationError, match="bootstrap_samples"):
        score(manifest, make_ratings(manifest), bootstrap_samples=count)


@pytest.mark.parametrize("field", ["experiment_id", "manifest_sha256"])
def test_rejects_stale_or_foreign_ratings(field: str) -> None:
    manifest = make_manifest()
    updated = make_ratings(manifest).model_copy(
        update={field: uuid4() if field == "experiment_id" else "0" * 64}
    )
    with pytest.raises(EvaluationError, match="exact experiment manifest"):
        score(manifest, updated, bootstrap_samples=100)


def test_rejects_unknown_ballot_duplicate_review_and_missing_dimension() -> None:
    manifest = make_manifest()
    valid = make_ratings(manifest)
    first = valid.ratings[0]
    for changed, message in [
        ((first.model_copy(update={"ballot_id": uuid4()}),), "unknown ballot"),
        ((first, first), "same ballot twice"),
        (
            (first.model_copy(update={"choices": {"voice": "tie"}}),),
            "exactly the experiment dimensions",
        ),
    ]:
        with pytest.raises(EvaluationError, match=message):
            score(manifest, valid.model_copy(update={"ratings": changed}), bootstrap_samples=100)


def test_dimensions_are_independent_and_unlabelled_real_study_does_not_claim_fidelity() -> None:
    manifest = make_manifest().model_copy(update={"synthetic": False})
    valid = make_ratings(manifest)
    first = valid.ratings[0]
    rating = HumanRating(
        ballot_id=first.ballot_id,
        reviewer_id="reviewer",
        choices={"voice": first.choices["voice"], "meaning": "tie", "fluency": "tie"},
    )
    report = score(manifest, valid.model_copy(update={"ratings": (rating,)}), bootstrap_samples=100)
    assert {row.dimension: row.preference_rate for row in report.results} == {
        "voice": 1.0,
        "meaning": 0.5,
        "fluency": 0.5,
    }
    assert "Synthetic fixture" not in render_report(report)
    assert any("No authorship" in limit for limit in report.limitations)


def test_rating_schema_retains_declared_snapshot() -> None:
    manifest = make_manifest()
    submission = make_ratings(manifest)
    assert RatingSubmission.model_validate_json(submission.model_dump_json()) == submission
