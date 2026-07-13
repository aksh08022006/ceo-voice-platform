"""Tests for raw projection, normalization, and metadata extraction."""

from datetime import datetime
from uuid import UUID

import pytest

from ceo_voice.core.exceptions import DataIngestionError
from ceo_voice.ingestion import (
    ContentParser,
    DocumentCleaner,
    DocumentNormalizer,
    IngestionDocument,
    MetadataExtractor,
    RawDocument,
    RawDocumentFactory,
    SourceItem,
)
from ceo_voice.models import ContentFormat, DocumentSourceType, DocumentType, Platform


def _source_item(
    *,
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
    source: DocumentSourceType = DocumentSourceType.LINKEDIN,
    external_id: str = "item-1",
    raw_content: bytes = b"One useful operating lesson.",
    author: str | None = "Example CEO",
) -> SourceItem:
    return SourceItem(
        external_id=external_id,
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        source=source,
        raw_content=raw_content,
        content_format=ContentFormat.PLAIN_TEXT,
        fetched_at=fixed_time,
        publication_date=fixed_time,
        author=author,
        title="  A useful title  ",
        language_hint="en",
        metadata={"provider_field": "retained"},
        tags=("operations",),
        url="https://example.com/item-1",
    )


def _normalize(item: SourceItem, fixed_time: datetime) -> tuple[RawDocument, IngestionDocument]:
    raw = RawDocumentFactory().create(item, stored_at=fixed_time)
    parsed = ContentParser().parse(item)
    cleaned = DocumentCleaner().clean(parsed)
    return raw, DocumentNormalizer().normalize(item, raw, cleaned, processed_at=fixed_time)


@pytest.mark.parametrize(
    ("source", "expected_type"),
    [
        (DocumentSourceType.X, DocumentType.SOCIAL_POST),
        (DocumentSourceType.LINKEDIN, DocumentType.SOCIAL_POST),
        (DocumentSourceType.YOUTUBE, DocumentType.VIDEO_TRANSCRIPT),
        (DocumentSourceType.PODCAST, DocumentType.PODCAST_TRANSCRIPT),
        (DocumentSourceType.EARNINGS_CALL, DocumentType.EARNINGS_CALL_TRANSCRIPT),
        (DocumentSourceType.BLOG, DocumentType.BLOG_POST),
        (DocumentSourceType.INTERVIEW, DocumentType.INTERVIEW_TRANSCRIPT),
        (DocumentSourceType.SHAREHOLDER_LETTER, DocumentType.SHAREHOLDER_LETTER),
        (DocumentSourceType.CONFERENCE_TALK, DocumentType.CONFERENCE_TALK_TRANSCRIPT),
    ],
)
def test_normalizer_maps_supported_sources_without_connector_logic(
    source: DocumentSourceType,
    expected_type: DocumentType,
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = _source_item(tenant_id=tenant_id, ceo_id=ceo_id, fixed_time=fixed_time, source=source)

    _, document = _normalize(item, fixed_time)

    assert document.document_type is expected_type
    assert document.metadata["provider_field"] == "retained"
    assert document.title == "A useful title"


def test_raw_artifacts_are_content_addressed_but_canonical_identity_is_stable(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    first_item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content=b"First version",
    )
    changed_item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content=b"Changed version",
    )

    first_raw, first_document = _normalize(first_item, fixed_time)
    changed_raw, changed_document = _normalize(changed_item, fixed_time)

    assert first_raw.id != changed_raw.id
    assert first_raw.raw_checksum != changed_raw.raw_checksum
    assert first_document.id == changed_document.id
    assert first_document.raw_document_id != changed_document.raw_document_id


def test_normalizer_defaults_platform_and_records_transform_lineage(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = _source_item(tenant_id=tenant_id, ceo_id=ceo_id, fixed_time=fixed_time)

    _, document = _normalize(item, fixed_time)

    assert document.platform is Platform.LINKEDIN
    assert document.metadata["transformations"] == {
        "parser_version": "text-parser-v1",
        "cleaner_version": "style-preserving-cleaner-v1",
        "operations": [],
        "source_encoding": "utf-8-sig",
    }


def test_normalizer_rejects_missing_author_and_broken_lineage(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    valid = _source_item(tenant_id=tenant_id, ceo_id=ceo_id, fixed_time=fixed_time)
    missing_author = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        author=None,
    )
    unrelated = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        external_id="different-item",
    )
    unrelated_raw = RawDocumentFactory().create(unrelated, stored_at=fixed_time)
    cleaned_valid = DocumentCleaner().clean(ContentParser().parse(valid))
    cleaned_missing = DocumentCleaner().clean(ContentParser().parse(missing_author))

    with pytest.raises(DataIngestionError, match="does not match"):
        DocumentNormalizer().normalize(
            valid,
            unrelated_raw,
            cleaned_valid,
            processed_at=fixed_time,
        )

    missing_raw = RawDocumentFactory().create(missing_author, stored_at=fixed_time)
    with pytest.raises(DataIngestionError, match="missing a usable author"):
        DocumentNormalizer().normalize(
            missing_author,
            missing_raw,
            cleaned_missing,
            processed_at=fixed_time,
        )


def test_normalizer_requires_an_explicit_source_mapping(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = _source_item(tenant_id=tenant_id, ceo_id=ceo_id, fixed_time=fixed_time)
    raw = RawDocumentFactory().create(item, stored_at=fixed_time)
    cleaned = DocumentCleaner().clean(ContentParser().parse(item))

    with pytest.raises(DataIngestionError, match="no configured canonical document type"):
        DocumentNormalizer(document_types={}).normalize(
            item,
            raw,
            cleaned,
            processed_at=fixed_time,
        )


def test_metadata_extractor_calculates_deterministic_lengths_and_reading_time(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    content = " ".join(f"word{index}" for index in range(200))
    item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content=content.encode(),
    )
    _, document = _normalize(item, fixed_time)

    metadata = MetadataExtractor().extract(document)

    assert metadata.document_id == document.id
    assert metadata.ceo_id == ceo_id
    assert metadata.word_count == 200
    assert metadata.content_length_characters == len(content)
    assert metadata.content_length_bytes == len(content.encode())
    assert metadata.estimated_reading_time_seconds == 60


def test_metadata_extractor_requires_positive_reading_rate() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        MetadataExtractor(reading_words_per_minute=0)
