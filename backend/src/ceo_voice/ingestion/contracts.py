"""Typed contracts passed between ingestion boundaries."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import AnyUrl, Field, JsonValue, field_validator, model_validator

from ceo_voice.core.constants import DEFAULT_LANGUAGE_CODE
from ceo_voice.models.base import ContractModel, NonBlankText, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import ContentFormat, DocumentSourceType, DocumentType, Platform


class FetchRequest(ContractModel):
    """Tenant-scoped request passed to a source connector.

    Attributes:
        tenant_id: Tenant that owns all items returned for the request.
        ceo_id: Leader to whom returned source items are attributed.
        cursor: Opaque connector cursor from the previous successful fetch.
        modified_after: Optional lower timestamp bound for incremental connectors.
        limit: Maximum number of items the connector may yield.
        options: Source-specific, JSON-compatible connector options.
    """

    tenant_id: UUID = Field(description="Tenant that owns returned source items.")
    ceo_id: UUID = Field(description="Leader associated with returned source items.")
    cursor: str | None = Field(default=None, description="Opaque source cursor for resumption.")
    modified_after: UtcDatetime | None = Field(
        default=None,
        description="UTC lower bound for connectors supporting modified-since queries.",
    )
    limit: int = Field(default=100, ge=1, le=1_000, description="Maximum yielded item count.")
    options: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Validated source-specific connector options.",
    )


class ConnectorCapabilities(ContractModel):
    """Declarative capabilities used by orchestration without source-specific branching."""

    supports_cursor: bool = Field(description="Whether opaque cursor resumption is supported.")
    supports_modified_after: bool = Field(
        description="Whether timestamp-based incremental fetching is supported."
    )
    preserves_raw_bytes: bool = Field(
        default=True,
        description="Whether the connector yields the original received bytes.",
    )


class SourceItem(ContractModel):
    """Provider-neutral raw item emitted by every source connector.

    Source adapters translate API payloads, exports, or uploads into this envelope. They do not
    clean prose, infer metadata, or construct the canonical document.
    """

    external_id: NonEmptyStr = Field(description="Stable item identifier in the source system.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    ceo_id: UUID = Field(description="Leader associated with the source item.")
    source: DocumentSourceType = Field(description="Source family that produced the item.")
    raw_content: bytes = Field(min_length=1, description="Original bytes returned by the source.")
    content_format: ContentFormat = Field(description="Transport representation of raw content.")
    fetched_at: UtcDatetime = Field(description="UTC timestamp at which the item was acquired.")
    author: str | None = Field(default=None, description="Author claimed by the source.")
    platform: Platform | None = Field(
        default=None,
        description="Content platform when meaningful for the source.",
    )
    publication_date: UtcDatetime | None = Field(
        default=None,
        description="UTC-normalized publication timestamp when supplied.",
    )
    title: str | None = Field(default=None, description="Source-supplied title when available.")
    language_hint: str | None = Field(
        default=None,
        description="Source-supplied BCP 47 language hint.",
    )
    url: AnyUrl | None = Field(default=None, description="Canonical public source URL.")
    tags: tuple[NonEmptyStr, ...] = Field(
        default_factory=tuple,
        description="Source-supplied classification tags.",
    )
    metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Source-specific attributes retained for provenance.",
    )
    source_version: str | None = Field(
        default=None,
        description="ETag, revision, or other source-provided change token.",
    )
    cursor: str | None = Field(
        default=None,
        description="Opaque cursor that resumes after this item.",
    )
    encoding_hint: str | None = Field(
        default=None,
        description="Declared text encoding when the source provides one.",
    )

    @field_validator("tags")
    @classmethod
    def validate_unique_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Reject ambiguous duplicate tags without changing their order or spelling."""

        if len(value) != len(set(value)):
            raise ValueError("tags must be unique")
        return value


class RawDocument(ContractModel):
    """Immutable raw artifact persisted before parsing or cleaning."""

    id: UUID = Field(description="Stable raw-artifact identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    ceo_id: UUID = Field(description="Leader associated with the source item.")
    external_id: NonEmptyStr = Field(description="Item identifier in the source system.")
    source: DocumentSourceType = Field(description="Source family that produced the item.")
    raw_content: bytes = Field(min_length=1, description="Unmodified source bytes.")
    content_format: ContentFormat = Field(description="Transport representation of raw content.")
    raw_checksum: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
        description="SHA-256 digest of raw content.",
    )
    fetched_at: UtcDatetime = Field(description="UTC acquisition timestamp.")
    stored_at: UtcDatetime = Field(description="UTC raw-storage timestamp.")
    source_version: str | None = Field(default=None, description="Source change token.")
    cursor: str | None = Field(default=None, description="Opaque connector resume cursor.")
    attributes: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Unmodified provider-neutral provenance attributes.",
    )


