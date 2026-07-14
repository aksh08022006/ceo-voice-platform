"""Closed vocabularies for the voice-analysis compiler layer."""

from enum import StrEnum


class AnalyzerCategory(StrEnum):
    """Independent analyzer families used for discovery and governance."""

    FORMATTING = "formatting"
    LEXICAL = "lexical"
    STRUCTURAL = "structural"
    SYNTACTIC = "syntactic"
    SEMANTIC = "semantic"
    RHETORICAL = "rhetorical"
    BEHAVIORAL = "behavioral"
    PLATFORM = "platform"
    TEMPORAL = "temporal"


class AnalyzerInput(StrEnum):
    """Compiler artifacts an analyzer requires before it may execute."""

    DOCUMENT = "document"
    PARAGRAPHS = "paragraphs"
    SENTENCES = "sentences"
    LINES = "lines"


class AnalyzerRunStatus(StrEnum):
    """Stable analyzer outcome recorded in the deterministic execution trace."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CACHE_HIT = "cache_hit"


class AnalysisRunStatus(StrEnum):
    """Aggregate disposition of one document analysis run."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class ConfidenceMethod(StrEnum):
    """Extensible confidence-composition method classes."""

    DETERMINISTIC = "deterministic"
    STATISTICAL = "statistical"
    CLASSIFIER = "classifier"
    LLM = "llm"
    EVIDENCE_WEIGHTED = "evidence_weighted"
