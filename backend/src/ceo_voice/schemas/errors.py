"""Transport-neutral error response schemas."""

from uuid import UUID

from pydantic import Field, JsonValue

from ceo_voice.models.base import NonEmptyStr
from ceo_voice.schemas.base import BoundarySchema


class ErrorDetail(BoundarySchema):
    """Safe error content suitable for external transport."""

    code: NonEmptyStr = Field(description="Stable machine-readable error code.")
    message: NonEmptyStr = Field(description="Safe human-readable error description.")
    retryable: bool = Field(description="Whether a caller may safely retry the operation.")
    details: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Safe structured details with secrets and personal data removed.",
    )


class ErrorResponse(BoundarySchema):
    """Request-correlated error envelope."""

    request_id: UUID | None = Field(
        default=None,
        description="Request identifier when one was established before failure.",
    )
    error: ErrorDetail = Field(description="Structured failure information.")