class IngestionDocument(ContractModel):
    """Canonical working document shared by all source-independent pipeline stages.

    Raw bytes remain attached only while the pipeline constructs separate raw and clean storage
    projections. Clean repositories persist a raw-document reference rather than duplicating the
    raw payload.
    """

    id: UUID = Field(description="Stable canonical document identifier.")
    raw_document_id: UUID = Field(description="Associated immutable raw artifact.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    ceo_id: UUID = Field(description="Leader associated with the content.")
    external_id: NonEmptyStr = Field(description="Item identifier in the source system.")
    source: DocumentSourceType = Field(description="Source family that produced the content.")
    document_type: DocumentType = Field(description="Canonical source-independent content form.")
    author: NonEmptyStr = Field(description="Normalized author label.")
    platform: Platform | None = Field(description="Associated platform when meaningful.")
    publication_date: UtcDatetime | None = Field(description="UTC publication timestamp.")
    title: str | None = Field(description="Normalized document title when available.")
    content: NonBlankText = Field(description="Cleaned text with stylistic form preserved.")
    raw_content: bytes = Field(
        min_length=1, description="Original bytes retained during processing."
    )
    metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Extracted and source-provided JSON-compatible metadata.",
    )
    language: NonEmptyStr = Field(
        default=DEFAULT_LANGUAGE_CODE,
        description="BCP 47 language code.",
    )
    url: AnyUrl | None = Field(description="Canonical public source URL when available.")
    tags: tuple[NonEmptyStr, ...] = Field(
        default_factory=tuple,
        description="Ordered unique classification tags.",
    )
    raw_checksum: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
        description="SHA-256 digest of the original bytes.",
    )
    content_checksum: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
        description="SHA-256 digest of canonical clean text.",
    )
    fetched_at: UtcDatetime = Field(description="UTC source-acquisition timestamp.")
    processed_at: UtcDatetime = Field(description="UTC canonical-processing timestamp.")
    source_version: str | None = Field(default=None, description="Source change token.")
    version: int = Field(default=1, ge=1, description="Monotonic canonical document version.")

    @field_validator("tags")
    @classmethod
    def validate_unique_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require deterministic tag sets without silently rewriting caller input."""

        if len(value) != len(set(value)):
            raise ValueError("tags must be unique")
        return value


class ParsedContent(ContractModel):
    """Deterministically decoded source content before cleaning."""

    content: NonBlankText = Field(description="Decoded text with no cleaning applied.")
    encoding: NonEmptyStr = Field(description="Canonical codec used to decode source bytes.")
    content_format: ContentFormat = Field(description="Transport representation being cleaned.")
    parser_version: NonEmptyStr = Field(description="Version of the deterministic parser.")


class CleanedContent(ContractModel):
    """Style-preserving cleaning output and transformation lineage."""

    content: NonBlankText = Field(description="Clean text with meaningful style retained.")
    source_encoding: NonEmptyStr = Field(description="Codec used during parsing.")
    parser_version: NonEmptyStr = Field(description="Parser version used before cleaning.")
    cleaner_version: NonEmptyStr = Field(description="Cleaning-policy version.")
    applied_operations: tuple[NonEmptyStr, ...] = Field(
        default_factory=tuple,
        description="Ordered cleaning operations that changed the text.",
    )


class ExtractedMetadata(ContractModel):
    """Typed metadata projection stored separately from canonical content."""

    document_id: UUID = Field(description="Canonical document identifier.")
    document_version: int = Field(ge=1, description="Canonical document version.")
    raw_document_id: UUID = Field(description="Immutable raw-artifact identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    ceo_id: UUID = Field(description="Leader associated with the content.")
    external_id: NonEmptyStr = Field(description="Item identifier in the source system.")
    source: DocumentSourceType = Field(description="Source family.")
    document_type: DocumentType = Field(description="Canonical content form.")
    platform: Platform | None = Field(description="Associated platform when meaningful.")
    author: NonEmptyStr = Field(description="Normalized author label.")
    publication_date: UtcDatetime | None = Field(description="UTC publication timestamp.")
    fetched_at: UtcDatetime = Field(description="UTC acquisition timestamp.")
    processed_at: UtcDatetime = Field(description="UTC processing timestamp.")
    language: NonEmptyStr = Field(description="BCP 47 language code.")
    url: AnyUrl | None = Field(description="Canonical public source URL.")
    tags: tuple[NonEmptyStr, ...] = Field(description="Ordered classification tags.")
    content_length_characters: int = Field(ge=1, description="Unicode character count.")
    content_length_bytes: int = Field(ge=1, description="UTF-8 byte count.")
    word_count: int = Field(ge=0, description="Deterministic word count.")
    estimated_reading_time_seconds: int = Field(
        ge=0,
        description="Estimated reading time using the configured words-per-minute rate.",
    )
    raw_checksum: NonEmptyStr = Field(description="SHA-256 digest of source bytes.")
    content_checksum: NonEmptyStr = Field(description="SHA-256 digest of clean text.")
    metadata_schema_version: NonEmptyStr = Field(description="Metadata extractor schema version.")


class ValidationSeverity(StrEnum):
    """Severity assigned to an ingestion validation issue."""

    ERROR = "error"
    WARNING = "warning"


class ValidationIssue(ContractModel):
    """One machine-readable validation finding."""

    code: NonEmptyStr = Field(description="Stable issue code.")
    message: NonEmptyStr = Field(description="Safe operator-facing explanation.")
    severity: ValidationSeverity = Field(description="Whether processing must stop.")
    field: str | None = Field(default=None, description="Related field when applicable.")


class ValidationResult(ContractModel):
    """Complete non-short-circuiting validation result for one artifact."""

    is_valid: bool = Field(description="Whether no error-severity findings were produced.")
    issues: tuple[ValidationIssue, ...] = Field(
        default_factory=tuple,
        description="All validation findings in deterministic order.",
    )


class CleanDocument(ContractModel):
    """Durable clean-document projection referencing separately stored raw bytes."""

    id: UUID = Field(description="Stable canonical document identifier.")
    raw_document_id: UUID = Field(description="Associated immutable raw artifact.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    ceo_id: UUID = Field(description="Leader associated with the content.")
    external_id: NonEmptyStr = Field(description="Item identifier in the source system.")
    source: DocumentSourceType = Field(description="Source family.")
    document_type: DocumentType = Field(description="Canonical content form.")
    author: NonEmptyStr = Field(description="Normalized author label.")
    platform: Platform | None = Field(description="Associated platform when meaningful.")
    publication_date: UtcDatetime | None = Field(description="UTC publication timestamp.")
    title: str | None = Field(description="Normalized title when available.")
    content: NonBlankText = Field(description="Cleaned content with stylistic form retained.")
    metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Source and transformation metadata.",
    )
    language: NonEmptyStr = Field(description="BCP 47 language code.")
    url: AnyUrl | None = Field(description="Canonical public source URL.")
    tags: tuple[NonEmptyStr, ...] = Field(description="Ordered classification tags.")
    raw_checksum: NonEmptyStr = Field(description="SHA-256 digest of source bytes.")
    content_checksum: NonEmptyStr = Field(description="SHA-256 digest of clean text.")
    fetched_at: UtcDatetime = Field(description="UTC acquisition timestamp.")
    processed_at: UtcDatetime = Field(description="UTC processing timestamp.")
    source_version: str | None = Field(description="Source-provided revision token.")
    version: int = Field(ge=1, description="Monotonic canonical document version.")


class RepositoryWriteDisposition(StrEnum):
    """Outcome of an idempotent repository write."""

    CREATED = "created"
    UPDATED = "updated"
    ALREADY_EXISTS = "already_exists"


class ConnectorCheckpoint(ContractModel):
    """Successful connector progress used to seed a later incremental fetch."""

    connector_id: NonEmptyStr = Field(description="Stable connector identifier.")
    tenant_id: UUID = Field(description="Tenant checkpoint boundary.")
    ceo_id: UUID = Field(description="Leader checkpoint boundary.")
    cursor: str | None = Field(description="Opaque connector cursor after the successful batch.")
    modified_after: UtcDatetime | None = Field(
        description="Timestamp lower bound suggested for the next fetch."
    )
    last_successful_fetch_at: UtcDatetime = Field(description="UTC successful fetch timestamp.")
    updated_at: UtcDatetime = Field(description="UTC checkpoint write timestamp.")


class DocumentChangeKind(StrEnum):
    """Incremental-processing decision for a source item."""

    NEW = "new"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    DUPLICATE = "duplicate"


class DocumentChangeDecision(ContractModel):
    """Auditable incremental decision made before or after normalization."""

    kind: DocumentChangeKind = Field(description="Required processing disposition.")
    next_version: int | None = Field(
        default=None,
        ge=1,
        description="Version to persist for new or changed content.",
    )
    existing_document_id: UUID | None = Field(
        default=None,
        description="Related stored document for changed, unchanged, or duplicate content.",
    )
    existing_version: int | None = Field(
        default=None,
        ge=1,
        description="Version of the related stored document.",
    )
    reason: NonEmptyStr = Field(description="Stable human-readable decision rationale.")

    @model_validator(mode="after")
    def validate_version_semantics(self) -> Self:
        """Require a write version only for decisions that continue processing."""

        if self.kind in {DocumentChangeKind.NEW, DocumentChangeKind.CHANGED}:
            if self.next_version is None:
                raise ValueError("new and changed decisions require next_version")
        elif self.next_version is not None:
            raise ValueError("unchanged and duplicate decisions must not set next_version")
        return self
