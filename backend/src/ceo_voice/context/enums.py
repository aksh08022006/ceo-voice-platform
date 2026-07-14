"""Closed vocabularies for deterministic generation-context compilation."""

from enum import StrEnum


class VoiceResolutionSource(StrEnum):
    """Source that governs a compiled voice target."""

    CORE_RESIDUAL = "core_residual"
    PLATFORM_CONDITIONAL = "platform_conditional"
    EXPLICIT_PREFERENCE = "explicit_preference"


class ConstraintCategory(StrEnum):
    """Independent origin or purpose of a compiled constraint."""

    PLATFORM = "platform"
    FORMATTING = "formatting"
    USER = "user"
    NEGATIVE_VOICE = "negative_voice"
    SAFETY = "safety"


class ConstraintStrength(StrEnum):
    """Whether a future consumer must enforce or should prefer a constraint."""

    HARD = "hard"
    SOFT = "soft"


class ConstraintOperator(StrEnum):
    """Model-neutral operation represented by a compiled constraint."""

    EQUALS = "equals"
    MAXIMUM = "maximum"
    MINIMUM = "minimum"
    PROHIBIT = "prohibit"
    INSTRUCTION = "instruction"


class IgnoredReason(StrEnum):
    """Stable reasons why knowledge did not cross the compilation boundary."""

    NOT_GENERATION_AUTHORIZED = "not_generation_authorized"
    NON_ACTIONABLE = "non_actionable"
    LOW_CONFIDENCE = "low_confidence"
    PLATFORM_MISMATCH = "platform_mismatch"
    LANGUAGE_MISMATCH = "language_mismatch"
    SUPERSEDED_BY_CONTEXT = "superseded_by_context"
    SUPERSEDED_BY_PREFERENCE = "superseded_by_preference"
    DEPENDENCY_NOT_SELECTED = "dependency_not_selected"
    INSUFFICIENT_SUPPORT = "insufficient_support"
    INSUFFICIENT_AUTHORITY = "insufficient_authority"
    SELECTION_LIMIT = "selection_limit"


class TraceArtifactKind(StrEnum):
    """Knowledge artifact represented in compilation provenance."""

    HVM_RELEASE = "hvm_release"
    HVM_COMPONENT = "hvm_component"
    HVM_EVIDENCE = "hvm_evidence"
    VKR_RELEASE = "vkr_release"
    VKR_PATTERN = "vkr_pattern"
    VKR_EVIDENCE = "vkr_evidence"
    RETRIEVAL = "retrieval"
