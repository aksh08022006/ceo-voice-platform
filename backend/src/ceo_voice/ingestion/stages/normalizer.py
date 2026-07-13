"""Source-independent document normalization stage."""

from collections.abc import Mapping
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from pydantic import JsonValue

from ceo_voice.core.constants import DEFAULT_LANGUAGE_CODE
from ceo_voice.core.exceptions import DataIngestionError
from ceo_voice.ingestion.contracts import (
    CleanedContent,
    IngestionDocument,
    RawDocument,
    SourceItem,
)
from ceo_voice.models.enums import DocumentSourceType, DocumentType, Platform
from ceo_voice.utils.hashing import sha256_bytes, sha256_text

_DEFAULT_DOCUMENT_TYPES: Mapping[DocumentSourceType, DocumentType] = {
    DocumentSourceType.X: DocumentType.SOCIAL_POST,
    DocumentSourceType.LINKEDIN: DocumentType.SOCIAL_POST,
    DocumentSourceType.YOUTUBE: DocumentType.VIDEO_TRANSCRIPT,
    DocumentSourceType.VIDEO: DocumentType.VIDEO_TRANSCRIPT,
    DocumentSourceType.PODCAST: DocumentType.PODCAST_TRANSCRIPT,
    DocumentSourceType.EARNINGS_CALL: DocumentType.EARNINGS_CALL_TRANSCRIPT,
    DocumentSourceType.BLOG: DocumentType.BLOG_POST,
    DocumentSourceType.INTERVIEW: DocumentType.INTERVIEW_TRANSCRIPT,
    DocumentSourceType.SHAREHOLDER_LETTER: DocumentType.SHAREHOLDER_LETTER,
    DocumentSourceType.CONFERENCE_TALK: DocumentType.CONFERENCE_TALK_TRANSCRIPT,
    DocumentSourceType.NEWSLETTER: DocumentType.NEWSLETTER,
    DocumentSourceType.FILE_UPLOAD: DocumentType.OTHER,
    DocumentSourceType.OTHER: DocumentType.OTHER,
}
_DEFAULT_PLATFORMS: Mapping[DocumentSourceType, Platform] = {
    DocumentSourceType.X: Platform.X,
    DocumentSourceType.LINKEDIN: Platform.LINKEDIN,
    DocumentSourceType.YOUTUBE: Platform.YOUTUBE,
    DocumentSourceType.VIDEO: Platform.YOUTUBE,
    DocumentSourceType.PODCAST: Platform.PODCAST,
    DocumentSourceType.BLOG: Platform.BLOG,
    DocumentSourceType.NEWSLETTER: Platform.NEWSLETTER,
}


class RawDocumentFactory:
    """Project a connector item into an immutable raw-storage artifact."""

    def create(self, item: SourceItem, *, stored_at: datetime) -> RawDocument:
        """Create a content-addressed raw artifact from one source item."""

        raw_checksum = sha256_bytes(item.raw_content)
        identity = _source_identity(item)
        attributes: dict[str, JsonValue] = dict(item.metadata)
        attributes.update(
            {
                "author": item.author,
                "platform": item.platform.value if item.platform else None,
                "publication_date": (
                    item.publication_date.isoformat() if item.publication_date else None
                ),
                "title": item.title,
                "language_hint": item.language_hint,
                "url": str(item.url) if item.url else None,
                "tags": list(item.tags),
                "encoding_hint": item.encoding_hint,
            }
        )
        return RawDocument(
            id=uuid5(NAMESPACE_URL, f"{identity}:raw:{raw_checksum}"),
            tenant_id=item.tenant_id,
            ceo_id=item.ceo_id,
            external_id=item.external_id,
            source=item.source,
            raw_content=item.raw_content,
            content_format=item.content_format,
            raw_checksum=raw_checksum,
            fetched_at=item.fetched_at,
            stored_at=stored_at,
            source_version=item.source_version,
            cursor=item.cursor,
            attributes=attributes,
        )


class DocumentNormalizer:
    """Map source items and clean text into the common ingestion document schema."""

    def __init__(
        self,
        *,
        document_types: Mapping[DocumentSourceType, DocumentType] = _DEFAULT_DOCUMENT_TYPES,
        default_platforms: Mapping[DocumentSourceType, Platform] = _DEFAULT_PLATFORMS,
    ) -> None:
        self._document_types = dict(document_types)
        self._default_platforms = dict(default_platforms)

    def normalize(
        self,
        item: SourceItem,
        raw_document: RawDocument,
        cleaned: CleanedContent,
        *,
        processed_at: datetime,
        version: int = 1,
    ) -> IngestionDocument:
        """Create a canonical document after checking cross-stage lineage."""

        self._validate_lineage(item, raw_document)
        if not item.author or not item.author.strip():
            raise DataIngestionError(
                "Source item is missing a usable author.",
                details={"source": item.source.value, "external_id": item.external_id},
            )
        try:
            document_type = self._document_types[item.source]
        except KeyError as exc:
            raise DataIngestionError(
                "Source has no configured canonical document type.",
                details={"source": item.source.value},
            ) from exc

        metadata: dict[str, JsonValue] = dict(item.metadata)
        metadata["transformations"] = {
            "parser_version": cleaned.parser_version,
            "cleaner_version": cleaned.cleaner_version,
            "operations": list(cleaned.applied_operations),
            "source_encoding": cleaned.source_encoding,
        }
        identity = _source_identity(item)
        return IngestionDocument(
            id=uuid5(NAMESPACE_URL, f"{identity}:canonical"),
            raw_document_id=raw_document.id,
            tenant_id=item.tenant_id,
            ceo_id=item.ceo_id,
            external_id=item.external_id,
            source=item.source,
            document_type=document_type,
            author=item.author.strip(),
            platform=item.platform or self._default_platforms.get(item.source),
            publication_date=item.publication_date,
            title=item.title.strip() if item.title else None,
            content=cleaned.content,
            raw_content=item.raw_content,
            metadata=metadata,
            language=(item.language_hint or DEFAULT_LANGUAGE_CODE).strip(),
            url=item.url,
            tags=item.tags,
            raw_checksum=raw_document.raw_checksum,
            content_checksum=sha256_text(cleaned.content),
            fetched_at=item.fetched_at,
            processed_at=processed_at,
            source_version=item.source_version,
            version=version,
        )

    @staticmethod
    def _validate_lineage(item: SourceItem, raw_document: RawDocument) -> None:
        expected = (
            item.tenant_id,
            item.ceo_id,
            item.external_id,
            item.source,
            sha256_bytes(item.raw_content),
        )
        actual = (
            raw_document.tenant_id,
            raw_document.ceo_id,
            raw_document.external_id,
            raw_document.source,
            raw_document.raw_checksum,
        )
        if actual != expected:
            raise DataIngestionError(
                "Raw artifact does not match its source item.",
                details={"source": item.source.value, "external_id": item.external_id},
            )


def _source_identity(item: SourceItem) -> str:
    return f"ceo-voice:{item.tenant_id}:{item.ceo_id}:{item.source.value}:{item.external_id}"
