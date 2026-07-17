"""Closed generation vocabularies."""

from enum import StrEnum


class ProviderName(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class PromptSectionKind(StrEnum):
    SYSTEM = "system"
    VOICE = "voice"
    STRUCTURE = "structure"
    EVIDENCE = "evidence"
    REQUEST = "request"
    OUTPUT = "output"
    REPAIR = "repair"


class ValidationCode(StrEnum):
    EMPTY = "empty"
    PLATFORM_LENGTH = "platform_length"
    THREAD_NOT_SUPPORTED = "thread_not_supported"
    THREAD_LENGTH = "thread_length"
    THREAD_POST_LENGTH = "thread_post_length"
    THREAD_POST_COUNT = "thread_post_count"
    WORD_COUNT = "word_count"
    REQUIRED_CONSTRAINT = "required_constraint"
    UNSAFE_CONTENT = "unsafe_content"
    LOW_VOICE_CONFIDENCE = "low_voice_confidence"


class AttemptKind(StrEnum):
    INITIAL = "initial"
    PROVIDER_RETRY = "provider_retry"
    VALIDATION_REPAIR = "validation_repair"
