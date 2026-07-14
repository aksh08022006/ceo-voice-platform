"""Closed vocabularies for structural engagement intelligence."""

from enum import StrEnum


class StructuralDimension(StrEnum):
    """Content-organization concerns that never specify personal wording."""

    OPENING_HOOK = "opening_hook"
    PACING = "pacing"
    TRANSITION = "transition"
    PARAGRAPH_RHYTHM = "paragraph_rhythm"
    NARRATIVE_SHAPE = "narrative_shape"
    CALL_TO_ACTION = "call_to_action"
    FORMATTING = "formatting"
    THREAD_ORGANIZATION = "thread_organization"
    ANNOUNCEMENT_STRUCTURE = "announcement_structure"


class EvidenceUnit(StrEnum):
    """Addressable source unit supporting a structural classification."""

    DOCUMENT = "document"
    OPENING = "opening"
    PARAGRAPH = "paragraph"
    CLOSING = "closing"


class MetricCollectionMethod(StrEnum):
    """How a performance snapshot was obtained."""

    PLATFORM_API = "platform_api"
    AUTHORIZED_EXPORT = "authorized_export"
    MANUAL = "manual"


class PerformanceBasis(StrEnum):
    """Denominator used by the transparent v1 performance normalizer."""

    IMPRESSIONS = "impressions"
    AUDIENCE = "audience"
    RAW_ENGAGEMENT = "raw_engagement"


class PatternAuthority(StrEnum):
    """Maximum justified use of an aggregate structural pattern."""

    INSUFFICIENT = "insufficient"
    DESCRIPTIVE = "descriptive"


class PublicationStatus(StrEnum):
    """Catalog state for an immutable virality release."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"


class ValidationSeverity(StrEnum):
    """Severity of a structural release validation issue."""

    ERROR = "error"
    WARNING = "warning"


class ValidationCode(StrEnum):
    """Stable machine-readable validation categories."""

    OWNERSHIP = "ownership"
    REGISTRY = "registry"
    EVIDENCE = "evidence"
    OBSERVATION = "observation"
    AGGREGATE = "aggregate"
    VERSION = "version"


class PatternChangeStatus(StrEnum):
    """Disposition of a pattern across two immutable releases."""

    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
