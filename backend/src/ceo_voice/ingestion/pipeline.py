"""Source-independent ingestion pipeline orchestration."""

from collections.abc import AsyncIterator, Callable
from datetime import datetime
from uuid import UUID

from ceo_voice.core.exceptions import DataIngestionError, StorageError
from ceo_voice.core.logging import get_logger
from ceo_voice.ingestion.connectors import ConnectorRegistry, SourceConnector
from ceo_voice.ingestion.contracts import (
    ConnectorCheckpoint,
    FetchRequest,
    SourceItem,
)
from ceo_voice.ingestion.incremental import IncrementalPlanner
from ceo_voice.ingestion.outcomes import (
    DocumentChangeDecision,
    DocumentChangeKind,
    IngestionItemResult,
    IngestionItemStatus,
    IngestionRunResult,
    IngestionRunStatus,
    ValidationIssue,
)
from ceo_voice.ingestion.repositories import IngestionRepositories, to_clean_document
from ceo_voice.ingestion.stages import (
    ContentParser,
    DocumentCleaner,
    DocumentNormalizer,
    DocumentValidator,
    MetadataExtractor,
    RawDocumentFactory,
    SourceItemValidator,
)
from ceo_voice.utils.time import utc_now

_LOGGER = get_logger(__name__)


class IngestionPipeline:
    """Coordinate connector, transformation, validation, and persistence boundaries.

    Each stage is injected behind a narrow responsibility. The pipeline owns sequencing and
    failure policy only; it contains no provider-specific parsing or storage implementation logic.
    """

    def __init__(
        self,
        *,
        connectors: ConnectorRegistry,
        repositories: IngestionRepositories,
        parser: ContentParser | None = None,
        cleaner: DocumentCleaner | None = None,
        raw_factory: RawDocumentFactory | None = None,
        normalizer: DocumentNormalizer | None = None,
        metadata_extractor: MetadataExtractor | None = None,
        source_validator: SourceItemValidator | None = None,
        document_validator: DocumentValidator | None = None,
        incremental_planner: IncrementalPlanner | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._connectors = connectors
        self._repositories = repositories
        self._parser = parser or ContentParser()
        self._cleaner = cleaner or DocumentCleaner()
        self._raw_factory = raw_factory or RawDocumentFactory()
        self._normalizer = normalizer or DocumentNormalizer()
        self._metadata_extractor = metadata_extractor or MetadataExtractor()
        self._source_validator = source_validator or SourceItemValidator(clock=clock)
        self._document_validator = document_validator or DocumentValidator(clock=clock)
        self._incremental = incremental_planner or IncrementalPlanner(repositories.clean_documents)
        self._clock = clock

    async def run(self, connector_id: str, request: FetchRequest) -> IngestionRunResult:
        """Process one bounded connector stream and commit progress on full stream success.

        Malformed individual documents are retained in raw storage and returned as rejections.
        Connector contract violations, connector failures, and storage failures abort the run and
        deliberately leave the checkpoint unchanged so an orchestrator can retry safely.
        """

        connector = self._connectors.get(connector_id)
        fetch_request = await self._seed_from_checkpoint(connector, request)
        started_at = self._clock()
        outcomes: list[IngestionItemResult] = []
        last_cursor = fetch_request.cursor
        latest_modified_at = fetch_request.modified_after

        _LOGGER.info(
            "ingestion_run_started",
            extra={
                "connector_id": connector.connector_id,
                "tenant_id": request.tenant_id,
                "ceo_id": request.ceo_id,
                "limit": request.limit,
            },
        )

        async for position, item in _enumerate_async(connector.fetch(fetch_request)):
            if position >= request.limit:
                raise DataIngestionError(
                    "Connector yielded more items than requested.",
                    details={
                        "connector_id": connector.connector_id,
                        "limit": request.limit,
                    },
                )
            self._assert_item_scope(connector, request, item)
            if item.cursor is not None:
                last_cursor = item.cursor
            latest_modified_at = _latest_timestamp(
                latest_modified_at,
                item.source_modified_at,
            )
            outcomes.append(await self._process_item(item))

        completed_at = self._clock()
        checkpoint = ConnectorCheckpoint(
            connector_id=connector.connector_id,
            tenant_id=request.tenant_id,
            ceo_id=request.ceo_id,
            cursor=last_cursor if connector.capabilities.supports_cursor else None,
            modified_after=(
                latest_modified_at if connector.capabilities.supports_modified_after else None
            ),
            last_successful_fetch_at=completed_at,
            updated_at=completed_at,
        )
        await self._repositories.checkpoints.save(checkpoint)

        stored_count = sum(item.status is IngestionItemStatus.STORED for item in outcomes)
        skipped_count = sum(
            item.status in {IngestionItemStatus.UNCHANGED, IngestionItemStatus.DUPLICATE}
            for item in outcomes
        )
        rejected_count = sum(item.status is IngestionItemStatus.REJECTED for item in outcomes)
        status = (
            IngestionRunStatus.COMPLETED_WITH_REJECTIONS
            if rejected_count
            else IngestionRunStatus.COMPLETED
        )
        result = IngestionRunResult(
            connector_id=connector.connector_id,
            tenant_id=request.tenant_id,
            ceo_id=request.ceo_id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            items=tuple(outcomes),
            checkpoint=checkpoint,
            stored_count=stored_count,
            skipped_count=skipped_count,
            rejected_count=rejected_count,
        )
        _LOGGER.info(
            "ingestion_run_completed",
            extra={
                "connector_id": connector.connector_id,
                "tenant_id": request.tenant_id,
                "ceo_id": request.ceo_id,
                "stored_count": stored_count,
                "skipped_count": skipped_count,
                "rejected_count": rejected_count,
            },
        )
        return result

    async def _process_item(self, item: SourceItem) -> IngestionItemResult:
        raw_document = self._raw_factory.create(item, stored_at=self._clock())
        await self._repositories.raw_documents.save(raw_document)
        persisted_raw_document = await self._repositories.raw_documents.get(
            item.tenant_id,
            raw_document.id,
        )
        if persisted_raw_document is None:
            raise StorageError(
                "Raw artifact was not readable after a successful write.",
                details={"raw_document_id": str(raw_document.id)},
                retryable=True,
            )
        raw_document = persisted_raw_document

        source_validation = self._source_validator.validate(item)
        if not source_validation.is_valid:
            return self._rejected(
                item,
                raw_document_id=raw_document.id,
                issues=source_validation.issues,
            )

        preliminary = await self._incremental.assess_raw(item, raw_document)
        if preliminary.kind in {DocumentChangeKind.UNCHANGED, DocumentChangeKind.DUPLICATE}:
            return _skipped_result(item, raw_document.id, preliminary)

        try:
            parsed = self._parser.parse(item)
            cleaned = self._cleaner.clean(parsed)
            document = self._normalizer.normalize(
                item,
                raw_document,
                cleaned,
                processed_at=raw_document.stored_at,
                version=preliminary.next_version or 1,
            )
        except DataIngestionError as error:
            return self._rejected(
                item,
                raw_document_id=raw_document.id,
                error=error,
            )

        document_validation = self._document_validator.validate(document)
        if not document_validation.is_valid:
            return self._rejected(
                item,
                raw_document_id=raw_document.id,
                issues=document_validation.issues,
            )

        canonical_decision = await self._incremental.assess_canonical(document, preliminary)
        if canonical_decision.kind in {
            DocumentChangeKind.UNCHANGED,
            DocumentChangeKind.DUPLICATE,
        }:
            return _skipped_result(item, raw_document.id, canonical_decision)

        metadata = self._metadata_extractor.extract(document)
        # Metadata-first is intentionally repairable for non-transactional adapters: a retry can
        # complete the clean write idempotently. Production adapters should commit both in one
        # database transaction or transactional outbox operation.
        await self._repositories.metadata.save(metadata)
        await self._repositories.clean_documents.save(to_clean_document(document))
        return IngestionItemResult(
            external_id=item.external_id,
            status=IngestionItemStatus.STORED,
            raw_document_id=raw_document.id,
            document_id=document.id,
            document_version=document.version,
            decision=canonical_decision,
        )

    async def _seed_from_checkpoint(
        self,
        connector: SourceConnector,
        request: FetchRequest,
    ) -> FetchRequest:
        checkpoint = await self._repositories.checkpoints.get(
            request.tenant_id,
            request.ceo_id,
            connector.connector_id,
        )
        if checkpoint is None:
            return request

        cursor = request.cursor
        if cursor is None and connector.capabilities.supports_cursor:
            cursor = checkpoint.cursor
        modified_after = request.modified_after
        if modified_after is None and connector.capabilities.supports_modified_after:
            modified_after = checkpoint.modified_after
        return request.model_copy(
            update={"cursor": cursor, "modified_after": modified_after},
        )

    @staticmethod
    def _assert_item_scope(
        connector: SourceConnector,
        request: FetchRequest,
        item: SourceItem,
    ) -> None:
        if (
            item.tenant_id != request.tenant_id
            or item.ceo_id != request.ceo_id
            or item.source is not connector.source_type
        ):
            raise DataIngestionError(
                "Connector emitted an item outside its requested ownership or source scope.",
                details={
                    "connector_id": connector.connector_id,
                    "expected_source": connector.source_type.value,
                    "actual_source": item.source.value,
                    "external_id": item.external_id,
                },
            )

    @staticmethod
    def _rejected(
        item: SourceItem,
        *,
        raw_document_id: UUID,
        issues: tuple[ValidationIssue, ...] = (),
        error: DataIngestionError | None = None,
    ) -> IngestionItemResult:
        _LOGGER.warning(
            "ingestion_item_rejected",
            extra={
                "source": item.source,
                "external_id": item.external_id,
                "error_code": error.code if error else None,
                "validation_codes": [issue.code for issue in issues],
            },
        )
        return IngestionItemResult(
            external_id=item.external_id,
            status=IngestionItemStatus.REJECTED,
            raw_document_id=raw_document_id,
            validation_issues=issues,
            error_code=error.code if error else None,
            error_message=error.message if error else None,
        )


async def _enumerate_async(
    items: AsyncIterator[SourceItem],
) -> AsyncIterator[tuple[int, SourceItem]]:
    """Enumerate an asynchronous iterator without buffering connector content."""

    position = 0
    async for item in items:
        yield position, item
        position += 1


def _skipped_result(
    item: SourceItem,
    raw_document_id: UUID,
    decision: DocumentChangeDecision,
) -> IngestionItemResult:
    status = (
        IngestionItemStatus.UNCHANGED
        if decision.kind is DocumentChangeKind.UNCHANGED
        else IngestionItemStatus.DUPLICATE
    )
    return IngestionItemResult(
        external_id=item.external_id,
        status=status,
        raw_document_id=raw_document_id,
        document_id=decision.existing_document_id,
        document_version=decision.existing_version,
        decision=decision,
    )


def _latest_timestamp(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if candidate is None:
        return current
    if current is None or candidate > current:
        return candidate
    return current
