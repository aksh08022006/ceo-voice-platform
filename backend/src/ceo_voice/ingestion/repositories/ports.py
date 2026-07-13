"""Async persistence ports owned by the ingestion application boundary."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from ceo_voice.ingestion.contracts import (
    CleanDocument,
    ConnectorCheckpoint,
    ExtractedMetadata,
    RawDocument,
    RepositoryWriteDisposition,
)
from ceo_voice.models.enums import DocumentSourceType


@runtime_checkable
class RawDocumentRepository(Protocol):
    """Persist and retrieve immutable raw artifacts."""

    async def save(self, document: RawDocument) -> RepositoryWriteDisposition:
        """Persist a raw artifact idempotently."""

        ...

    async def get(self, tenant_id: UUID, document_id: UUID) -> RawDocument | None:
        """Return a tenant-scoped raw artifact."""

        ...


@runtime_checkable
class CleanDocumentRepository(Protocol):
    """Persist and query versioned canonical clean documents."""

    async def save(self, document: CleanDocument) -> RepositoryWriteDisposition:
        """Persist the next valid document version idempotently."""

        ...

    async def get(self, tenant_id: UUID, document_id: UUID, version: int) -> CleanDocument | None:
        """Return one tenant-scoped document version."""

        ...

    async def get_latest_by_source(
        self,
        tenant_id: UUID,
        ceo_id: UUID,
        source: DocumentSourceType,
        external_id: str,
    ) -> CleanDocument | None:
        """Return the latest document for a stable source identity."""

        ...

    async def find_by_raw_checksum(
        self, tenant_id: UUID, ceo_id: UUID, checksum: str
    ) -> CleanDocument | None:
        """Find exact raw duplication within one leader corpus."""

        ...

    async def find_by_content_checksum(
        self, tenant_id: UUID, ceo_id: UUID, checksum: str
    ) -> CleanDocument | None:
        """Find exact canonical-content duplication within one leader corpus."""

        ...


@runtime_checkable
class MetadataRepository(Protocol):
    """Persist and retrieve metadata independently from content payloads."""

    async def save(self, metadata: ExtractedMetadata) -> RepositoryWriteDisposition:
        """Persist one versioned metadata projection idempotently."""

        ...

    async def get(
        self, tenant_id: UUID, document_id: UUID, version: int
    ) -> ExtractedMetadata | None:
        """Return one tenant-scoped metadata projection."""

        ...


@runtime_checkable
class CheckpointRepository(Protocol):
    """Persist successful connector progress without owning synchronization policy."""

    async def save(self, checkpoint: ConnectorCheckpoint) -> RepositoryWriteDisposition:
        """Create or advance a connector checkpoint."""

        ...

    async def get(
        self, tenant_id: UUID, ceo_id: UUID, connector_id: str
    ) -> ConnectorCheckpoint | None:
        """Return the latest tenant- and leader-scoped checkpoint."""

        ...


@dataclass(frozen=True, slots=True)
class IngestionRepositories:
    """Explicit repository bundle injected into ingestion orchestration."""

    raw_documents: RawDocumentRepository
    clean_documents: CleanDocumentRepository
    metadata: MetadataRepository
    checkpoints: CheckpointRepository
