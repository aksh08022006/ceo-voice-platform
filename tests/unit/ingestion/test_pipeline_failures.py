"""Failure isolation and retry tests for ingestion orchestration."""

import asyncio
from datetime import datetime
from uuid import UUID

import pytest

from ceo_voice.core.exceptions import DataIngestionError, ExternalAPIError, StorageError
from ceo_voice.ingestion import (
    FetchRequest,
    IngestionItemStatus,
    IngestionRepositories,
    InMemoryCheckpointRepository,
    InMemoryMetadataRepository,
    InMemoryRawDocumentRepository,
    RawDocumentFactory,
)
from ceo_voice.models import DocumentSourceType
from tests.unit.ingestion.pipeline_helpers import (
    AdvancingClock,
    FailOnceCleanRepository,
    FakeConnector,
    pipeline,
    repositories,
    source_item,
)


def test_connector_failure_does_not_advance_checkpoint_and_retry_is_idempotent(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        external_id="post-1",
        content=b"Persist before connector failure.",
    )
    connector = FakeConnector("linkedin-api", DocumentSourceType.LINKEDIN, [item])
    connector.failure = ExternalAPIError("Provider unavailable.", retryable=True)
    repository_bundle = repositories()
    ingestion_pipeline = pipeline(connector, repository_bundle, AdvancingClock(fixed_time))

    async def scenario() -> None:
        request = FetchRequest(tenant_id=tenant_id, ceo_id=ceo_id)
        with pytest.raises(ExternalAPIError, match="Provider unavailable"):
            await ingestion_pipeline.run(connector.connector_id, request)
        assert (
            await repository_bundle.checkpoints.get(tenant_id, ceo_id, connector.connector_id)
            is None
        )

        connector.failure = None
        retry = await ingestion_pipeline.run(connector.connector_id, request)
        assert retry.items[0].status is IngestionItemStatus.UNCHANGED
        assert await repository_bundle.checkpoints.get(tenant_id, ceo_id, connector.connector_id)

    asyncio.run(scenario())


def test_partial_metadata_write_is_repaired_with_identical_version_on_retry(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        external_id="post-1",
        content=b"A reproducible canonical version.",
    )
    connector = FakeConnector("linkedin-api", DocumentSourceType.LINKEDIN, [item])
    repository_bundle = IngestionRepositories(
        raw_documents=InMemoryRawDocumentRepository(),
        clean_documents=FailOnceCleanRepository(),
        metadata=InMemoryMetadataRepository(),
        checkpoints=InMemoryCheckpointRepository(),
    )
    ingestion_pipeline = pipeline(connector, repository_bundle, AdvancingClock(fixed_time))

    async def scenario() -> None:
        request = FetchRequest(tenant_id=tenant_id, ceo_id=ceo_id)
        with pytest.raises(StorageError, match="Transient clean write failure"):
            await ingestion_pipeline.run(connector.connector_id, request)
        assert (
            await repository_bundle.checkpoints.get(tenant_id, ceo_id, connector.connector_id)
            is None
        )

        result = await ingestion_pipeline.run(connector.connector_id, request)
        outcome = result.items[0]
        assert outcome.status is IngestionItemStatus.STORED
        assert outcome.document_id is not None
        metadata = await repository_bundle.metadata.get(tenant_id, outcome.document_id, 1)
        clean = await repository_bundle.clean_documents.get(tenant_id, outcome.document_id, 1)
        assert metadata is not None and clean is not None
        assert metadata.processed_at == clean.processed_at

    asyncio.run(scenario())


def test_scope_violation_and_connector_overflow_fail_without_checkpoint(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    wrong_scope = source_item(
        tenant_id=UUID(int=999),
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        external_id="wrong-tenant",
        content=b"Must never cross the tenant boundary.",
    )
    connector = FakeConnector("linkedin-api", DocumentSourceType.LINKEDIN, [wrong_scope])
    repository_bundle = repositories()
    ingestion_pipeline = pipeline(connector, repository_bundle, AdvancingClock(fixed_time))

    async def scenario() -> None:
        request = FetchRequest(tenant_id=tenant_id, ceo_id=ceo_id, limit=1)
        with pytest.raises(DataIngestionError, match="outside its requested"):
            await ingestion_pipeline.run(connector.connector_id, request)
        raw = RawDocumentFactory().create(wrong_scope, stored_at=fixed_time)
        assert await repository_bundle.raw_documents.get(wrong_scope.tenant_id, raw.id) is None
        assert (
            await repository_bundle.checkpoints.get(tenant_id, ceo_id, connector.connector_id)
            is None
        )

        valid = wrong_scope.model_copy(update={"tenant_id": tenant_id})
        connector.items = [valid, valid.model_copy(update={"external_id": "overflow"})]
        with pytest.raises(DataIngestionError, match="more items than requested"):
            await ingestion_pipeline.run(connector.connector_id, request)
        assert (
            await repository_bundle.checkpoints.get(tenant_id, ceo_id, connector.connector_id)
            is None
        )

    asyncio.run(scenario())


def test_malformed_encoding_is_rejected_after_raw_retention(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    malformed = source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        external_id="bad-encoding",
        content=b"\xff\xfe",
    ).model_copy(update={"encoding_hint": "utf-8"})
    connector = FakeConnector("linkedin-api", DocumentSourceType.LINKEDIN, [malformed])
    repository_bundle = repositories()
    ingestion_pipeline = pipeline(connector, repository_bundle, AdvancingClock(fixed_time))

    async def scenario() -> None:
        result = await ingestion_pipeline.run(
            connector.connector_id,
            FetchRequest(tenant_id=tenant_id, ceo_id=ceo_id),
        )
        outcome = result.items[0]
        assert outcome.status is IngestionItemStatus.REJECTED
        assert outcome.error_code == "data_ingestion_error"
        assert outcome.raw_document_id is not None
        assert await repository_bundle.raw_documents.get(tenant_id, outcome.raw_document_id)

    asyncio.run(scenario())
