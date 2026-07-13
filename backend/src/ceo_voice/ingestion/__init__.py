"""Heterogeneous source ingestion contracts and pipeline boundaries."""

from ceo_voice.ingestion.connectors import SourceConnector
from ceo_voice.ingestion.contracts import (
    CleanedContent,
    ConnectorCapabilities,
    ExtractedMetadata,
    FetchRequest,
    IngestionDocument,
    ParsedContent,
    RawDocument,
    SourceItem,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)
from ceo_voice.ingestion.stages import (
    ContentParser,
    DocumentCleaner,
    DocumentNormalizer,
    DocumentValidator,
    MetadataExtractor,
    RawDocumentFactory,
    SourceItemValidator,
)

__all__ = [
    "CleanedContent",
    "ConnectorCapabilities",
    "ContentParser",
    "DocumentCleaner",
    "DocumentNormalizer",
    "DocumentValidator",
    "ExtractedMetadata",
    "FetchRequest",
    "IngestionDocument",
    "MetadataExtractor",
    "ParsedContent",
    "RawDocument",
    "RawDocumentFactory",
    "SourceConnector",
    "SourceItem",
    "SourceItemValidator",
    "ValidationIssue",
    "ValidationResult",
    "ValidationSeverity",
]
