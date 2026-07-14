"""Tier 1 exact analyzers using only deterministic standard-library rules."""

import re
import unicodedata
from collections.abc import Iterable
from uuid import UUID

from pydantic import Field

from ceo_voice.analysis.contracts import (
    AnalyzerContext,
    AnalyzerSpecification,
    MeasurementCandidate,
)
from ceo_voice.analysis.enums import AnalyzerCategory, AnalyzerInput
from ceo_voice.models.base import ContractModel, NonEmptyStr
from ceo_voice.voice.enums import MeasurementClass, ObservationState
from ceo_voice.voice.primitives import FeatureReference, SemanticVersion
from ceo_voice.voice.values import ScalarValue

_VERSION = SemanticVersion(major=1, minor=0, patch=0)
_WORD_PATTERN = re.compile(r"\b\w+(?:['\N{RIGHT SINGLE QUOTATION MARK}.-]\w+)*\b", re.UNICODE)
_LINK_PATTERN = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_HASHTAG_PATTERN = re.compile(r"(?<!\w)#[\w]+", re.UNICODE)
_MENTION_PATTERN = re.compile(r"(?<!\w)@[\w]+", re.UNICODE)
_LIST_PATTERN = re.compile(r"^[ \t]*(?:[-*+] |\d+[.)] )", re.MULTILINE)
_HEADING_PATTERN = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+\S", re.MULTILINE)
_REPEATED_WHITESPACE_PATTERN = re.compile(r"(?<!\n)[ \t]{2,}")
_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2300, 0x23FF),
)


class DocumentStatisticsFeatures(ContractModel):
    """Registry bindings for exact document-size measurements."""

    character_count: FeatureReference
    word_count: FeatureReference
    reading_time: FeatureReference
    document_length: FeatureReference
    thread_length: FeatureReference


class StructuralFeatures(ContractModel):
    """Registry bindings for deterministic document-structure measurements."""

    sentence_count: FeatureReference
    mean_sentence_words: FeatureReference
    paragraph_count: FeatureReference
    mean_paragraph_words: FeatureReference
    line_break_count: FeatureReference
    list_item_count: FeatureReference
    heading_count: FeatureReference


class SymbolUsageFeatures(ContractModel):
    """Registry bindings for deterministic symbol and marker measurements."""

    emoji_count: FeatureReference
    punctuation_count: FeatureReference
    question_frequency: FeatureReference
    exclamation_frequency: FeatureReference
    link_count: FeatureReference
    hashtag_count: FeatureReference
    mention_count: FeatureReference


class FormattingFeatures(ContractModel):
    """Registry bindings for deterministic capitalization and whitespace measurements."""

    capitalization_ratio: FeatureReference
    uppercase_word_ratio: FeatureReference
    blank_line_count: FeatureReference
    repeated_whitespace_count: FeatureReference


class DeterministicAnalyzerConfig(ContractModel):
    """Common behavior-affecting configuration for Tier 1 analyzers."""

    configuration_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    reading_words_per_minute: int = Field(default=200, ge=1)
    thread_length_metadata_field: NonEmptyStr = Field(default="thread_length")


def _specification(
    *,
    analyzer_id: str,
    category: AnalyzerCategory,
    features: Iterable[FeatureReference],
    required_inputs: tuple[AnalyzerInput, ...],
    config: DeterministicAnalyzerConfig,
) -> AnalyzerSpecification:
    return AnalyzerSpecification(
        analyzer_id=analyzer_id,
        version=_VERSION,
        category=category,
        supported_features=tuple(features),
        required_inputs=required_inputs,
        all_platforms=True,
        all_languages=True,
        priority=100,
        measurement_class=MeasurementClass.DETERMINISTIC,
        configuration_hash=config.configuration_hash,
    )


def _feature_values(binding: ContractModel) -> tuple[FeatureReference, ...]:
    return tuple(value for _, value in binding if isinstance(value, FeatureReference))


def _all_evidence(context: AnalyzerContext) -> tuple[UUID, ...]:
    document = context.analyzed_document
    return tuple(
        span.id for span in (document.document_span, *document.paragraphs, *document.sentences)
    )


def _candidate(
    feature: FeatureReference,
    value: float,
    unit: str,
    context: AnalyzerContext,
    *,
    opportunities: int,
) -> MeasurementCandidate:
    return MeasurementCandidate(
        feature=feature,
        value=ScalarValue(value=value, unit=unit),
        evidence_span_ids=_all_evidence(context),
        opportunity_count=opportunities,
    )


