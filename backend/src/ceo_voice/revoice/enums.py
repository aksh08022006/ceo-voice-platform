"""Closed vocabularies for deterministic Re-Voice decisions and reports."""

from enum import StrEnum


class ChangeKind(StrEnum):
    EQUAL = "equal"
    INSERT = "insert"
    DELETE = "delete"
    REPLACE = "replace"


class ProtectionKind(StrEnum):
    UNCHANGED_TEXT = "unchanged_text"
    URL = "url"
    EMAIL = "email"
    SOCIAL_REFERENCE = "social_reference"
    NUMBER = "number"
    QUOTATION = "quotation"
    MARKDOWN_LINK = "markdown_link"
    INLINE_CODE = "inline_code"
    PROPER_NOUN = "proper_noun"
    CTA = "cta"


class ReVoiceValidationCode(StrEnum):
    EMPTY = "empty"
    INVALID_CONTROL_CHARACTER = "invalid_control_character"
    STRUCTURE_CHANGED = "structure_changed"
    FORMATTING_CHANGED = "formatting_changed"
    PROTECTED_TEXT_CHANGED = "protected_text_changed"
    CHANGE_BUDGET_EXCEEDED = "change_budget_exceeded"
    PLATFORM_LENGTH = "platform_length"
    THREAD_LENGTH = "thread_length"
    UNSAFE_CONTENT = "unsafe_content"
    HARD_CONSTRAINT_VIOLATED = "hard_constraint_violated"


class ReVoiceAttemptKind(StrEnum):
    INITIAL = "initial"
    PROVIDER_RETRY = "provider_retry"
    VALIDATION_REPAIR = "validation_repair"
