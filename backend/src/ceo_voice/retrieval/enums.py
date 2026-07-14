"""Closed vocabularies for deterministic generation retrieval."""

from enum import StrEnum


class EvidenceSourceKind(StrEnum):
    """Governed origin of a materialized evidence span."""

    HVM = "hvm"
    VKR = "vkr"
    REQUEST = "request"


class EvidencePurpose(StrEnum):
    """Generation requirement satisfied by selected evidence."""

    VOICE_SUPPORT = "voice_support"
    REPRESENTATIVE_EXAMPLE = "representative_example"
    COUNTEREXAMPLE = "counterexample"
    STRUCTURAL_SUPPORT = "structural_support"
    NEGATIVE_CONSTRAINT = "negative_constraint"
    FACTUAL_SUPPORT = "factual_support"
    PLATFORM_REFERENCE = "platform_reference"


class RetrievalPruneReason(StrEnum):
    """Stable reason a relevant candidate was not included."""

    LOWER_RANK = "lower_rank"
    ITEM_BUDGET = "item_budget"
    CHARACTER_BUDGET = "character_budget"
    EXAMPLE_BUDGET = "example_budget"
    PER_REQUIREMENT_BUDGET = "per_requirement_budget"
    DUPLICATE_DOCUMENT = "duplicate_document"
    PLATFORM_MISMATCH = "platform_mismatch"
    RIGHTS_RESTRICTED = "rights_restricted"
    UNSUPPORTED = "unsupported"


class KnowledgeKind(StrEnum):
    """Structured knowledge categories retained in a bundle."""

    VOICE_FEATURE = "voice_feature"
    STRUCTURAL_PATTERN = "structural_pattern"
    OBSERVATION = "observation"
    AGGREGATE = "aggregate"
    PREFERENCE = "preference"
    NEGATIVE_CONSTRAINT = "negative_constraint"
    PLATFORM_POLICY = "platform_policy"