class DocumentStatisticsAnalyzer:
    """Measure exact character, word, reading-time, and declared thread dimensions."""

    def __init__(
        self, *, features: DocumentStatisticsFeatures, config: DeterministicAnalyzerConfig
    ) -> None:
        self._features = features
        self._config = config
        self._specification = _specification(
            analyzer_id="tier1.document_statistics",
            category=AnalyzerCategory.STRUCTURAL,
            features=_feature_values(features),
            required_inputs=(AnalyzerInput.DOCUMENT,),
            config=config,
        )

    @property
    def specification(self) -> AnalyzerSpecification:
        """Return exact analyzer capabilities."""

        return self._specification

    async def analyze(self, context: AnalyzerContext) -> tuple[MeasurementCandidate, ...]:
        """Return exact counts and a configured deterministic reading-time estimate."""

        content = context.request.document.content
        words = _WORD_PATTERN.findall(content)
        word_count = len(words)
        evidence_ids = _all_evidence(context)
        thread_value = context.request.document.metadata.get(
            self._config.thread_length_metadata_field
        )
        thread_candidate = (
            _candidate(
                self._features.thread_length,
                float(thread_value),
                "posts",
                context,
                opportunities=1,
            )
            if isinstance(thread_value, int)
            and not isinstance(thread_value, bool)
            and thread_value > 0
            else MeasurementCandidate(
                feature=self._features.thread_length,
                state=ObservationState.MISSING,
                value=None,
                evidence_span_ids=evidence_ids,
                opportunity_count=1,
            )
        )
        return (
            _candidate(
                self._features.character_count,
                float(len(content)),
                "unicode_characters",
                context,
                opportunities=len(content),
            ),
            _candidate(
                self._features.word_count,
                float(word_count),
                "words",
                context,
                opportunities=word_count,
            ),
            _candidate(
                self._features.reading_time,
                word_count * 60.0 / self._config.reading_words_per_minute,
                "seconds",
                context,
                opportunities=word_count,
            ),
            _candidate(
                self._features.document_length,
                float(len(content)),
                "unicode_characters",
                context,
                opportunities=len(content),
            ),
            thread_candidate,
        )


class StructuralAnalyzer:
    """Measure sentence, paragraph, line-break, list, and heading structure."""

    def __init__(
        self, *, features: StructuralFeatures, config: DeterministicAnalyzerConfig
    ) -> None:
        self._features = features
        self._specification = _specification(
            analyzer_id="tier1.structural",
            category=AnalyzerCategory.STRUCTURAL,
            features=_feature_values(features),
            required_inputs=(
                AnalyzerInput.DOCUMENT,
                AnalyzerInput.PARAGRAPHS,
                AnalyzerInput.SENTENCES,
            ),
            config=config,
        )

    @property
    def specification(self) -> AnalyzerSpecification:
        """Return exact analyzer capabilities."""

        return self._specification

    async def analyze(self, context: AnalyzerContext) -> tuple[MeasurementCandidate, ...]:
        """Return structural counts and arithmetic mean lengths."""

        analyzed = context.analyzed_document
        content = analyzed.document.content
        sentence_lengths = tuple(
            len(_WORD_PATTERN.findall(analyzed.text_for(span))) for span in analyzed.sentences
        )
        paragraph_lengths = tuple(
            len(_WORD_PATTERN.findall(analyzed.text_for(span))) for span in analyzed.paragraphs
        )
        sentence_count = len(sentence_lengths)
        paragraph_count = len(paragraph_lengths)
        return (
            _candidate(
                self._features.sentence_count,
                sentence_count,
                "sentences",
                context,
                opportunities=sentence_count,
            ),
            _candidate(
                self._features.mean_sentence_words,
                sum(sentence_lengths) / sentence_count if sentence_count else 0.0,
                "words_per_sentence",
                context,
                opportunities=sentence_count,
            ),
            _candidate(
                self._features.paragraph_count,
                paragraph_count,
                "paragraphs",
                context,
                opportunities=paragraph_count,
            ),
            _candidate(
                self._features.mean_paragraph_words,
                sum(paragraph_lengths) / paragraph_count if paragraph_count else 0.0,
                "words_per_paragraph",
                context,
                opportunities=paragraph_count,
            ),
            _candidate(
                self._features.line_break_count,
                content.count("\n"),
                "line_breaks",
                context,
                opportunities=max(len(analyzed.lines) - 1, 0),
            ),
            _candidate(
                self._features.list_item_count,
                len(_LIST_PATTERN.findall(content)),
                "list_items",
                context,
                opportunities=len(analyzed.lines),
            ),
            _candidate(
                self._features.heading_count,
                len(_HEADING_PATTERN.findall(content)),
                "headings",
                context,
                opportunities=len(analyzed.lines),
            ),
        )


