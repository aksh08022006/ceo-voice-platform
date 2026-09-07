"""Editorial expression controls and source-grounded observations, never personality scores."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from ceo_voice.models.base import ContractModel, NonBlankText
from ceo_voice.models.enums import Platform


class ExpressionDirection(ContractModel):
    """Editor intent for this draft; automatic means context-sensitive, not a fixed mood."""

    emotion: Literal[
        "auto",
        "neutral",
        "enthusiastic",
        "grateful",
        "reflective",
        "curious",
        "concerned",
        "determined",
    ] = "auto"
    intensity: Literal["restrained", "balanced", "expressive"] = "balanced"
    warmth: Literal["profile", "reserved", "warm"] = "profile"
    emoji_policy: Literal["match_profile", "none", "one"] = "match_profile"
    viewpoint: NonBlankText | None = Field(default=None, max_length=600)
    rationale: NonBlankText | None = Field(default=None, max_length=600)


class ExpressionExample(ContractModel):
    """Exact bounded source span. A lexical cue is a candidate, not a semantic diagnosis."""

    document_id: UUID
    source_url: str | None
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    text: NonBlankText
    cues: tuple[str, ...]
    complete_document: bool = False


class ExpressionProfile(ContractModel):
    """Versioned person/platform snapshot carried with the sealed generation context."""

    version: Literal["expression/1.0"] = "expression/1.0"
    leader_id: UUID
    platform: Platform
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    document_count: int = Field(ge=0)
    documents_with_emoji: int = Field(ge=0)
    emoji_inventory: tuple[str, ...] = ()
    cue_document_counts: dict[str, int] = Field(default_factory=dict)
    examples: tuple[ExpressionExample, ...] = ()
    limitations: tuple[str, ...] = (
        "Lexical cues need context: negation, quotation and irony can reverse their meaning.",
        "Historical viewpoints are topic-bound expression examples, not new facts or permanent beliefs.",
        "Exact duplicates are collapsed; campaign independence and provenance still need review.",
    )


EXPRESSION_INSTRUCTIONS = (
    "Expression controls apply to this draft, not the person's permanent beliefs. "
    "Follow the editor's emotion, intensity, warmth and viewpoint without changing facts or claim strength. "
    "Curiosity asks about an unresolved point; concern states the supplied reservation; "
    "gratitude credits a supplied contribution; enthusiasm reacts to the supplied event. "
    "Auto chooses a fitting register from the brief and observed writing. Never force excitement. "
    "Examples show wording in context; cue counts are not an emotion or ideology diagnosis. "
    "For emoji none, use none; for one, use at most one across the output. "
    "For match_profile, use only an observed symbol when its contextual purpose fits, otherwise omit it. "
    "Warmth never implies agreement, and stronger emotion never upgrades may to will. "
    "Preserve explicit brief prohibitions even when viewpoint or rationale conflicts with them."
)

EMOTION_GUIDANCE: dict[str, str] = {
    "auto": "Choose a fitting register from this brief and the person's observed expression; do not force a stock mood.",
    "neutral": "State the supplied point plainly, with no added excitement or alarm.",
    "enthusiastic": "Express enthusiasm about the supplied event or idea using this person's wording, without upgrading its promised benefits.",
    "grateful": "Recognize the supplied contribution and give credit without inventing people, relationships or assistance.",
    "reflective": "Consider what the supplied event or idea means; do not invent a memory or lesson from personal experience.",
    "curious": "Explore a genuine unresolved question about this idea. Let the question be visible in the text rather than merely providing a neutral summary.",
    "concerned": "Name the supplied reservation or tradeoff directly, without inventing harms or turning uncertainty into a prediction of failure.",
    "determined": "Express commitment to the stated direction, without adding promises, certainty or a new company plan.",
}
