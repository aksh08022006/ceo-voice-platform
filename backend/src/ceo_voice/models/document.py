"""Canonical source-document contracts."""

from uuid import UUID

from pydantic import Field, JsonValue

from ceo_voice.core.constants import DEFAULT_LANGUAGE_CODE
from ceo_voice.models.base import ContractModel, NonBlankText, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import DocumentSourceType, DocumentStatus, Platform


class Metadata(ContractModel):
    """Provenance and source attributes associated with one document.

    Attributes:
        source_type: Origin category used for policy and analysis routing.
        platform: Platform associated with the source, when meaningful.
        source_uri: Original source location; access controls apply outside this model.
        external_id: Stable identifier supplied by the source system.
        author: Claimed author name from the source.
        published_at: Source publication time when known.
        ingested_at: Time at which the platform accepted the source.
        language: BCP 47 language code reported or detected upstream.
        attributes: Source-specific values that do not warrant shared schema fields.
    """

    source_type: DocumentSourceType = Field(description="Origin category of the document.")
    platform: Platform | None = Field(
        default=None,
        description="Associated content platform when the source is platform-specific.",
    )
    source_uri: str | None = Field(default=None, description="Original source URI when known.")
    external_id: str | None = Field(
        default=None,
        description="Identifier assigned by the upstream source.",
    )
    author: str | None = Field(default=None, description="Author label reported by the source.")
    published_at: UtcDatetime | None = Field(
        default=None,
        description="UTC-normalized publication timestamp when known.",
    )
    ingested_at: UtcDatetime = Field(description="UTC timestamp of platform ingestion.")
    language: NonEmptyStr = Field(
        default=DEFAULT_LANGUAGE_CODE,
        description="BCP 47 language code associated with the content.",
    )
    attributes: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Validated JSON-compatible source-specific attributes.",
    )


class Document(ContractModel):
    """Immutable version of normalized source content.

    Attributes:
        id: Stable identifier for this canonical document.
        tenant_id: Ownership boundary for isolation and authorization.
        ceo_id: Leader to whom the document is attributed.
        version: Monotonically increasing content version.
        content: Original-fidelity normalized text; voice-significant formatting is retained.
        checksum: SHA-256 checksum used for integrity and deduplication.
        status: Eligibility of this version for downstream use.
        metadata: Provenance and source-specific attributes.
    """

    id: UUID = Field(description="Stable canonical document identifier.")
    tenant_id: UUID = Field(description="Tenant that owns the document.")
    ceo_id: UUID = Field(description="Leader to whom the document is attributed.")
    version: int = Field(default=1, ge=1, description="Monotonic document version.")
    content: NonBlankText = Field(
        description="Normalized text with voice-significant form retained exactly."
    )
    checksum: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
        description="Lowercase SHA-256 digest of the canonical content.",
    )
    status: DocumentStatus = Field(
        default=DocumentStatus.ACTIVE,
        description="Whether the document may participate in downstream processing.",
    )
    metadata: Metadata = Field(description="Document provenance and source attributes.")
