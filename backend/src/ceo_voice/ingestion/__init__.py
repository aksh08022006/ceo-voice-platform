"""Heterogeneous source ingestion contracts and pipeline boundaries."""

from ceo_voice.ingestion.connectors import SourceConnector
from ceo_voice.ingestion.contracts import (
    ConnectorCapabilities,
    FetchRequest,
    IngestionDocument,
    RawDocument,
    SourceItem,
)

__all__ = [
    "ConnectorCapabilities",
    "FetchRequest",
    "IngestionDocument",
    "RawDocument",
    "SourceConnector",
    "SourceItem",
]
