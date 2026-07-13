"""Enumerations shared by typed domain contracts."""

from enum import StrEnum


class Platform(StrEnum):
    """Content destination whose conventions affect output and evaluation."""

    LINKEDIN = "linkedin"
    X = "x"
    YOUTUBE = "youtube"
    PODCAST = "podcast"
    BLOG = "blog"
    NEWSLETTER = "newsletter"
    GENERIC = "generic"


class DocumentSourceType(StrEnum):
    """Origin of an ingested source document."""

    LINKEDIN = "linkedin"
    X = "x"
    BLOG = "blog"
    NEWSLETTER = "newsletter"
    INTERVIEW = "interview"
    PODCAST = "podcast"
    YOUTUBE = "youtube"
    VIDEO = "video"
    EARNINGS_CALL = "earnings_call"
    SHAREHOLDER_LETTER = "shareholder_letter"
    CONFERENCE_TALK = "conference_talk"
    FILE_UPLOAD = "file_upload"
    OTHER = "other"


class DocumentType(StrEnum):
    """Canonical content form independent of the source provider."""

    SOCIAL_POST = "social_post"
    VIDEO_TRANSCRIPT = "video_transcript"
    PODCAST_TRANSCRIPT = "podcast_transcript"
    EARNINGS_CALL_TRANSCRIPT = "earnings_call_transcript"
    BLOG_POST = "blog_post"
    INTERVIEW_TRANSCRIPT = "interview_transcript"
    SHAREHOLDER_LETTER = "shareholder_letter"
    CONFERENCE_TALK_TRANSCRIPT = "conference_talk_transcript"
    NEWSLETTER = "newsletter"
    OTHER = "other"


class ContentFormat(StrEnum):
    """Transport format of content before source-independent parsing."""

    PLAIN_TEXT = "plain_text"
    HTML = "html"
    MARKDOWN = "markdown"


class DocumentStatus(StrEnum):
    """Eligibility of a document for downstream processing."""

    ACTIVE = "active"
    EXCLUDED = "excluded"


class VoiceFeatureLayer(StrEnum):
    """Linguistic layer represented by a voice feature."""

    LEXICAL = "lexical"
    SYNTACTIC = "syntactic"
    RHETORICAL = "rhetorical"
    NARRATIVE = "narrative"
    PRAGMATIC = "pragmatic"
    FORMATTING = "formatting"
    PLATFORM_BEHAVIOR = "platform_behavior"


class FeatureScope(StrEnum):
    """Whether a feature is stable globally or conditioned on a platform."""

    GLOBAL = "global"
    PLATFORM = "platform"


class VoiceProfileStatus(StrEnum):
    """Lifecycle state of a versioned voice profile."""

    DRAFT = "draft"
    APPROVED = "approved"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class ContextRole(StrEnum):
    """Reason a retrieved item is present in generation context."""

    VOICE_EVIDENCE = "voice_evidence"
    FACTUAL_EVIDENCE = "factual_evidence"
    STRUCTURAL_REFERENCE = "structural_reference"
    PLATFORM_REFERENCE = "platform_reference"


class EvaluationStatus(StrEnum):
    """Aggregate disposition of an evaluated candidate."""

    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class GenerationStatus(StrEnum):
    """Completion state of a generation response."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