class SymbolUsageAnalyzer:
    """Measure visible punctuation, emoji, links, hashtags, and mentions."""

    def __init__(
        self, *, features: SymbolUsageFeatures, config: DeterministicAnalyzerConfig
    ) -> None:
        self._features = features
        self._specification = _specification(
            analyzer_id="tier1.symbol_usage",
            category=AnalyzerCategory.FORMATTING,
            features=_feature_values(features),
            required_inputs=(AnalyzerInput.DOCUMENT, AnalyzerInput.SENTENCES),
            config=config,
        )

    @property
    def specification(self) -> AnalyzerSpecification:
        """Return exact analyzer capabilities."""

        return self._specification

    async def analyze(self, context: AnalyzerContext) -> tuple[MeasurementCandidate, ...]:
        """Return exact standard-library symbol counts and per-sentence frequencies."""

        content = context.request.document.content
        sentence_count = len(context.analyzed_document.sentences)
        denominator = sentence_count or 1
        emoji_count = sum(
            any(start <= ord(character) <= end for start, end in _EMOJI_RANGES)
            for character in content
        )
        punctuation_count = sum(
            unicodedata.category(character).startswith("P") for character in content
        )
        return (
            _candidate(
                self._features.emoji_count,
                emoji_count,
                "emoji_codepoints",
                context,
                opportunities=len(content),
            ),
            _candidate(
                self._features.punctuation_count,
                punctuation_count,
                "punctuation_characters",
                context,
                opportunities=len(content),
            ),
            _candidate(
                self._features.question_frequency,
                content.count("?") / denominator,
                "marks_per_sentence",
                context,
                opportunities=sentence_count,
            ),
            _candidate(
                self._features.exclamation_frequency,
                content.count("!") / denominator,
                "marks_per_sentence",
                context,
                opportunities=sentence_count,
            ),
            _candidate(
                self._features.link_count,
                len(_LINK_PATTERN.findall(content)),
                "links",
                context,
                opportunities=len(content),
            ),
            _candidate(
                self._features.hashtag_count,
                len(_HASHTAG_PATTERN.findall(content)),
                "hashtags",
                context,
                opportunities=len(content),
            ),
            _candidate(
                self._features.mention_count,
                len(_MENTION_PATTERN.findall(content)),
                "mentions",
                context,
                opportunities=len(content),
            ),
        )


class FormattingAnalyzer:
    """Measure capitalization and whitespace behaviors without changing source text."""

    def __init__(
        self, *, features: FormattingFeatures, config: DeterministicAnalyzerConfig
    ) -> None:
        self._features = features
        self._specification = _specification(
            analyzer_id="tier1.formatting",
            category=AnalyzerCategory.FORMATTING,
            features=_feature_values(features),
            required_inputs=(AnalyzerInput.DOCUMENT, AnalyzerInput.LINES),
            config=config,
        )

    @property
    def specification(self) -> AnalyzerSpecification:
        """Return exact analyzer capabilities."""

        return self._specification

    async def analyze(self, context: AnalyzerContext) -> tuple[MeasurementCandidate, ...]:
        """Return casing ratios and explicit blank/repeated-whitespace counts."""

        content = context.request.document.content
        cased_characters = tuple(character for character in content if character.isalpha())
        words = _WORD_PATTERN.findall(content)
        cased_words = tuple(
            word for word in words if any(character.isalpha() for character in word)
        )
        uppercase_words = sum(
            word.isupper() and any(character.isalpha() for character in word)
            for word in cased_words
        )
        blank_lines = sum(not line.strip() for line in content.splitlines())
        return (
            _candidate(
                self._features.capitalization_ratio,
                (
                    sum(character.isupper() for character in cased_characters)
                    / len(cased_characters)
                    if cased_characters
                    else 0.0
                ),
                "ratio",
                context,
                opportunities=len(cased_characters),
            ),
            _candidate(
                self._features.uppercase_word_ratio,
                uppercase_words / len(cased_words) if cased_words else 0.0,
                "ratio",
                context,
                opportunities=len(cased_words),
            ),
            _candidate(
                self._features.blank_line_count,
                blank_lines,
                "blank_lines",
                context,
                opportunities=len(content.splitlines()),
            ),
            _candidate(
                self._features.repeated_whitespace_count,
                len(_REPEATED_WHITESPACE_PATTERN.findall(content)),
                "runs",
                context,
                opportunities=len(content),
            ),
        )
