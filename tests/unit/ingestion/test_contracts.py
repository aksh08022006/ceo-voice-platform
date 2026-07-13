"""Tests for common ingestion contracts and connector substitutability."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.ingestion import (
    ConnectorCapabilities,
    ConnectorCheckpoint,
    FetchRequest,
    IngestionDocument,
    IngestionItemResult,
    IngestionItemStatus,
    IngestionRunResult,
    IngestionRunStatus,
    SourceConnector,
    SourceItem,
    ValidationIssue,
    ValidationSeverity,
)
from ceo_voice.models import ContentFormat, DocumentSourceType, DocumentType, Platform


class FakeConnector:
    """Minimal connector proving that the protocol requires no base-class coupling."""

    connector_id = "fake-linkedin"
    source_type = DocumentSourceType.LINKEDIN
    capabilities = ConnectorCapabilities(
        supports_cursor=True,
        supports_modified_after=True,
    )

    def __init__(self, item: SourceItem) -> None:
        self._item = item

    async def fetch(self, request: FetchRequest) -> AsyncIterator[SourceItem]:
        if request.limit > 0:
            yield self._item


def test_all_required_source_families_are_explicit() -> None:
    required = {
        DocumentSourceType.X,
        DocumentSourceType.LINKEDIN,
        DocumentSourceType.YOUTUBE,
        DocumentSourceType.PODCAST,
        DocumentSourceType.EARNINGS_CALL,
        DocumentSourceType.BLOG,
        DocumentSourceType.INTERVIEW,
        DocumentSourceType.SHAREHOLDER_LETTER,
        DocumentSourceType.CONFERENCE_TALK,
    }

    assert required.issubset(set(DocumentSourceType))


def test_source_item_preserves_bytes_and_normalizes_timestamps(
    tenant_id: UUID,
    ceo_id: UUID,
) -> None:
    local_time = datetime(2026, 7, 13, 15, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    item = SourceItem(
        external_id="post-1",
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        source=DocumentSourceType.LINKEDIN,
        raw_content=b"  First line.\n\nSecond line.  ",
        content_format=ContentFormat.PLAIN_TEXT,
        fetched_at=local_time,
        publication_date=local_time,
        platform=Platform.LINKEDIN,
        url="https://www.linkedin.com/posts/example",
        tags=("leadership", "operations"),
    )

    assert item.raw_content.startswith(b"  ")
    assert item.fetched_at == datetime(2026, 7, 13, 9, 30, tzinfo=UTC)
    assert str(item.url) == "https://www.linkedin.com/posts/example"


def test_source_item_rejects_missing_content_and_duplicate_tags(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    base = {
        "external_id": "post-1",
        "tenant_id": tenant_id,
        "ceo_id": ceo_id,
        "source": DocumentSourceType.X,
        "content_format": ContentFormat.PLAIN_TEXT,
        "fetched_at": fixed_time,
    }

    with pytest.raises(ValidationError, match="at least 1 byte"):
        SourceItem(raw_content=b"", **base)
    with pytest.raises(ValidationError, match="tags must be unique"):
        SourceItem(raw_content=b"text", tags=("same", "same"), **base)


def test_ingestion_document_contains_common_source_independent_fields(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    document = IngestionDocument(
        id=UUID("30000000-0000-0000-0000-000000000003"),
        raw_document_id=UUID("40000000-0000-0000-0000-000000000004"),
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        external_id="episode-42",
        source=DocumentSourceType.PODCAST,
        document_type=DocumentType.PODCAST_TRANSCRIPT,
        author="Example CEO",
        platform=Platform.PODCAST,
        publication_date=fixed_time,
        title="Operating at scale",
        content="  Preserved opening.\n\nPreserved ending.  ",
        raw_content=b"  Preserved opening.\n\nPreserved ending.  ",
        metadata={"episode": 42},
        language="en",
        url="https://example.com/episodes/42",
        tags=("operations",),
        raw_checksum="a" * 64,
        source_fingerprint="b" * 64,
        content_checksum="c" * 64,
        document_fingerprint="d" * 64,
        fetched_at=fixed_time,
        processed_at=fixed_time,
    )

    assert document.content.startswith("  ")
    assert document.raw_content.startswith(b"  ")
    assert document.document_type is DocumentType.PODCAST_TRANSCRIPT
    assert document.metadata == {"episode": 42}


def test_connector_protocol_is_structural_and_async(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = SourceItem(
        external_id="post-1",
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        source=DocumentSourceType.LINKEDIN,
        raw_content=b"A post",
        content_format=ContentFormat.PLAIN_TEXT,
        fetched_at=fixed_time,
    )
    connector = FakeConnector(item)
    request = FetchRequest(tenant_id=tenant_id, ceo_id=ceo_id, limit=1)

    async def collect() -> list[SourceItem]:
        return [result async for result in connector.fetch(request)]

    assert isinstance(connector, SourceConnector)
    assert asyncio.run(collect()) == [item]


def test_ingestion_results_enforce_status_and_aggregate_semantics(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    issue = ValidationIssue(
        code="missing_author",
        message="A usable author is required.",
        severity=ValidationSeverity.ERROR,
        field="author",
    )
    rejected = IngestionItemResult(
        external_id="bad-item",
        status=IngestionItemStatus.REJECTED,
        validation_issues=(issue,),
    )
    checkpoint = ConnectorCheckpoint(
        connector_id="test-connector",
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        cursor="cursor-1",
        modified_after=fixed_time,
        last_successful_fetch_at=fixed_time + timedelta(seconds=1),
        updated_at=fixed_time + timedelta(seconds=1),
    )
    result = IngestionRunResult(
        connector_id="test-connector",
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        status=IngestionRunStatus.COMPLETED_WITH_REJECTIONS,
        started_at=fixed_time,
        completed_at=fixed_time + timedelta(seconds=1),
        items=(rejected,),
        checkpoint=checkpoint,
        stored_count=0,
        skipped_count=0,
        rejected_count=1,
    )

    assert result.rejected_count == 1
    with pytest.raises(ValidationError, match="require a document id"):
        IngestionItemResult(external_id="bad", status=IngestionItemStatus.STORED)
    with pytest.raises(ValidationError, match="require validation issues"):
        IngestionItemResult(external_id="bad", status=IngestionItemStatus.REJECTED)
    with pytest.raises(ValidationError, match="only rejected results"):
        IngestionItemResult(
            external_id="bad",
            status=IngestionItemStatus.UNCHANGED,
            validation_issues=(issue,),
        )
    with pytest.raises(ValidationError, match="aggregate counts"):
        result.model_copy(update={"rejected_count": 0}).model_validate(
            result.model_copy(update={"rejected_count": 0}).model_dump()
        )
    with pytest.raises(ValidationError, match="must not precede"):
        IngestionRunResult(
            **{
                **result.model_dump(),
                "started_at": fixed_time + timedelta(seconds=2),
            }
        )
    with pytest.raises(ValidationError, match="status must reflect"):
        IngestionRunResult(
            **{
                **result.model_dump(),
                "status": IngestionRunStatus.COMPLETED,
            }
        )
