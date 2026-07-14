"""Deterministic, wording-free classifiers for reusable content organization."""

import re
from abc import ABC, abstractmethod
from statistics import fmean, pstdev
from typing import ClassVar

from ceo_voice.virality.contracts import (
    ExtractionContext,
    ExtractorSpecification,
    FeatureReference,
    PatternMeasurement,
)
from ceo_voice.virality.enums import EvidenceUnit
from ceo_voice.virality.features import (
    ANNOUNCEMENT,
    CTA,
    FORMATTING,
    HOOK,
    NARRATIVE,
    OPENING,
    PACING,
    PARAGRAPH,
    THREAD,
    TRANSITION,
    VERSION,
)

_WORD = re.compile(r"\b[\w'-]+\b", re.UNICODE)
_SENTENCE = re.compile(r"[^.!?]+[.!?]?", re.MULTILINE)
_LIST_LINE = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+")
_HEADING_LINE = re.compile(r"(?m)^\s*(?:#{1,6}\s+|[A-Z][A-Z\s]{3,}:?\s*$)")
_ANNOUNCEMENT = ("announce", "announcing", "launch", "launching", "introducing", "today we")


def _paragraphs(text: str) -> tuple[tuple[int, int, str], ...]:
    return tuple(
        (match.start(), match.end(), match.group())
        for match in re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", text, re.DOTALL)
    )


def _sentences(text: str) -> tuple[str, ...]:
    return tuple(item.group().strip() for item in _SENTENCE.finditer(text) if item.group().strip())


def _words(text: str) -> tuple[str, ...]:
    return tuple(item.group() for item in _WORD.finditer(text))


def _measurement(
    feature: FeatureReference,
    key: str,
    label: str,
    unit: EvidenceUnit,
    start: int,
    end: int,
) -> PatternMeasurement:
    return PatternMeasurement(
        feature=feature,
        pattern_key=key,
        label=label,
        unit=unit,
        start=start,
        end=end,
    )


class BaseExtractor(ABC):
    """Shared immutable specification plumbing for deterministic extractors."""

    extractor_id: str
    features: tuple[FeatureReference, ...]

    @property
    def specification(self) -> ExtractorSpecification:
        return ExtractorSpecification(
            extractor_id=self.extractor_id,
            version=VERSION,
            features=self.features,
        )

    @abstractmethod
    def extract(self, context: ExtractionContext) -> tuple[PatternMeasurement, ...]:
        """Return structural classifications for one canonical post."""


class OpeningExtractor(BaseExtractor):
    """Classify the functional hook and first-paragraph budget."""

    extractor_id = "opening-extractor"
    features = (HOOK, OPENING)

    def extract(self, context: ExtractionContext) -> tuple[PatternMeasurement, ...]:
        text = context.document.content
        start, end, opening = _paragraphs(text)[0]
        lowered = opening.lower().strip()
        if "?" in opening:
            hook = "question"
        elif lowered.startswith(_ANNOUNCEMENT):
            hook = "announcement"
        elif re.search(r"\d", opening):
            hook = "numeric"
        elif lowered.startswith(("but ", "however", "most people", "the problem")):
            hook = "contrast"
        elif re.search(r"\b(i|we)\b", lowered) and re.search(
            r"\b(remember|years ago|last year|when)\b", lowered
        ):
            hook = "personal_story"
        else:
            hook = "direct_claim"
        count = len(_words(opening))
        length = "short" if count <= 12 else "medium" if count <= 30 else "extended"
        return (
            _measurement(
                HOOK, hook, hook.replace("_", " ").title(), EvidenceUnit.OPENING, start, end
            ),
            _measurement(
                OPENING,
                length,
                f"{length.title()} opening",
                EvidenceUnit.OPENING,
                start,
                end,
            ),
        )


class RhythmExtractor(BaseExtractor):
    """Classify sentence pacing and paragraph rhythm using length bands."""

    extractor_id = "rhythm-extractor"
    features = (PACING, PARAGRAPH)

    def extract(self, context: ExtractionContext) -> tuple[PatternMeasurement, ...]:
        text = context.document.content
        sentence_lengths = tuple(len(_words(item)) for item in _sentences(text))
        paragraph_lengths = tuple(len(_words(item[2])) for item in _paragraphs(text))
        pacing = self._band(sentence_lengths, short=10, long=24)
        paragraph = self._band(paragraph_lengths, short=24, long=70)
        return (
            _measurement(
                PACING, pacing, f"{pacing.title()} pacing", EvidenceUnit.DOCUMENT, 0, len(text)
            ),
            _measurement(
                PARAGRAPH,
                (
                    "compact"
                    if paragraph == "short"
                    else "longform" if paragraph == "long" else paragraph
                ),
                f"{paragraph.title()} paragraph rhythm",
                EvidenceUnit.DOCUMENT,
                0,
                len(text),
            ),
        )

    @staticmethod
    def _band(values: tuple[int, ...], *, short: int, long: int) -> str:
        average = fmean(values)
        if len(values) > 1 and pstdev(values) > max(4, average * 0.55):
            return "varied"
        return (
            "short"
            if average <= short
            else "long" if average >= long else "medium" if short == 10 else "standard"
        )


