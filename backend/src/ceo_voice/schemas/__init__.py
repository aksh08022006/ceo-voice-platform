"""Input and output schemas for application boundaries."""

from ceo_voice.schemas.errors import ErrorDetail, ErrorResponse
from ceo_voice.schemas.generation import (
    GenerationCandidate,
    GenerationRequest,
    GenerationResponse,
)

__all__ = [
    "ErrorDetail",
    "ErrorResponse",
    "GenerationCandidate",
    "GenerationRequest",
    "GenerationResponse",
]
