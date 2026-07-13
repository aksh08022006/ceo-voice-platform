"""Generation use-case messages without generation behavior or API coupling."""

from uuid import UUID, uuid4

from pydantic import Field

from ceo_voice.models.base import NonBlankText, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import GenerationStatus, Platform
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
