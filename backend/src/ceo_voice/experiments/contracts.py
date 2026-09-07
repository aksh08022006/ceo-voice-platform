"""Validated, provider-independent inputs for blinded writing experiments."""

import hashlib
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from ceo_voice.models.base import (
    ContractModel,
    NonBlankText,
    NonEmptyStr,
    UtcDatetime,
)

Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Choice = Literal["a", "b", "tie"]


class ExperimentSource(ContractModel):
    """A source version; group IDs identify reposts, threads, or shared events."""

    source_id: NonEmptyStr
    group_id: NonEmptyStr
    content_sha256: Digest
    published_at: UtcDatetime


class ExperimentCase(ContractModel):
    """One common brief and actual candidate outputs from every experiment arm."""

    case_id: NonEmptyStr
    author_id: NonEmptyStr
    platform: Literal["linkedin", "x"]
    brief: NonBlankText
    as_of: UtcDatetime
    training_source_ids: tuple[NonEmptyStr, ...] = ()
    context_source_ids: tuple[NonEmptyStr, ...] = ()
    held_out_source_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    outputs: dict[NonEmptyStr, NonBlankText]

    @model_validator(mode="after")
    def distinct_sources(self) -> Self:
        """Repeated references within one role are data errors, not extra evidence."""

        for references in (
            self.training_source_ids,
            self.context_source_ids,
            self.held_out_source_ids,
        ):
            if len(references) != len(set(references)):
                raise ValueError("case source references must be unique within each role")
        return self


class ExperimentManifest(ContractModel):
    """Sealed study design; held-out sources never enter any arm's local context."""

    schema_version: Literal["1.0"] = "1.0"
    experiment_id: UUID
    tenant_id: UUID
    synthetic: bool
    seed: int = Field(ge=0, le=2**32 - 1)
    dimensions: tuple[NonEmptyStr, ...] = ("voice", "meaning", "fluency")
    arms: tuple[NonEmptyStr, ...] = ("generic", "exemplar", "hvm", "hybrid")
    baseline_arm: NonEmptyStr = "generic"
    sources: tuple[ExperimentSource, ...] = Field(min_length=1)
    cases: tuple[ExperimentCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_design(self) -> Self:
        """Reject source, event, duplicate-content, and observable temporal leakage."""

        if len(self.arms) < 2 or len(self.arms) != len(set(self.arms)):
            raise ValueError("at least two distinct experiment arms are required")
        if self.baseline_arm not in self.arms:
            raise ValueError("baseline arm must be in experiment arms")
        if not self.dimensions or len(self.dimensions) != len(set(self.dimensions)):
            raise ValueError("dimensions must be nonempty and unique")
        sources = {source.source_id: source for source in self.sources}
        if len(sources) != len(self.sources):
            raise ValueError("source IDs must be unique")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("case IDs must be unique")
        briefs = {(case.author_id, case.platform, case.brief.strip()) for case in self.cases}
        if len(briefs) != len(self.cases):
            raise ValueError("duplicate author/platform/brief cases are not independent trials")
        used: set[str] = set()
        held_out: set[str] = set()
        for case in self.cases:
            if set(case.outputs) != set(self.arms):
                raise ValueError("every case must contain exactly one output for every arm")
            evidence = set(case.training_source_ids) | set(case.context_source_ids)
            references = evidence | set(case.held_out_source_ids)
            if not references <= sources.keys():
                raise ValueError("every case source reference must exist in the source registry")
            if any(sources[source_id].published_at > case.as_of for source_id in evidence):
                raise ValueError(
                    "training and context sources cannot be published after case as_of"
                )
            if any(
                sources[source_id].published_at <= case.as_of
                for source_id in case.held_out_source_ids
            ):
                raise ValueError("held-out sources must be published strictly after case as_of")
            used.update(evidence)
            held_out.update(case.held_out_source_ids)
        if used & held_out:
            raise ValueError(
                "held-out source IDs overlap training or context anywhere in the study"
            )
        for attribute in ("group_id", "content_sha256"):
            used_values = {getattr(sources[source_id], attribute) for source_id in used}
            held_values = {getattr(sources[source_id], attribute) for source_id in held_out}
            if used_values & held_values:
                raise ValueError(f"held-out {attribute} overlaps training or context")
        return self

    def fingerprint(self) -> str:
        """Bind ballot IDs and ratings to exact candidate text and study configuration."""

        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class Ballot(ContractModel):
    """Reviewer-visible comparison, intentionally containing no arm or model labels."""

    ballot_id: UUID
    author_id: NonEmptyStr
    platform: Literal["linkedin", "x"]
    brief: NonBlankText
    candidate_a: NonBlankText
    candidate_b: NonBlankText
    dimensions: tuple[NonEmptyStr, ...]


class Assignment(ContractModel):
    """Private analyst key; do not distribute alongside reviewer ballots."""

    ballot_id: UUID
    case_id: NonEmptyStr
    arm_a: NonEmptyStr
    arm_b: NonEmptyStr


class BallotExport(ContractModel):
    """Blinded review packet; synthetic status always travels with its contents."""

    experiment_id: UUID
    manifest_sha256: Digest
    synthetic: bool
    instructions: str = (
        "Compare A and B separately for each dimension. Choose a, b, or tie. "
        "Judge voice against independently supplied reference writing; if you cannot judge, "
        "leave the ballot unsubmitted. Do not infer model identity. "
        "Synthetic cases establish experiment plumbing only, never real-person fidelity."
    )
    ballots: tuple[Ballot, ...]


class PrivateKey(ContractModel):
    """Analyst-only mapping generated from the exact manifest."""

    experiment_id: UUID
    manifest_sha256: Digest
    assignments: tuple[Assignment, ...]


class HumanRating(ContractModel):
    """A real reviewer's full dimension decisions for one blinded ballot."""

    ballot_id: UUID
    reviewer_id: NonEmptyStr
    choices: dict[NonEmptyStr, Choice]


class RatingSubmission(ContractModel):
    """Ratings must explicitly identify the candidate snapshot they evaluated."""

    experiment_id: UUID
    manifest_sha256: Digest
    ratings: tuple[HumanRating, ...]


class ArmResult(ContractModel):
    """Case-weighted preferences against the common baseline, independently per dimension."""

    arm: NonEmptyStr
    author_id: str | None
    dimension: NonEmptyStr
    rated_cases: int
    independent_groups: int
    ratings: int
    win_rate: float
    tie_rate: float
    loss_rate: float
    preference_rate: float
    preference_ci95: tuple[float, float] | None


class ExperimentReport(ContractModel):
    """Observed human evidence; no generated ratings, judge calls, or fidelity shortcuts."""

    experiment_id: UUID
    manifest_sha256: Digest
    synthetic: bool
    status: Literal["awaiting_human_ratings", "partial", "complete"]
    baseline_arm: NonEmptyStr
    expected_ballots: int
    rated_ballots: int
    bootstrap_samples: int
    results: tuple[ArmResult, ...]
    limitations: tuple[str, ...]
