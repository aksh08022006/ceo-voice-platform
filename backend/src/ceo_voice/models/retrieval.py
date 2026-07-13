"""Transport-neutral retrieval result contracts."""

from uuid import UUID

from pydantic import Field, JsonValue

from ceo_voice.models.base import ContractModel, NonBlankText, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import ContextRole


class RetrievedItem(ContractModel):
    """One ranked piece of evidence selected for a downstream use case."""

    document_id: UUID = Field(description="Canonical source document identifier.")
    content: NonBlankText = Field(
        description="Evidence text selected without destructive whitespace normalization."
    )
    role: ContextRole = Field(description="Purpose of this item in the assembled context.")
    score: float = Field(description="Retriever-specific relevance score.")
    rank: int = Field(ge=1, description="One-based rank within the returned context.")
    attributes: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="JSON-compatible provenance and diagnostic attributes.",
    )


class RetrievedContext(ContractModel):
    """Auditable set of ranked evidence returned by a retriever.

    Explicit roles keep voice exemplars, factual grounding, and structural references separate;
    downstream builders do not have to infer why a text fragment was retrieved.
    """

    trace_id: UUID = Field(description="Identifier linking retrieval decisions to later output.")
    query: NonEmptyStr = Field(description="Canonical retrieval intent or query.")
    items: tuple[RetrievedItem, ...] = Field(
        default_factory=tuple,
        description="Ranked evidence with explicit downstream roles.",
    )
    generated_at: UtcDatetime = Field(description="UTC context assembly timestamp.")
