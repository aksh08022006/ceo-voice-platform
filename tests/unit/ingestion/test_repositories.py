"""Tests for ingestion repository contracts and in-memory adapters."""

import asyncio
from datetime import datetime, timedelta
from uuid import UUID

import pytest

from ceo_voice.core.exceptions import StorageError
from ceo_voice.ingestion import (
    CheckpointRepository,
    CleanDocumentRepository,
    ConnectorCheckpoint,
    ContentParser,
    DocumentCleaner,
    DocumentNormalizer,
    IngestionDocument,
    IngestionRepositories,
    InMemoryCheckpointRepository,
    InMemoryCleanDocumentRepository,
    InMemoryMetadataRepository,
    InMemoryRawDocumentRepository,
    MetadataExtractor,
    RawDocument,
    RawDocumentFactory,
    RawDocumentRepository,
    RepositoryWriteDisposition,
    SourceItem,
    to_clean_document,
)
from ceo_voice.models import ContentFormat, DocumentSourceType


def _source_item(
    *, tenant_id: UUID, ceo_id: UUID, fixed_time: datetime, content: bytes = b"Content"
) -> SourceItem:
    return SourceItem(
        external_id="item-1",
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        source=DocumentSourceType.BLOG,
        raw_content=content,
        content_format=ContentFormat.PLAIN_TEXT,
        fetched_at=fixed_time,
        publication_date=fixed_time,
        author="Example CEO",
        language_hint="en",
    )


def _artifacts(item: SourceItem, fixed_time: datetime) -> tuple[RawDocument, IngestionDocument]:
    raw = RawDocumentFactory().create(item, stored_at=fixed_time)
    cleaned = DocumentCleaner().clean(ContentParser().parse(item))
    document = DocumentNormalizer().normalize(item, raw, cleaned, processed_at=fixed_time)
    return raw, document


def test_raw_repository_is_idempotent_tenant_scoped_and_conflict_safe(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    raw, _ = _artifacts(
        _source_item(tenant_id=tenant_id, ceo_id=ceo_id, fixed_time=fixed_time), fixed_time
    )
    repository = InMemoryRawDocumentRepository()

    async def scenario() -> None:
        assert await repository.save(raw) is RepositoryWriteDisposition.CREATED
        assert await repository.save(raw) is RepositoryWriteDisposition.ALREADY_EXISTS
        assert await repository.get(tenant_id, raw.id) == raw
        assert await repository.get(UUID(int=0), raw.id) is None

        conflict = raw.model_copy(update={"raw_content": b"conflicting bytes"})
        with pytest.raises(StorageError, match="identity conflict"):
            await repository.save(conflict)

    asyncio.run(scenario())
    assert isinstance(repository, RawDocumentRepository)


def test_clean_repository_enforces_contiguous_versions_and_indexes_checksums(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    _, document = _artifacts(
        _source_item(tenant_id=tenant_id, ceo_id=ceo_id, fixed_time=fixed_time), fixed_time
    )
    first = to_clean_document(document)
    second = first.model_copy(
        update={
            "version": 2,
            "raw_document_id": UUID("90000000-0000-0000-0000-000000000009"),
            "raw_checksum": "b" * 64,
            "content_checksum": "c" * 64,
            "content": "Changed content",
        }
    )
    repository = InMemoryCleanDocumentRepository()

    async def scenario() -> None:
        assert await repository.save(first) is RepositoryWriteDisposition.CREATED
        assert await repository.save(first) is RepositoryWriteDisposition.ALREADY_EXISTS
        assert await repository.save(second) is RepositoryWriteDisposition.CREATED
        assert await repository.get(tenant_id, first.id, 1) == first
        assert await repository.get(UUID(int=0), first.id, 1) is None
        assert (
            await repository.get_latest_by_source(
                tenant_id, ceo_id, first.source, first.external_id
            )
            == second
        )
        assert await repository.find_by_raw_checksum(tenant_id, ceo_id, first.raw_checksum) == first
        assert (
            await repository.find_by_content_checksum(tenant_id, ceo_id, second.content_checksum)
            == second
        )

        gap = second.model_copy(update={"version": 4})
        with pytest.raises(StorageError, match="not contiguous"):
            await repository.save(gap)
        conflict = second.model_copy(update={"title": "Conflicting title"})
        with pytest.raises(StorageError, match="version conflict"):
            await repository.save(conflict)

    asyncio.run(scenario())
    assert isinstance(repository, CleanDocumentRepository)
    assert not hasattr(first, "raw_content")


def test_metadata_repository_versions_projections_independently(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    _, document = _artifacts(
        _source_item(tenant_id=tenant_id, ceo_id=ceo_id, fixed_time=fixed_time), fixed_time
    )
    metadata = MetadataExtractor().extract(document)
    repository = InMemoryMetadataRepository()

    async def scenario() -> None:
        assert await repository.save(metadata) is RepositoryWriteDisposition.CREATED
        assert await repository.save(metadata) is RepositoryWriteDisposition.ALREADY_EXISTS
        assert await repository.get(tenant_id, document.id, 1) == metadata
        assert await repository.get(UUID(int=0), document.id, 1) is None

        conflict = metadata.model_copy(update={"word_count": metadata.word_count + 1})
        with pytest.raises(StorageError, match="Metadata version conflict"):
            await repository.save(conflict)

    asyncio.run(scenario())


def test_checkpoint_repository_only_advances_successful_progress(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    first = ConnectorCheckpoint(
        connector_id="linkedin-primary",
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        cursor="cursor-1",
        modified_after=fixed_time,
        last_successful_fetch_at=fixed_time,
        updated_at=fixed_time,
    )
    updated = first.model_copy(
        update={"cursor": "cursor-2", "updated_at": fixed_time + timedelta(seconds=1)}
    )
    repository = InMemoryCheckpointRepository()

    async def scenario() -> None:
        assert await repository.save(first) is RepositoryWriteDisposition.CREATED
        assert await repository.save(first) is RepositoryWriteDisposition.ALREADY_EXISTS
        assert await repository.save(updated) is RepositoryWriteDisposition.UPDATED
        assert await repository.get(tenant_id, ceo_id, first.connector_id) == updated
        assert await repository.get(UUID(int=0), ceo_id, first.connector_id) is None

        with pytest.raises(StorageError, match="cannot move backward"):
            await repository.save(first.model_copy(update={"cursor": "conflict"}))

    asyncio.run(scenario())
    assert isinstance(repository, CheckpointRepository)


def test_repository_bundle_is_explicit_dependency_injection() -> None:
    repositories = IngestionRepositories(
        raw_documents=InMemoryRawDocumentRepository(),
        clean_documents=InMemoryCleanDocumentRepository(),
        metadata=InMemoryMetadataRepository(),
        checkpoints=InMemoryCheckpointRepository(),
    )

    assert isinstance(repositories.raw_documents, RawDocumentRepository)
    assert isinstance(repositories.clean_documents, CleanDocumentRepository)
