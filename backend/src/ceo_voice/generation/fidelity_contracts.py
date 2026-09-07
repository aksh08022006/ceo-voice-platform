"""Bounded claim-review contracts; model judgments are never human approval."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ceo_voice.generation.enums import ProviderName
from ceo_voice.models.base import ContractModel, NonBlankText

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ReviewText = Annotated[NonBlankText, Field(max_length=2_000)]
SourceAuthority = Literal["brief", "constraint", "factual_source", "attributed_context"]
ClaimVerdict = Literal["supported", "contradicted", "unsupported", "uncertain"]


class FidelityPolicy(ContractModel):
    enabled: bool = False
    review_format: Literal["atomic_spans", "sentence_verdicts"] = "atomic_spans"
    failure_behavior: Literal["raise", "return_for_review"] = "raise"
    model: str = Field(default="", max_length=200)
    maximum_prompt_bytes: int = Field(default=48_000, ge=1_000, le=200_000)
    maximum_output_tokens: int = Field(default=6_000, ge=256, le=16_000)
    maximum_response_bytes: int = Field(default=100_000, ge=1_000, le=250_000)
    maximum_candidate_characters: int = Field(default=12_000, ge=1, le=20_000)
    maximum_units: int = Field(default=64, ge=1, le=128)
    maximum_sources: int = Field(default=32, ge=1, le=64)
    timeout_seconds: float = Field(default=45, gt=0, le=120)


class ExactSpan(ContractModel):
    """Python/Unicode code-point offsets, end exclusive; never UTF-16 offsets."""

    start: int = Field(strict=True, ge=0, le=200_000)
    end: int = Field(strict=True, ge=1, le=200_000)
    text: NonBlankText = Field(max_length=20_000)

    @model_validator(mode="after")
    def valid_extent(self) -> Self:
        if self.end <= self.start or self.end - self.start != len(self.text):
            raise ValueError("span extent must equal its exact Unicode text length")
        return self


class CandidateUnit(ExactSpan):
    unit_id: str = Field(pattern=r"^u[0-9]{3}$")


class BriefSource(ContractModel):
    source_id: str = Field(min_length=1, max_length=100)
    authority: SourceAuthority
    text: NonBlankText = Field(max_length=20_000)


class SourceDigest(ContractModel):
    source_id: str = Field(min_length=1, max_length=100)
    authority: SourceAuthority
    sha256: Digest


class EvidenceCitation(ExactSpan):
    source_id: str = Field(min_length=1, max_length=100)


class ClaimAssessment(ContractModel):
    span: ExactSpan
    kind: Literal["factual", "attributed_statement", "editorial_expression"]
    verdict: ClaimVerdict
    aspects: tuple[
        Literal[
            "general",
            "causality",
            "quantity",
            "negation",
            "modality",
            "time_status",
            "attribution",
            "experience",
        ],
        ...,
    ] = Field(min_length=1, max_length=8)
    reason: ReviewText
    citations: tuple[EvidenceCitation, ...] = Field(max_length=8)

    @model_validator(mode="after")
    def evidence_required(self) -> Self:
        if self.verdict in ("supported", "contradicted") and not self.citations:
            raise ValueError("supported and contradicted verdicts require exact evidence citations")
        if len(set(self.aspects)) != len(self.aspects):
            raise ValueError("duplicate review aspects")
        return self


class UnitAssessment(ContractModel):
    unit_id: str = Field(pattern=r"^u[0-9]{3}$")
    claims: tuple[ClaimAssessment, ...] = Field(min_length=1, max_length=16)


class FidelityPayload(ContractModel):
    candidate_sha256: Digest
    units: tuple[UnitAssessment, ...] = Field(min_length=1, max_length=128)


class FidelityReview(ContractModel):
    version: Literal["claim-review/1.0.0"] = "claim-review/1.0.0"
    candidate_sha256: Digest
    status: Literal["clear", "blocked", "error"]
    units: tuple[CandidateUnit, ...] = Field(default=(), max_length=128)
    sources: tuple[SourceDigest, ...] = Field(default=(), max_length=64)
    assessment: FidelityPayload | None = None
    provider: ProviderName
    model: str = Field(max_length=200)
    provider_request_id: str | None = Field(default=None, max_length=500)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    error_code: str | None = Field(default=None, max_length=100)
    provider_http_status: int | None = Field(default=None, ge=100, le=599)
    human_approval_required: Literal[True] = True
    provider_call_attempted: bool = False
    aligned_span_count: int = Field(default=0, ge=0)

    @property
    def approval_eligible(self) -> bool:
        """Eligibility for a named human decision, never approval itself."""
        return self.status == "clear"

    @model_validator(mode="after")
    def coherent_disposition(self) -> Self:
        if self.status == "error":
            if not self.error_code or self.assessment is not None:
                raise ValueError("failed review requires an error and no accepted assessment")
        else:
            if self.assessment is None or self.error_code is not None:
                raise ValueError("completed review requires an assessment and no error")
            if self.assessment.candidate_sha256 != self.candidate_sha256:
                raise ValueError("review candidate binding mismatch")
            blocked = any(c.verdict != "supported" for u in self.assessment.units for c in u.claims)
            if (self.status == "blocked") != blocked:
                raise ValueError("review disposition does not match claim verdicts")
        return self
