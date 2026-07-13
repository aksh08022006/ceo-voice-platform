"""Concurrency-safe in-memory repository adapters for tests and local composition."""

import asyncio
from uuid import UUID

from ceo_voice.core.exceptions import StorageError
from ceo_voice.ingestion.contracts import (
    CleanDocument,
    ConnectorCheckpoint,
    ExtractedMetadata,
    RawDocument,
)
from ceo_voice.ingestion.outcomes import RepositoryWriteDisposition
from ceo_voice.models.enums import DocumentSourceType

_DocumentVersionKey = tuple[UUID, UUID, int]
_SourceKey = tuple[UUID, UUID, DocumentSourceType, str]
_FingerprintKey = tuple[UUID, UUID, DocumentSourceType, str]
_CheckpointKey = tuple[UUID, UUID, str]


class InMemoryRawDocumentRepository:
    """Store immutable raw artifacts with tenant-scoped keys."""

    def __init__(self) -> None:
        self._documents: dict[tuple[UUID, UUID], RawDocument] = {}
        self._lock = asyncio.Lock()

    async def save(self, document: RawDocument) -> RepositoryWriteDisposition:
        key = (document.tenant_id, document.id)
        async with self._lock:
            existing = self._documents.get(key)
            if existing == document:
                return RepositoryWriteDisposition.ALREADY_EXISTS
            if existing is not None and (
                existing.ceo_id,
                existing.external_id,
                existing.source,
                existing.content_format,
                existing.raw_content,
                existing.raw_checksum,
                existing.source_fingerprint,
            ) == (
                document.ceo_id,
                document.external_id,
                document.source,
                document.content_format,
                document.raw_content,
                document.raw_checksum,
                document.source_fingerprint,
            ):
                return RepositoryWriteDisposition.ALREADY_EXISTS
            if existing is not None:
                raise StorageError(
                    "Raw artifact identity conflict.",
                    details={"document_id": str(document.id)},
                )
            self._documents[key] = document
            return RepositoryWriteDisposition.CREATED

    async def get(self, tenant_id: UUID, document_id: UUID) -> RawDocument | None:
        async with self._lock:
            return self._documents.get((tenant_id, document_id))


class InMemoryCleanDocumentRepository:
    """Store contiguous canonical versions and checksum indexes."""

    def __init__(self) -> None:
        self._documents: dict[_DocumentVersionKey, CleanDocument] = {}
        self._latest_by_source: dict[_SourceKey, _DocumentVersionKey] = {}
        self._source_fingerprints: dict[_FingerprintKey, _DocumentVersionKey] = {}
        self._document_fingerprints: dict[_FingerprintKey, _DocumentVersionKey] = {}
        self._lock = asyncio.Lock()

    async def save(self, document: CleanDocument) -> RepositoryWriteDisposition:
        key = (document.tenant_id, document.id, document.version)
        source_key = (
            document.tenant_id,
            document.ceo_id,
            document.source,
            document.external_id,
        )
        async with self._lock:
            existing = self._documents.get(key)
            if existing == document:
                return RepositoryWriteDisposition.ALREADY_EXISTS
            if existing is not None:
                raise StorageError(
                    "Clean document version conflict.",
                    details={"document_id": str(document.id), "version": document.version},
                )

            latest_key = self._latest_by_source.get(source_key)
            expected_version = 1
            if latest_key is not None:
                expected_version = self._documents[latest_key].version + 1
            if document.version != expected_version:
                raise StorageError(
                    "Clean document version is not contiguous.",
                    details={
                        "document_id": str(document.id),
                        "expected_version": expected_version,
                        "actual_version": document.version,
                    },
                )

            self._documents[key] = document
            self._latest_by_source[source_key] = key
            self._source_fingerprints.setdefault(
                (
                    document.tenant_id,
                    document.ceo_id,
                    document.source,
                    document.source_fingerprint,
                ),
                key,
            )
            self._document_fingerprints.setdefault(
                (
                    document.tenant_id,
                    document.ceo_id,
                    document.source,
                    document.document_fingerprint,
                ),
                key,
            )
            return RepositoryWriteDisposition.CREATED

    async def get(self, tenant_id: UUID, document_id: UUID, version: int) -> CleanDocument | None:
        async with self._lock:
            return self._documents.get((tenant_id, document_id, version))

    async def get_latest_by_source(
        self,
        tenant_id: UUID,
        ceo_id: UUID,
        source: DocumentSourceType,
        external_id: str,
    ) -> CleanDocument | None:
        source_key = (tenant_id, ceo_id, source, external_id)
        async with self._lock:
            key = self._latest_by_source.get(source_key)
            return self._documents.get(key) if key else None

    async def find_by_source_fingerprint(
        self,
        tenant_id: UUID,
        ceo_id: UUID,
        source: DocumentSourceType,
        fingerprint: str,
    ) -> CleanDocument | None:
        async with self._lock:
            key = self._source_fingerprints.get((tenant_id, ceo_id, source, fingerprint))
            return self._documents.get(key) if key else None

    async def find_by_document_fingerprint(
        self,
        tenant_id: UUID,
        ceo_id: UUID,
        source: DocumentSourceType,
        fingerprint: str,
    ) -> CleanDocument | None:
        async with self._lock:
            key = self._document_fingerprints.get((tenant_id, ceo_id, source, fingerprint))
            return self._documents.get(key) if key else None


