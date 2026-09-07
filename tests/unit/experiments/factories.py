"""Explicitly synthetic text and ratings for unit testing, never study evidence."""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from ceo_voice.experiments import (
    ExperimentCase,
    ExperimentManifest,
    ExperimentSource,
    HumanRating,
    RatingSubmission,
    prepare,
)
from ceo_voice.experiments.contracts import Choice


def make_manifest() -> ExperimentManifest:
    """Three distinct briefs, two fictional authors, and separately held-out sources."""

    arms = ("generic", "exemplar", "hvm", "hybrid")
    sources = tuple(
        ExperimentSource(
            source_id=f"source-{index}",
            group_id=f"group-{index}",
            content_sha256=sha256(f"synthetic source {index}".encode()).hexdigest(),
            published_at=datetime(2023 if index == 0 else 2024, 1, 1, tzinfo=UTC),
        )
        for index in range(4)
    )
    return ExperimentManifest(
        experiment_id=UUID("4de49a38-48df-4489-9870-967e088ac965"),
        tenant_id=UUID("0e779fdf-d144-45bb-bf19-7c224ea92075"),
        synthetic=True,
        seed=1729,
        sources=sources,
        cases=tuple(
            ExperimentCase(
                case_id=f"case-{index}",
                author_id=f"fictional-{index % 2}",
                platform="linkedin" if index % 2 else "x",
                brief=f"Explain synthetic lesson {index}.",
                as_of=datetime(2023, 12, 1, tzinfo=UTC),
                training_source_ids=("source-0",),
                held_out_source_ids=(f"source-{index}",),
                outputs={arm: f"Synthetic candidate {index}: {arm}.\n" for arm in arms},
            )
            for index in range(1, 4)
        ),
    )


def make_ratings(manifest: ExperimentManifest, preference: str = "arm") -> RatingSubmission:
    """Test-only decisions selected by the analyst key to verify unblinding arithmetic."""

    _, key = prepare(manifest)
    ratings: list[HumanRating] = []
    for assignment in key.assignments:
        choice: Choice
        if preference == "tie":
            choice = "tie"
        elif preference == "baseline":
            choice = "a" if assignment.arm_a == manifest.baseline_arm else "b"
        else:
            choice = "b" if assignment.arm_a == manifest.baseline_arm else "a"
        ratings.append(
            HumanRating(
                ballot_id=assignment.ballot_id,
                reviewer_id="synthetic-test-reviewer",
                choices=dict.fromkeys(manifest.dimensions, choice),
            )
        )
    return RatingSubmission(
        experiment_id=manifest.experiment_id,
        manifest_sha256=manifest.fingerprint(),
        ratings=tuple(ratings),
    )
