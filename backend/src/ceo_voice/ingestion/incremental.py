"""Repository-backed incremental processing decisions."""

from ceo_voice.ingestion.contracts import (
    DocumentChangeDecision,
    DocumentChangeKind,
    IngestionDocument,
    RawDocument,
    SourceItem,
)
from ceo_voice.ingestion.repositories.ports import CleanDocumentRepository


class IncrementalPlanner:
    """Classify new, changed, unchanged, and exactly duplicated documents."""

    def __init__(self, repository: CleanDocumentRepository) -> None:
        self._repository = repository

    async def assess_raw(
        self, item: SourceItem, raw_document: RawDocument
    ) -> DocumentChangeDecision:
        """Skip unchanged raw content before source-independent transformation."""

        latest = await self._repository.get_latest_by_source(
            item.tenant_id,
            item.ceo_id,
            item.source,
            item.external_id,
        )
        if latest is not None and latest.raw_checksum == raw_document.raw_checksum:
            return DocumentChangeDecision(
                kind=DocumentChangeKind.UNCHANGED,
                existing_document_id=latest.id,
                existing_version=latest.version,
                reason="raw checksum matches the latest source version",
            )

        duplicate = await self._repository.find_by_raw_checksum(
            item.tenant_id, item.ceo_id, raw_document.raw_checksum
        )
        if duplicate is not None and (latest is None or duplicate.id != latest.id):
            return DocumentChangeDecision(
                kind=DocumentChangeKind.DUPLICATE,
                existing_document_id=duplicate.id,
                existing_version=duplicate.version,
                reason="raw checksum matches another stored document",
            )

        if latest is not None:
            return DocumentChangeDecision(
                kind=DocumentChangeKind.CHANGED,
                next_version=latest.version + 1,
                existing_document_id=latest.id,
                existing_version=latest.version,
                reason="raw checksum changed for an existing source item",
            )
        return DocumentChangeDecision(
            kind=DocumentChangeKind.NEW,
            next_version=1,
            reason="source identity has not been processed",
        )

    async def assess_canonical(
        self,
        document: IngestionDocument,
        preliminary: DocumentChangeDecision,
    ) -> DocumentChangeDecision:
        """Detect canonical duplicates after transport cleanup and normalization."""

        if preliminary.kind not in {DocumentChangeKind.NEW, DocumentChangeKind.CHANGED}:
            return preliminary

        latest = await self._repository.get_latest_by_source(
            document.tenant_id,
            document.ceo_id,
            document.source,
            document.external_id,
        )
        if latest is not None and latest.content_checksum == document.content_checksum:
            return DocumentChangeDecision(
                kind=DocumentChangeKind.UNCHANGED,
                existing_document_id=latest.id,
                existing_version=latest.version,
                reason="canonical content is unchanged after transport cleanup",
            )

        duplicate = await self._repository.find_by_content_checksum(
            document.tenant_id,
            document.ceo_id,
            document.content_checksum,
        )
        if duplicate is not None and (latest is None or duplicate.id != latest.id):
            return DocumentChangeDecision(
                kind=DocumentChangeKind.DUPLICATE,
                existing_document_id=duplicate.id,
                existing_version=duplicate.version,
                reason="canonical content matches another stored document",
            )
        return preliminary
