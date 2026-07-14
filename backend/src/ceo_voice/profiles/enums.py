"""Workflow states for executable profile building and reporting."""

from enum import StrEnum


class BuildStage(StrEnum):
    """Durable restart points in the profile workflow."""

    ANALYZING = "analyzing"
    COMPILING = "compiling"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProgressKind(StrEnum):
    """Stable progress event categories for CLI and workflow adapters."""

    BUILD_STARTED = "build_started"
    DOCUMENT_ANALYZED = "document_analyzed"
    DOCUMENT_REUSED = "document_reused"
    DOCUMENT_FAILED = "document_failed"
    COMPILATION_STARTED = "compilation_started"
    PUBLICATION_STARTED = "publication_started"
    BUILD_COMPLETED = "build_completed"
    BUILD_FAILED = "build_failed"


class CorpusHealthStatus(StrEnum):
    """Corpus disposition independent of release lifecycle status."""

    HEALTHY = "healthy"
    WARNING = "warning"
    BLOCKED = "blocked"


class ProfileAuthority(StrEnum):
    """Highest scientifically justified use of the published profile."""

    DESCRIPTIVE = "descriptive"
    GENERATION_READY = "generation_ready"
