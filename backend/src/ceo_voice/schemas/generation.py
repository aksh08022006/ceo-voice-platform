"""Generation use-case messages without generation behavior or API coupling."""

from uuid import UUID, uuid4

from pydantic import Field, model_validator

from ceo_voice.models.base import NonBlankText, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import ContentType, GenerationStatus, Platform
from ceo_voice.models.evaluation import EvaluationResult
from ceo_voice.schemas.base import BoundarySchema


class GenerationRequest(BoundarySchema):
    """Validated request to a future generation use case.

    The message references versioned evidence and voice artifacts by identifier. It does not
    contain prompts or model parameters, keeping callers independent from implementation choices.
    """

    request_id: UUID = Field(
        default_factory=uuid4,
        description="Idempotency and trace identifier for this request.",
    )
    tenant_id: UUID = Field(description="Tenant authorizing and owning the request.")
    ceo_id: UUID = Field(description="Leader whose voice should govern the output.")
    voice_profile_id: UUID = Field(description="Explicit voice-profile lineage to use.")
    voice_profile_version: int = Field(
        ge=1,
        description="Pinned voice-profile version for reproducibility.",
    )
    platform: Platform = Field(description="Target content platform.")
    content_type: ContentType = Field(
        default=ContentType.POST,
        description="Requested output shape; threads are validated against platform policy.",
    )
    thread_post_count: int | None = Field(
        default=None,
        ge=2,
        le=5,
        description="Exact requested thread length; present only for thread requests.",
    )
    virality_influence: float = Field(
        default=0.125,
        ge=0,
        le=0.25,
        description="Bounded structural influence; voice remains dominant at every setting.",
    )
    minimum_words: int | None = Field(
        default=None,
        ge=1,
        le=2_000,
        description="Optional deterministic lower word-count bound.",
    )
    maximum_words: int | None = Field(
        default=None,
        ge=1,
        le=2_000,
        description="Optional deterministic upper word-count bound.",
    )
    topic: NonEmptyStr = Field(description="Subject the content should address.")
    objective: NonEmptyStr = Field(description="Intended communication outcome.")
    audience: NonEmptyStr = Field(description="Intended reader segment.")
    source_document_ids: tuple[UUID, ...] = Field(
        default_factory=tuple,
        description="Pinned factual sources available for evidence retrieval.",
    )
    constraints: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Caller-supplied content constraints, not prompt instructions.",
    )
    candidate_count: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Number of independently traceable candidates requested.",
    )

    @model_validator(mode="after")
    def validate_output_shape(self) -> "GenerationRequest":
        """Keep thread and word bounds internally consistent before orchestration."""

        if self.content_type is ContentType.THREAD:
            if self.platform is not Platform.X:
                raise ValueError("thread output is supported only for X")
            if self.thread_post_count is None:
                raise ValueError("thread requests require thread_post_count")
        elif self.thread_post_count is not None:
            raise ValueError("thread_post_count is allowed only for thread requests")
        if (
            self.minimum_words is not None
            and self.maximum_words is not None
            and self.minimum_words > self.maximum_words
        ):
            raise ValueError("minimum_words cannot exceed maximum_words")
        return self


class GenerationCandidate(BoundarySchema):
    """One generated candidate and its optional evaluation record."""

    id: UUID = Field(default_factory=uuid4, description="Stable candidate identifier.")
    content: NonBlankText = Field(
        description="Generated content returned without whitespace-destructive validation."
    )
    evaluation: EvaluationResult | None = Field(
        default=None,
        description="Evaluation attached when the configured pipeline completed it.",
    )


class GenerationResponse(BoundarySchema):
    """Transport-neutral response from a future generation use case."""

    request_id: UUID = Field(description="Identifier copied from the corresponding request.")
    status: GenerationStatus = Field(description="Overall completion state.")
    candidates: tuple[GenerationCandidate, ...] = Field(
        default_factory=tuple,
        description="Generated candidates that completed successfully.",
    )
    error_codes: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Stable error codes explaining a partial or failed outcome.",
    )
    created_at: UtcDatetime = Field(description="UTC response creation timestamp.")
