"""Governed public-source discovery and corpus readiness auditing."""

from ceo_voice.acquisition.audit import CorpusAcquisitionAuditor
from ceo_voice.acquisition.contracts import (
    CorpusAcquisitionPolicy,
    CorpusAcquisitionReport,
    CorpusAuditFinding,
    SourceCatalogEntry,
    SourceCatalogManifest,
)
from ceo_voice.acquisition.enums import (
    AcquisitionMethod,
    AuditSeverity,
    AuthorshipBasis,
    CorpusContentRole,
    SourceReviewStatus,
)
from ceo_voice.acquisition.io import load_source_catalog

__all__ = [
    "AcquisitionMethod",
    "AuditSeverity",
    "AuthorshipBasis",
    "CorpusAcquisitionAuditor",
    "CorpusAcquisitionPolicy",
    "CorpusAcquisitionReport",
    "CorpusAuditFinding",
    "CorpusContentRole",
    "SourceCatalogEntry",
    "SourceCatalogManifest",
    "SourceReviewStatus",
    "load_source_catalog",
]
