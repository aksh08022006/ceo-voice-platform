"""Case-paired human preferences with bootstrap resampling of independent source groups."""

import random
from collections import defaultdict
from statistics import mean

from ceo_voice.core.exceptions import EvaluationError

from .contracts import (
    ArmResult,
    Assignment,
    Choice,
    ExperimentManifest,
    ExperimentReport,
    RatingSubmission,
)
from .preparation import prepare


def _clusters(manifest: ExperimentManifest) -> tuple[frozenset[str], ...]:
    """Keep cases sharing held-out event groups together, including transitive overlap."""

    sources = {source.source_id: source for source in manifest.sources}
    groups: list[tuple[set[str], set[str]]] = []
    for case in manifest.cases:
        source_groups = {
            value
            for source_id in case.held_out_source_ids
            for value in (
                f"group:{sources[source_id].group_id}",
                f"hash:{sources[source_id].content_sha256}",
            )
        }
        members = {case.case_id}
        remaining: list[tuple[set[str], set[str]]] = []
        for existing_sources, existing_members in groups:
            if source_groups & existing_sources:
                source_groups.update(existing_sources)
                members.update(existing_members)
            else:
                remaining.append((existing_sources, existing_members))
        remaining.append((source_groups, members))
        groups = remaining
    return tuple(frozenset(members) for _, members in groups)


def _interval(
    case_preferences: dict[str, float],
    clusters: tuple[frozenset[str], ...],
    samples: int,
    seed: int,
) -> tuple[int, tuple[float, float] | None]:
    """Resample paired case outcomes jointly; a single group cannot identify uncertainty."""

    grouped = [
        [case_preferences[case_id] for case_id in sorted(cluster) if case_id in case_preferences]
        for cluster in clusters
    ]
    grouped = [values for values in grouped if values]
    if len(grouped) < 2:
        return len(grouped), None
    rng = random.Random(seed)
    bootstrap = sorted(
        mean(value for group in rng.choices(grouped, k=len(grouped)) for value in group)
        for _ in range(samples)
    )
    return len(grouped), (
        bootstrap[int(0.025 * (samples - 1))],
        bootstrap[int(0.975 * (samples - 1))],
    )


def _win(choice: Choice, assignment: Assignment, baseline: str) -> float:
    if choice == "tie":
        return 0.5
    winner = assignment.arm_a if choice == "a" else assignment.arm_b
    return 0.0 if winner == baseline else 1.0


def _result(
    *,
    arm: str,
    author_id: str | None,
    dimension: str,
    outcomes: dict[str, list[float]],
    clusters: tuple[frozenset[str], ...],
    samples: int,
    seed: int,
) -> ArmResult:
    case_preferences = {case_id: mean(values) for case_id, values in outcomes.items()}
    groups, interval = _interval(case_preferences, clusters, samples, seed)
    return ArmResult(
        arm=arm,
        author_id=author_id,
        dimension=dimension,
        rated_cases=len(outcomes),
        independent_groups=groups,
        ratings=sum(len(values) for values in outcomes.values()),
        win_rate=mean(mean(value == 1.0 for value in values) for values in outcomes.values()),
        tie_rate=mean(mean(value == 0.5 for value in values) for values in outcomes.values()),
        loss_rate=mean(mean(value == 0.0 for value in values) for values in outcomes.values()),
        preference_rate=mean(case_preferences.values()),
        preference_ci95=interval,
    )


def score(
    manifest: ExperimentManifest,
    submission: RatingSubmission,
    *,
    bootstrap_samples: int = 2000,
) -> ExperimentReport:
    """Score actual submitted human ratings, retaining missingness and synthetic status."""

    if not 100 <= bootstrap_samples <= 100_000:
        raise EvaluationError("bootstrap_samples must be between 100 and 100000")
    ballots, private = prepare(manifest)
    submission = RatingSubmission.model_validate(submission.model_dump())
    if (
        submission.experiment_id != manifest.experiment_id
        or submission.manifest_sha256 != private.manifest_sha256
    ):
        raise EvaluationError("ratings do not belong to this exact experiment manifest")
    assignments = {assignment.ballot_id: assignment for assignment in private.assignments}
    cases = {case.case_id: case for case in manifest.cases}
    seen: set[tuple[str, str]] = set()
    rated_ballots: set[str] = set()
    outcomes: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for rating in submission.ratings:
        assignment = assignments.get(rating.ballot_id)
        if assignment is None:
            raise EvaluationError("rating references an unknown ballot")
        identity = (str(rating.ballot_id), rating.reviewer_id)
        if identity in seen:
            raise EvaluationError("a reviewer cannot rate the same ballot twice")
        if set(rating.choices) != set(manifest.dimensions):
            raise EvaluationError("a rating must contain exactly the experiment dimensions")
        seen.add(identity)
        rated_ballots.add(str(rating.ballot_id))
        arm = assignment.arm_b if assignment.arm_a == manifest.baseline_arm else assignment.arm_a
        for dimension, choice in rating.choices.items():
            outcomes[arm, dimension][assignment.case_id].append(
                _win(choice, assignment, manifest.baseline_arm)
            )
    clusters = _clusters(manifest)
    results: list[ArmResult] = []
    for (arm, dimension), arm_outcomes in sorted(outcomes.items()):
        authors: list[str | None] = [None, *sorted({cases[key].author_id for key in arm_outcomes})]
        for author_id in authors:
            selected = {
                case_id: values
                for case_id, values in arm_outcomes.items()
                if author_id is None or cases[case_id].author_id == author_id
            }
            results.append(
                _result(
                    arm=arm,
                    author_id=author_id,
                    dimension=dimension,
                    outcomes=selected,
                    clusters=clusters,
                    samples=bootstrap_samples,
                    seed=manifest.seed,
                )
            )
    status = (
        "awaiting_human_ratings"
        if not rated_ballots
        else "complete" if len(rated_ballots) == len(ballots.ballots) else "partial"
    )
    limitations = [
        "Local source IDs, group IDs, hashes, and timestamps detect only declared leakage; "
        "unknown pretraining exposure and undeclared paraphrases remain unverified.",
        "Preferences average reviewers within each case before averaging cases. "
        "Intervals resample connected held-out source groups with replacement, keeping "
        "paired outcomes together; they are conditional on this reviewer panel and these authors.",
        "Preference is wins plus half ties. A complete report means every ballot has at least "
        "one rating, not that a target panel size, statistical power, or author population is covered.",
        "A single independent group has no reported interval. Partial submissions can have "
        "selection bias. Multiple comparisons and future hyperparameter selection are not corrected.",
        "No authorship, factual truth, engagement improvement, or production readiness follows "
        "from a preference score alone. Report dimensions separately and inspect factual failures.",
    ]
    if manifest.synthetic:
        limitations.insert(
            0, "SYNTHETIC FIXTURE: harness verification only; no real-person fidelity claim."
        )
    return ExperimentReport(
        experiment_id=manifest.experiment_id,
        manifest_sha256=private.manifest_sha256,
        synthetic=manifest.synthetic,
        status=status,
        baseline_arm=manifest.baseline_arm,
        expected_ballots=len(ballots.ballots),
        rated_ballots=len(rated_ballots),
        bootstrap_samples=bootstrap_samples,
        results=tuple(results),
        limitations=tuple(limitations),
    )
