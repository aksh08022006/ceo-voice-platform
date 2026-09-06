"""Portable input and evidence contracts for the PDF's exact evaluation scales."""

from typing import Annotated, Literal, Self

from pydantic import AnyHttpUrl, Field, model_validator

from ceo_voice.models.base import ContractModel, NonBlankText, NonEmptyStr, UtcDatetime

Platform = Literal["x", "linkedin"]
Category = Literal[
    "product_launch", "acquisition", "earnings", "personal_reflection", "industry_commentary"
]
HumanScore = Annotated[int, Field(strict=True, ge=1, le=5)]
VoiceScore = Annotated[int, Field(strict=True, ge=1, le=10)]


class ReferencePost(ContractModel):
    """One complete original public post; provenance is a human-reviewed attestation."""

    source_id: NonEmptyStr
    profile_id: NonEmptyStr
    platform: Platform
    independence_group: NonEmptyStr
    source_url: AnyHttpUrl
    published_at: UtcDatetime
    text: NonBlankText
    complete_original: bool = False
    provenance_verified: bool = False


class GenerationSource(ContractModel):
    """All text exposed to profile fitting, retrieval or generation, including source groups."""

    source_id: NonEmptyStr
    independence_group: NonEmptyStr
    text: NonBlankText


class HumanReview(ContractModel):
    """Actual ratings supplied by an identified human reviewer; no inferred/default ratings."""

    reviewer: NonEmptyStr
    reviewed_at: UtcDatetime
    candidate_sha256: NonEmptyStr
    voice_accuracy: HumanScore
    post_quality: HumanScore
    naturalness: HumanScore
    notes: NonBlankText


class AssignmentCase(ContractModel):
    case_id: NonEmptyStr
    profile_id: NonEmptyStr
    platform: Platform
    category: Category
    idea: NonBlankText
    draft: NonBlankText | None = None
    human_review: HumanReview | None = None


class AssignmentManifest(ContractModel):
    version: Literal["1.0.0"] = "1.0.0"
    profiles: tuple[NonEmptyStr, ...] = Field(min_length=3, max_length=3)
    cases: tuple[AssignmentCase, ...] = ()
    references: tuple[ReferencePost, ...] = ()
    generation_sources: tuple[GenerationSource, ...] = ()
    generation_sources_complete: bool = False

    @model_validator(mode="after")
    def validate_identities(self) -> Self:
        if len(set(self.profiles)) != 3:
            raise ValueError("three distinct profiles are required")
        if not {"ali-ghodsi", "matei-zaharia"} <= set(self.profiles):
            raise ValueError("the assignment requires ali-ghodsi and matei-zaharia")
        for items, attribute in ((self.cases, "case_id"), (self.references, "source_id")):
            identifiers = [getattr(item, attribute) for item in items]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"duplicate {attribute}")
        if any(item.profile_id not in self.profiles for item in self.cases) or any(
            item.profile_id not in self.profiles for item in self.references
        ):
            raise ValueError("case or reference names an undeclared profile")
        return self


class JudgePayload(ContractModel):
    voice_score: VoiceScore
    reasoning: NonBlankText
    reference_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    limitations: tuple[NonEmptyStr, ...]


class CaseJudgment(ContractModel):
    case_id: NonEmptyStr
    status: Literal["scored", "pending", "error"]
    reason: NonEmptyStr
    evidence_sha256: NonEmptyStr
    payload: JudgePayload | None = None
    provider: str | None = None
    model: str | None = None
    provider_request_id: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_score_state(self) -> Self:
        if (self.status == "scored") != (self.payload is not None):
            raise ValueError("only a scored judgment may contain a score")
        if self.status == "scored" and (not self.provider or not self.model):
            raise ValueError("scored judgments require provider and model provenance")
        return self


class JudgeBatch(ContractModel):
    prompt_version: Literal["assignment-voice-judge/1.0.0"] = "assignment-voice-judge/1.0.0"
    judgments: tuple[CaseJudgment, ...]

    @model_validator(mode="after")
    def validate_unique_cases(self) -> Self:
        identifiers = [item.case_id for item in self.judgments]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate judgment case_id")
        return self


class ProfileGate(ContractModel):
    profile_id: str
    status: Literal["passed", "failed", "pending"]
    completed_reviews: int
    required_reviews: Literal[10] = 10
    means: dict[str, float]
    blockers: tuple[str, ...]


class AssignmentReport(ContractModel):
    status: Literal["passed", "failed", "pending"]
    manual_gate: Literal["passed", "failed", "pending"]
    automated_status: Literal["complete", "pending"]
    profiles: tuple[ProfileGate, ...]
    automated_scored_cases: int
    required_cases: Literal[30] = 30
    blockers: tuple[str, ...]
    interpretation: str = (
        "Human review is the primary gate: each profile needs ten completed reviews and a mean "
        "of at least 4 on each of voice_accuracy, post_quality and naturalness. Automated 1-10 "
        "scores are developmental evidence and have no invented pass threshold."
    )
