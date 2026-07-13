"""Tests for raw and canonical incremental-processing decisions."""

import asyncio
from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.ingestion import (
    ContentParser,
    DocumentChangeDecision,
    DocumentChangeKind,
    DocumentCleaner,
    DocumentNormalizer,
    IncrementalPlanner,
    IngestionDocument,
    InMemoryCleanDocumentRepository,
    RawDocument,
    RawDocumentFactory,
    SourceItem,
    to_clean_document,
)
from ceo_voice.models import ContentFormat, DocumentSourceType


def _source_item(
    *,
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
    external_id: str,
    content: bytes,
    content_format: ContentFormat = ContentFormat.PLAIN_TEXT,
) -> SourceItem:
    return SourceItem(
        external_id=external_id,
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        source=DocumentSourceType.BLOG,
        raw_content=content,
        content_format=content_format,
        fetched_at=fixed_time,
        publication_date=fixed_time,
        author="Example CEO",
    )


def _artifacts(
    item: SourceItem, fixed_time: datetime, *, version: int = 1
) -> tuple[RawDocument, IngestionDocument]:
    raw = RawDocumentFactory().create(item, stored_at=fixed_time)
    cleaned = DocumentCleaner().clean(ContentParser().parse(item))
    document = DocumentNormalizer().normalize(
        item,
        raw,
        cleaned,
        processed_at=fixed_time,
        version=version,
    )
    return raw, document


def test_raw_incremental_decisions_cover_new_unchanged_changed_and_duplicate(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    repository = InMemoryCleanDocumentRepository()
    planner = IncrementalPlanner(repository)
    stored_item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        external_id="stored",
        content=b"Stored content",
    )
    stored_raw, stored_document = _artifacts(stored_item, fixed_time)

    async def scenario() -> None:
        await repository.save(to_clean_document(stored_document))

        unchanged = await planner.assess_raw(stored_item, stored_raw)
        assert unchanged.kind is DocumentChangeKind.UNCHANGED
        assert unchanged.existing_version == 1

        changed_item = _source_item(
            tenant_id=tenant_id,
            ceo_id=ceo_id,
            fixed_time=fixed_time,
            external_id="stored",
            content=b"Changed content",
        )
        changed_raw, _ = _artifacts(changed_item, fixed_time, version=2)
        changed = await planner.assess_raw(changed_item, changed_raw)
        assert changed.kind is DocumentChangeKind.CHANGED
        assert changed.next_version == 2

        duplicate_item = _source_item(
            tenant_id=tenant_id,
            ceo_id=ceo_id,
            fixed_time=fixed_time,
            external_id="duplicate-id",
            content=b"Stored content",
        )
        duplicate_raw, _ = _artifacts(duplicate_item, fixed_time)
        duplicate = await planner.assess_raw(duplicate_item, duplicate_raw)
        assert duplicate.kind is DocumentChangeKind.DUPLICATE
        assert duplicate.existing_document_id == stored_document.id

        new_item = _source_item(
            tenant_id=tenant_id,
            ceo_id=ceo_id,
            fixed_time=fixed_time,
            external_id="new-id",
            content=b"Entirely new content",
        )
        new_raw, _ = _artifacts(new_item, fixed_time)
        new = await planner.assess_raw(new_item, new_raw)
        assert new.kind is DocumentChangeKind.NEW
        assert new.next_version == 1

    asyncio.run(scenario())


def test_canonical_assessment_skips_transport_only_changes_and_clean_duplicates(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    repository = InMemoryCleanDocumentRepository()
    planner = IncrementalPlanner(repository)
    stored_item = _source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        external_id="stored",
        content=b"Same visible content",
    )
    _, stored_document = _artifacts(stored_item, fixed_time)

    async def scenario() -> None:
        await repository.save(to_clean_document(stored_document))

        changed_transport = _source_item(
            tenant_id=tenant_id,
            ceo_id=ceo_id,
            fixed_time=fixed_time,
            external_id="stored",
            content=b"<p>Same visible content</p>",
            content_format=ContentFormat.HTML,
        )
        changed_raw, changed_document = _artifacts(changed_transport, fixed_time, version=2)
        preliminary = await planner.assess_raw(changed_transport, changed_raw)
        unchanged = await planner.assess_canonical(changed_document, preliminary)
        assert preliminary.kind is DocumentChangeKind.CHANGED
        assert unchanged.kind is DocumentChangeKind.UNCHANGED

        duplicate_transport = _source_item(
            tenant_id=tenant_id,
            ceo_id=ceo_id,
            fixed_time=fixed_time,
            external_id="other-id",
            content=b"**Same visible content**",
            content_format=ContentFormat.MARKDOWN,
        )
        duplicate_raw, duplicate_document = _artifacts(duplicate_transport, fixed_time)
        duplicate_preliminary = await planner.assess_raw(duplicate_transport, duplicate_raw)
        duplicate = await planner.assess_canonical(duplicate_document, duplicate_preliminary)
        assert duplicate.kind is DocumentChangeKind.DUPLICATE

        assert await planner.assess_canonical(stored_document, unchanged) == unchanged

    asyncio.run(scenario())


def test_change_decision_enforces_version_semantics() -> None:
    with pytest.raises(ValidationError, match="require next_version"):
        DocumentChangeDecision(kind=DocumentChangeKind.NEW, reason="new")
    with pytest.raises(ValidationError, match="must not set next_version"):
        DocumentChangeDecision(
            kind=DocumentChangeKind.UNCHANGED,
            next_version=1,
            reason="unchanged",
        )