class TransitionExtractor(BaseExtractor):
    """Classify transition function without retaining preferred transition phrases."""

    extractor_id = "transition-extractor"
    features = (TRANSITION,)
    _groups: ClassVar[dict[str, tuple[str, ...]]] = {
        "contrastive": ("but", "however", "yet", "instead"),
        "causal": ("because", "therefore", "so that", "as a result"),
        "sequential": ("first", "second", "next", "then"),
        "concluding": ("finally", "in short", "the lesson", "ultimately"),
    }

    def extract(self, context: ExtractionContext) -> tuple[PatternMeasurement, ...]:
        text = context.document.content
        lowered = text.lower()
        present = tuple(
            name
            for name, markers in self._groups.items()
            if any(marker in lowered for marker in markers)
        )
        key = "implicit" if not present else present[0] if len(present) == 1 else "mixed"
        return (
            _measurement(
                TRANSITION,
                key,
                f"{key.title()} transitions",
                EvidenceUnit.DOCUMENT,
                0,
                len(text),
            ),
        )


class NarrativeExtractor(BaseExtractor):
    """Classify document-level rhetorical organization through explicit rules."""

    extractor_id = "narrative-extractor"
    features = (NARRATIVE,)

    def extract(self, context: ExtractionContext) -> tuple[PatternMeasurement, ...]:
        text = context.document.content
        lowered = text.lower()
        if len(_LIST_LINE.findall(text)) >= 2:
            key = "listicle"
        elif lowered.lstrip().startswith(_ANNOUNCEMENT):
            key = "announcement_details"
        elif any(marker in lowered for marker in ("the problem", "challenge")) and any(
            marker in lowered for marker in ("the solution", "we solved", "here's how")
        ):
            key = "problem_solution"
        elif any(marker in lowered for marker in ("i remember", "years ago", "when i")) and any(
            marker in lowered for marker in ("lesson", "learned", "takeaway")
        ):
            key = "story_lesson"
        elif "?" in _paragraphs(text)[0][2] and len(_paragraphs(text)) > 1:
            key = "question_answer"
        elif any(marker in lowered for marker in ("data", "evidence", "research", "%")):
            key = "claim_evidence"
        else:
            key = "linear_exposition"
        return (
            _measurement(
                NARRATIVE,
                key,
                key.replace("_", " ").title(),
                EvidenceUnit.DOCUMENT,
                0,
                len(text),
            ),
        )


class CTAExtractor(BaseExtractor):
    """Classify the functional close without retaining its wording."""

    extractor_id = "cta-extractor"
    features = (CTA,)

    def extract(self, context: ExtractionContext) -> tuple[PatternMeasurement, ...]:
        text = context.document.content
        start, end, closing = _paragraphs(text)[-1]
        lowered = closing.lower()
        if "?" in closing:
            key = "audience_question"
        elif any(item in lowered for item in ("read more", "learn more", "link", "details here")):
            key = "resource_direction"
        elif any(item in lowered for item in ("join us", "share your", "tell me", "let us know")):
            key = "community_invitation"
        elif re.search(r"\b(try|build|start|apply|download|register|follow)\b", lowered):
            key = "direct_action"
        else:
            key = "none"
        return (
            _measurement(CTA, key, key.replace("_", " ").title(), EvidenceUnit.CLOSING, start, end),
        )


class FormattingExtractor(BaseExtractor):
    """Classify dominant visual organization."""

    extractor_id = "formatting-extractor"
    features = (FORMATTING,)

    def extract(self, context: ExtractionContext) -> tuple[PatternMeasurement, ...]:
        text = context.document.content
        if len(_LIST_LINE.findall(text)) >= 2:
            key = "list_led"
        elif _HEADING_LINE.search(text):
            key = "heading_sectioned"
        elif text.count("\n\n") >= 3:
            key = "whitespace_broken"
        elif len(_paragraphs(text)) == 1 and len(_words(text)) > 80:
            key = "dense"
        else:
            key = "plain"
        return (
            _measurement(
                FORMATTING,
                key,
                key.replace("_", " ").title(),
                EvidenceUnit.DOCUMENT,
                0,
                len(text),
            ),
        )


class ThreadExtractor(BaseExtractor):
    """Classify declared thread length without source-specific branching."""

    extractor_id = "thread-extractor"
    features = (THREAD,)

    def extract(self, context: ExtractionContext) -> tuple[PatternMeasurement, ...]:
        text = context.document.content
        raw = context.document.metadata.get("thread_length", 1)
        length = raw if isinstance(raw, int) and raw > 0 else 1
        key = "single_post" if length == 1 else "short_thread" if length <= 5 else "long_thread"
        return (
            _measurement(
                THREAD,
                key,
                key.replace("_", " ").title(),
                EvidenceUnit.DOCUMENT,
                0,
                len(text),
            ),
        )


class AnnouncementExtractor(BaseExtractor):
    """Classify ordering only when a post is recognizably announcement-led."""

    extractor_id = "announcement-extractor"
    features = (ANNOUNCEMENT,)

    def extract(self, context: ExtractionContext) -> tuple[PatternMeasurement, ...]:
        text = context.document.content
        start, end, opening = _paragraphs(text)[0]
        lowered = opening.lower().strip()
        if not lowered.startswith(_ANNOUNCEMENT):
            return ()
        if any(marker in lowered for marker in ("available", "reached", "achieved", "%")):
            key = "outcome_first"
        elif any(marker in lowered for marker in ("after", "because", "for years", "over the")):
            key = "context_first"
        else:
            key = "details_first"
        return (
            _measurement(
                ANNOUNCEMENT,
                key,
                key.replace("_", " ").title(),
                EvidenceUnit.OPENING,
                start,
                end,
            ),
        )


def default_extractors() -> tuple[BaseExtractor, ...]:
    """Return the complete deterministic v1 extractor set."""

    return (
        AnnouncementExtractor(),
        CTAExtractor(),
        FormattingExtractor(),
        NarrativeExtractor(),
        OpeningExtractor(),
        RhythmExtractor(),
        ThreadExtractor(),
        TransitionExtractor(),
    )
