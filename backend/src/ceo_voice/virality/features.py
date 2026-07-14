"""Versioned structural feature catalog for deterministic virality v1."""

from uuid import NAMESPACE_URL, uuid5

from ceo_voice.virality.contracts import (
    FeatureReference,
    StructuralFeatureDefinition,
    Version,
)
from ceo_voice.virality.enums import StructuralDimension
from ceo_voice.virality.registry import StructuralFeatureRegistry

VERSION = Version(major=1, minor=0, patch=0)
REGISTRY_ID = uuid5(NAMESPACE_URL, "ceo-voice:virality-structural-registry")

HOOK = FeatureReference(feature_id="structure.hook-type", version=VERSION)
OPENING = FeatureReference(feature_id="structure.opening-length", version=VERSION)
PACING = FeatureReference(feature_id="structure.sentence-pacing", version=VERSION)
PARAGRAPH = FeatureReference(feature_id="structure.paragraph-rhythm", version=VERSION)
TRANSITION = FeatureReference(feature_id="structure.transition-strategy", version=VERSION)
NARRATIVE = FeatureReference(feature_id="structure.narrative-shape", version=VERSION)
CTA = FeatureReference(feature_id="structure.cta-pattern", version=VERSION)
FORMATTING = FeatureReference(feature_id="structure.formatting-strategy", version=VERSION)
THREAD = FeatureReference(feature_id="structure.thread-organization", version=VERSION)
ANNOUNCEMENT = FeatureReference(feature_id="structure.announcement-organization", version=VERSION)


def build_feature_registry() -> StructuralFeatureRegistry:
    """Build the complete content-addressed v1 structural vocabulary."""

    definitions = (
        _definition(
            HOOK,
            "Hook type",
            "Functional opening device without retaining its wording.",
            StructuralDimension.OPENING_HOOK,
            ("question", "numeric", "announcement", "contrast", "personal_story", "direct_claim"),
            "opening-extractor",
        ),
        _definition(
            OPENING,
            "Opening length",
            "Word-budget band of the first paragraph.",
            StructuralDimension.OPENING_HOOK,
            ("short", "medium", "extended"),
            "opening-extractor",
        ),
        _definition(
            PACING,
            "Sentence pacing",
            "Document-level sentence-length cadence band.",
            StructuralDimension.PACING,
            ("short", "medium", "long", "varied"),
            "rhythm-extractor",
        ),
        _definition(
            PARAGRAPH,
            "Paragraph rhythm",
            "Paragraph-length and alternation strategy.",
            StructuralDimension.PARAGRAPH_RHYTHM,
            ("compact", "standard", "longform", "varied"),
            "rhythm-extractor",
        ),
        _definition(
            TRANSITION,
            "Transition strategy",
            "Dominant functional relationship between content blocks.",
            StructuralDimension.TRANSITION,
            ("contrastive", "causal", "sequential", "concluding", "mixed", "implicit"),
            "transition-extractor",
        ),
        _definition(
            NARRATIVE,
            "Narrative shape",
            "Reusable document-level information organization.",
            StructuralDimension.NARRATIVE_SHAPE,
            (
                "listicle",
                "announcement_details",
                "problem_solution",
                "story_lesson",
                "question_answer",
                "claim_evidence",
                "linear_exposition",
            ),
            "narrative-extractor",
        ),
        _definition(
            CTA,
            "Call-to-action pattern",
            "Functional close strategy without retaining the wording.",
            StructuralDimension.CALL_TO_ACTION,
            (
                "audience_question",
                "direct_action",
                "resource_direction",
                "community_invitation",
                "none",
            ),
            "cta-extractor",
        ),
        _definition(
            FORMATTING,
            "Formatting strategy",
            "Dominant visual organization tactic.",
            StructuralDimension.FORMATTING,
            ("list_led", "heading_sectioned", "whitespace_broken", "dense", "plain"),
            "formatting-extractor",
        ),
        _definition(
            THREAD,
            "Thread organization",
            "Declared post sequence length band.",
            StructuralDimension.THREAD_ORGANIZATION,
            ("single_post", "short_thread", "long_thread"),
            "thread-extractor",
        ),
        _definition(
            ANNOUNCEMENT,
            "Announcement organization",
            "Ordering used when the opening is an announcement.",
            StructuralDimension.ANNOUNCEMENT_STRUCTURE,
            ("outcome_first", "context_first", "details_first"),
            "announcement-extractor",
        ),
    )
    return StructuralFeatureRegistry.build(
        registry_id=REGISTRY_ID,
        version=VERSION,
        definitions=definitions,
    )


def _definition(
    reference: FeatureReference,
    name: str,
    description: str,
    dimension: StructuralDimension,
    allowed: tuple[str, ...],
    extractor_id: str,
) -> StructuralFeatureDefinition:
    return StructuralFeatureDefinition(
        reference=reference,
        display_name=name,
        description=description,
        dimension=dimension,
        allowed_patterns=allowed,
        extractor_id=extractor_id,
    )
