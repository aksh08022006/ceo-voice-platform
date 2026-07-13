"""Typed test collaborators shared by ingestion pipeline scenarios."""

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from uuid import UUID

from ceo_voice.core.exceptions import ExternalAPIError, StorageError
from ceo_voice.ingestion import (
    CleanDocument,
    ConnectorCapabilities,
    ConnectorRegistry,
    ContentParser,
    FetchRequest,
    IngestionPipeline,
    IngestionRepositories,
    InMemoryCheckpointRepository,
    InMemoryCleanDocumentRepository,
    InMemoryMetadataRepository,
    InMemoryRawDocumentRepository,
    ParsedContent,
    RepositoryWriteDisposition,
    SourceItem,
)
from ceo_voice.models import ContentFormat, DocumentSourceType, Platform


class FakeConnector:
    """Bounded fake connector that records requests and can fail after yielding."""

    capabilities = ConnectorCapabilities(
        supports_cursor=True,
        supports_modified_after=True,
    )

    def __init__(
        self,
        connector_id: str,
        source_type: DocumentSourceType,
        items: list[SourceItem],
    ) -> None:
        self.connector_id = connector_id
        self.source_type = source_type
        self.items = items
        self.requests: list[FetchRequest] = []
        self.failure: ExternalAPIError | None = None

    async def fetch(self, request: FetchRequest) -> AsyncIterator[SourceItem]:
        self.requests.append(request)
        for item in self.items:
            yield item
        if self.failure is not None:
            raise self.failure


class AdvancingClock:
    """Deterministic monotonic clock for checkpoint and version tests."""

    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(seconds=1)
        return value


class CountingParser(ContentParser):
    """Parser spy proving unchanged content bypasses transformation work."""

    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def parse(self, item: SourceItem) -> ParsedContent:
        self.call_count += 1
        return super().parse(item)


class FailOnceCleanRepository(InMemoryCleanDocumentRepository):
    """Repository adapter simulating a failure after metadata persistence."""

    def __init__(self) -> None:
        super().__init__()
        self.should_fail = True

    async def save(self, document: CleanDocument) -> RepositoryWriteDisposition:
        if self.should_fail:
            self.should_fail = False
            raise StorageError("Transient clean write failure.", retryable=True)
        return await super().save(document)


def source_item(
    *,
    tenant_id: UUID,
    ceo_id: UUID,
    fixed_time: datetime,
    external_id: str,
    content: bytes,
    source: DocumentSourceType = DocumentSourceType.LINKEDIN,
    content_format: ContentFormat = ContentFormat.PLAIN_TEXT,
    author: str | None = "Example CEO",
    title: str = "Operating lesson",
    cursor: str | None = None,
    source_modified_at: datetime | None = None,
) -> SourceItem:
    """Build a valid source item with deterministic ownership and timestamps."""

    platform = {
        DocumentSourceType.LINKEDIN: Platform.LINKEDIN,
        DocumentSourceType.X: Platform.X,
    }.get(source)
    return SourceItem(
        external_id=external_id,
        tenant_id=tenant_id,
        ceo_id=ceo_id,
        source=source,
        raw_content=content,
        content_format=content_format,
        fetched_at=fixed_time,
        publication_date=fixed_time,
        source_modified_at=source_modified_at or fixed_time,
        author=author,
        title=title,
        platform=platform,
        language_hint="en",
        cursor=cursor,
    )


def repositories() -> IngestionRepositories:
    """Build an isolated in-memory repository bundle."""

    return IngestionRepositories(
        raw_documents=InMemoryRawDocumentRepository(),
        clean_documents=InMemoryCleanDocumentRepository(),
        metadata=InMemoryMetadataRepository(),
        checkpoints=InMemoryCheckpointRepository(),
    )


def pipeline(
    connector: FakeConnector,
    repository_bundle: IngestionRepositories,
    clock: AdvancingClock,
    *,
    parser: ContentParser | None = None,
) -> IngestionPipeline:
    """Compose a pipeline with one connector and injected deterministic collaborators."""

    return IngestionPipeline(
        connectors=ConnectorRegistry((connector,)),
        repositories=repository_bundle,
        parser=parser,
        clock=clock,
    )
