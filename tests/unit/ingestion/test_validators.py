"""Tests for non-short-circuiting ingestion validation."""

from datetime import datetime, timedelta
from uuid import UUID

import pytest

from ceo_voice.ingestion import (
    ContentParser,
    DocumentCleaner,
    DocumentNormalizer,
    DocumentValidator,
    IngestionDocument,
    RawDocumentFactory,
    SourceItem,
    SourceItemValidator,
)
from ceo_voice.models import ContentFormat, DocumentSourceType
from ceo_voice.utils.hashing import sha256_text


def _source_item(
    *,
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
    raw_content: bytes = b"A valid source item.",
    author: str | None = "Example CEO",
    publication_date: datetime | None = None,
    language_hint: str | None = "en",
) -> SourceItem:
    return SourceItem(
        external_id="item-1",
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        source=DocumentSourceType.BLOG,
        raw_content=raw_content,
        content_format=ContentFormat.PLAIN_TEXT,
        fetched_at=fixed_time,
        publication_date=publication_date or fixed_time,
        author=author,
        language_hint=language_hint,
    )


def _canonical(item: SourceItem, processed_at: datetime) -> IngestionDocument:
    raw = RawDocumentFactory().create(item, stored_at=processed_at)
    cleaned = DocumentCleaner().clean(ContentParser().parse(item))
    return DocumentNormalizer().normalize(item, raw, cleaned, processed_at=processed_at)


def test_source_validator_returns_all_errors_without_mutation(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        raw_content=b"too large",
        author=None,
        publication_date=fixed_time + timedelta(minutes=10),
        language_hint="not_a_language",
    )
    validator = SourceItemValidator(max_raw_bytes=3, clock=lambda: fixed_time)

    result = validator.validate(item)

    assert result.is_valid is False
    assert [issue.code for issue in result.issues] == [
        "missing_author",
        "raw_content_too_large",
        "future_publication_date",
        "malformed_language",
    ]
    assert item.raw_content == b"too large"


def test_source_validator_accepts_valid_item(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = _source_item(tenant_id=tenant_id, ceo_id=ceo_id, fixed_time=fixed_time)

    result = SourceItemValidator(clock=lambda: fixed_time).validate(item)

    assert result.is_valid is True
    assert result.issues == ()


def test_document_validator_detects_integrity_encoding_and_timestamp_errors(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = _source_item(tenant_id=tenant_id, ceo_id=ceo_id, fixed_time=fixed_time)
    document = _canonical(item, fixed_time)
    invalid = document.model_copy(
        update={
            "raw_checksum": "0" * 64,
            "content": "Damaged \ufffd content",
            "content_checksum": sha256_text("different content"),
            "processed_at": fixed_time - timedelta(seconds=1),
            "publication_date": fixed_time + timedelta(minutes=10),
            "language": "bad_language",
        }
    )

    result = DocumentValidator(clock=lambda: fixed_time).validate(invalid)

    assert result.is_valid is False
    assert {issue.code for issue in result.issues} == {
        "raw_checksum_mismatch",
        "content_checksum_mismatch",
        "processing_before_fetch",
        "future_publication_date",
        "malformed_language",
        "replacement_character",
    }


def test_document_validator_accepts_valid_document(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = _source_item(tenant_id=tenant_id, ceo_id=ceo_id, fixed_time=fixed_time)
    document = _canonical(item, fixed_time)

    result = DocumentValidator(clock=lambda: fixed_time).validate(document)

    assert result.is_valid is True
    assert result.issues == ()


def test_validator_configuration_rejects_invalid_limits() -> None:
    with pytest.raises(ValueError, match="max_raw_bytes must be positive"):
        SourceItemValidator(max_raw_bytes=0)
    with pytest.raises(ValueError, match="future_tolerance must be non-negative"):
        SourceItemValidator(future_tolerance=timedelta(seconds=-1))
    with pytest.raises(ValueError, match="future_tolerance must be non-negative"):
        DocumentValidator(future_tolerance=timedelta(seconds=-1))