class InMemoryMetadataRepository:
    """Store metadata projections under tenant, document, and version."""

    def __init__(self) -> None:
        self._metadata: dict[_DocumentVersionKey, ExtractedMetadata] = {}
        self._lock = asyncio.Lock()

    async def save(self, metadata: ExtractedMetadata) -> RepositoryWriteDisposition:
        key = (metadata.tenant_id, metadata.document_id, metadata.document_version)
        async with self._lock:
            existing = self._metadata.get(key)
            if existing == metadata:
                return RepositoryWriteDisposition.ALREADY_EXISTS
            if existing is not None:
                raise StorageError(
                    "Metadata version conflict.",
                    details={
                        "document_id": str(metadata.document_id),
                        "version": metadata.document_version,
                    },
                )
            self._metadata[key] = metadata
            return RepositoryWriteDisposition.CREATED

    async def get(
        self, tenant_id: UUID, document_id: UUID, version: int
    ) -> ExtractedMetadata | None:
        async with self._lock:
            return self._metadata.get((tenant_id, document_id, version))


class InMemoryCheckpointRepository:
    """Store monotonic connector checkpoints."""

    def __init__(self) -> None:
        self._checkpoints: dict[_CheckpointKey, ConnectorCheckpoint] = {}
        self._lock = asyncio.Lock()

    async def save(self, checkpoint: ConnectorCheckpoint) -> RepositoryWriteDisposition:
        key = (checkpoint.tenant_id, checkpoint.ceo_id, checkpoint.connector_id)
        async with self._lock:
            existing = self._checkpoints.get(key)
            if existing == checkpoint:
                return RepositoryWriteDisposition.ALREADY_EXISTS
            if existing is not None and checkpoint.updated_at <= existing.updated_at:
                raise StorageError(
                    "Connector checkpoint cannot move backward or conflict at the same timestamp.",
                    details={"connector_id": checkpoint.connector_id},
                )
            disposition = (
                RepositoryWriteDisposition.UPDATED
                if existing is not None
                else RepositoryWriteDisposition.CREATED
            )
            self._checkpoints[key] = checkpoint
            return disposition

    async def get(
        self, tenant_id: UUID, ceo_id: UUID, connector_id: str
    ) -> ConnectorCheckpoint | None:
        async with self._lock:
            return self._checkpoints.get((tenant_id, ceo_id, connector_id))
