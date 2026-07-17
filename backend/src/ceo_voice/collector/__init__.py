"""Fail-closed, offline public-content collection primitives.

This package intentionally contains no X or LinkedIn browser automation.
"""

from ceo_voice.collector.contracts import (
    AcquisitionDecision,
    AuthorizationReceipt,
    Checkpoint,
    ConnectorCapabilities,
    SourcePolicy,
)
from ceo_voice.collector.service import CollectorService, LocalFileStore

__all__ = [
    "AcquisitionDecision",
    "AuthorizationReceipt",
    "Checkpoint",
    "CollectorService",
    "ConnectorCapabilities",
    "LocalFileStore",
    "SourcePolicy",
]
