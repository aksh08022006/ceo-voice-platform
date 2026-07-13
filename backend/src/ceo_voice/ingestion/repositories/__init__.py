"""Ingestion persistence ports and local in-memory adapters."""

from ceo_voice.ingestion.repositories.memory import (
    InMemoryCheckpointRepository,
    InMemoryCleanDocumentRepository,
    InMemoryMetadataRepository,
    InMemoryRawDocumentRepository,
)
from ceo_voice.ingestion.repositories.ports import (
    CheckpointRepository,
    CleanDocumentRepository,
    IngestionRepositories,
    MetadataRepository,
    RawDocumentRepository,
)
from ceo_voice.ingestion.repositories.projection import to_clean_document

__all__ = [
    "CheckpointRepository",
    "CleanDocumentRepository",
    "InMemoryCheckpointRepository",
    "InMemoryCleanDocumentRepository",
    "InMemoryMetadataRepository",
    "InMemoryRawDocumentRepository",
    "IngestionRepositories",
    "MetadataRepository",
    "RawDocumentRepository",
    "to_clean_document",
]
