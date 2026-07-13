"""Behavior tests for source-independent ingestion orchestration."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from ceo_voice.ingestion import (
    ConnectorRegistry,
    FetchRequest,
    IngestionItemStatus,
    IngestionPipeline,
    IngestionRunStatus,
)
from ceo_voice.models import ContentFormat, DocumentSourceType
from tests.unit.ingestion.pipeline_helpers import (
    AdvancingClock,
    CountingParser,
    FakeConnector,
    pipeline,
    repositories,
    source_item,
)


def test_pipeline_stores_valid_content_skips_duplicates_and_isolates_rejections(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    valid = source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        external_id="post-1",
        content=b"One operating lesson.",
        cursor="cursor-1",
    )
    duplicate = valid.model_copy(update={"external_id": "post-copy", "cursor": "cursor-2"})
    invalid = source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        external_id="missing-author",
        content=b"Retain these raw bytes.",
        author=None,
        cursor="cursor-3",
    )
    connector = FakeConnector(
        "linkedin-export",
        DocumentSourceType.LINKEDIN,
        [valid, duplicate, invalid],
    )
    repository_bundle = repositories()
    ingestion_pipeline = pipeline(connector, repository_bundle, AdvancingClock(fixed_time))

    async def scenario() -> None:
        result = await ingestion_pipeline.run(
            connector.connector_id,
            FetchRequest(tenant_id=tenant_id, ceo_id=ceo_id, limit=3),
        )

        assert result.status is IngestionRunStatus.COMPLETED_WITH_REJECTIONS
        assert [item.status for item in result.items] == [
            IngestionItemStatus.STORED,
            IngestionItemStatus.DUPLICATE,
            IngestionItemStatus.REJECTED,
        ]
        assert (result.stored_count, result.skipped_count, result.rejected_count) == (1, 1, 1)
        assert result.checkpoint.cursor == "cursor-3"
        assert result.checkpoint.modified_after == fixed_time

        for outcome in result.items:
            assert outcome.raw_document_id is not None
            assert await repository_bundle.raw_documents.get(tenant_id, outcome.raw_document_id)

        stored = result.items[0]
        assert stored.document_id is not None
        clean = await repository_bundle.clean_documents.get(tenant_id, stored.document_id, 1)
        metadata = await repository_bundle.metadata.get(tenant_id, stored.document_id, 1)
        assert clean is not None and clean.content == "One operating lesson."
        assert metadata is not None and metadata.word_count == 3

    asyncio.run(scenario())


def test_checkpoint_seeds_retry_and_unchanged_content_bypasses_parser(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    item = source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        external_id="post-1",
        content=b"An unchanged post.",
        cursor="cursor-1",
    )
    connector = FakeConnector("linkedin-api", DocumentSourceType.LINKEDIN, [item])
    repository_bundle = repositories()
    parser = CountingParser()
    ingestion_pipeline = pipeline(
        connector,
        repository_bundle,
        AdvancingClock(fixed_time),
        parser=parser,
    )

    async def scenario() -> None:
        request = FetchRequest(tenant_id=tenant_id, ceo_id=ceo_id)
        first = await ingestion_pipeline.run(connector.connector_id, request)
        second = await ingestion_pipeline.run(connector.connector_id, request)

        assert first.items[0].status is IngestionItemStatus.STORED
        assert second.items[0].status is IngestionItemStatus.UNCHANGED
        assert parser.call_count == 1
        assert connector.requests[1].cursor == "cursor-1"
        assert connector.requests[1].modified_after == fixed_time

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("change", "expected_status"),
    [
        ({"raw_content": b"Changed words."}, IngestionItemStatus.STORED),
        ({"title": "Revised title"}, IngestionItemStatus.STORED),
        (
            {
                "raw_content": b"<p>Original words.</p>",
                "content_format": ContentFormat.HTML,
            },
            IngestionItemStatus.UNCHANGED,
        ),
        (
            {"source_modified_at": datetime(2026, 7, 13, 9, 31, tzinfo=UTC)},
            IngestionItemStatus.UNCHANGED,
        ),
    ],
)
def test_incremental_versions_content_and_metadata_but_not_transport_only_changes(
    change: dict[str, object],
    expected_status: IngestionItemStatus,
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    original = source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        external_id="post-1",
        content=b"Original words.",
        cursor="cursor-1",
    )
    connector = FakeConnector("linkedin-api", DocumentSourceType.LINKEDIN, [original])
    repository_bundle = repositories()
    ingestion_pipeline = pipeline(connector, repository_bundle, AdvancingClock(fixed_time))

    async def scenario() -> None:
        request = FetchRequest(tenant_id=tenant_id, ceo_id=ceo_id)
        first = await ingestion_pipeline.run(connector.connector_id, request)
        connector.items = [original.model_copy(update=change)]
        second = await ingestion_pipeline.run(connector.connector_id, request)

        assert first.items[0].status is IngestionItemStatus.STORED
        assert second.items[0].status is expected_status
        if expected_status is IngestionItemStatus.STORED:
            assert second.items[0].document_version == 2
        else:
            assert second.items[0].document_version == 1

    asyncio.run(scenario())


def test_duplicate_detection_does_not_collapse_cross_platform_voice_evidence(
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
) -> None:
    repository_bundle = repositories()
    clock = AdvancingClock(fixed_time)
    linkedin_item = source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        external_id="linkedin-1",
        content=b"The same public words.",
    )
    x_item = source_item(
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        fixed_time=fixed_time,
        external_id="x-1",
        content=b"The same public words.",
        source=DocumentSourceType.X,
    )
    linkedin = FakeConnector("linkedin", DocumentSourceType.LINKEDIN, [linkedin_item])
    x_connector = FakeConnector("x", DocumentSourceType.X, [x_item])
    pipeline = IngestionPipeline(
        connectors=ConnectorRegistry((linkedin, x_connector)),
        repositories=repository_bundle,
        clock=clock,
    )

    async def scenario() -> None:
        linkedin_result = await pipeline.run(
            "linkedin", FetchRequest(tenant_id=tenant_id, ceo_id=ceo_id)
        )
        x_result = await pipeline.run("x", FetchRequest(tenant_id=tenant_id, ceo_id=ceo_id))

        assert linkedin_result.items[0].status is IngestionItemStatus.STORED
        assert x_result.items[0].status is IngestionItemStatus.STORED
        assert linkedin_result.items[0].document_id != x_result.items[0].document_id

    asyncio.run(scenario())
