"""Deterministic distributional and rhetorical-position stylometry."""

import re
from collections import Counter
from collections.abc import Iterable
from math import sqrt
from typing import TypedDict

from pydantic import Field

from ceo_voice.analysis.contracts import (
    AddressedSpan,
    AnalyzerContext,
    AnalyzerSpecification,
    MeasurementCandidate,
)
from ceo_voice.analysis.enums import AnalyzerCategory, AnalyzerInput
from ceo_voice.models.base import ContractModel
from ceo_voice.voice.enums import MeasurementClass
from ceo_voice.voice.primitives import FeatureReference, SemanticVersion
from ceo_voice.voice.values import ScalarValue

_VERSION = SemanticVersion(major=1, minor=0, patch=0)
_WORD_PATTERN = re.compile(r"\b\w+(?:['\N{RIGHT SINGLE QUOTATION MARK}.-]\w+)*\b", re.UNICODE)
_FIRST_PERSON = frozenset(
    {"i", "i'm", "i've", "me", "my", "mine", "our", "ours", "us", "we", "we're", "we've"}
)
_SECOND_PERSON = frozenset({"you", "you're", "you've", "your", "yours"})


class DistributionalStylometryFeatures(ContractModel):
    """Bindings for document-balanced sentence and paragraph shape summaries."""

    sentence_p25_words: FeatureReference
    sentence_median_words: FeatureReference
    sentence_p75_words: FeatureReference
    sentence_length_stddev: FeatureReference
    short_sentence_ratio: FeatureReference
    long_sentence_ratio: FeatureReference
    paragraph_median_words: FeatureReference
    paragraph_length_stddev: FeatureReference
    single_sentence_paragraph_ratio: FeatureReference


class RhetoricalPositionFeatures(ContractModel):
    """Bindings for language-independent opening, closing, and question placement."""

    opening_sentence_words: FeatureReference
    opening_question_indicator: FeatureReference
    closing_question_indicator: FeatureReference
    question_position_mean: FeatureReference


class OpeningStanceFeatures(ContractModel):
    """Bindings for English first- and second-person opening stance."""

    opening_first_person_indicator: FeatureReference
    opening_second_person_indicator: FeatureReference


class StylometryAnalyzerConfig(ContractModel):
    """Versioned thresholds affecting deterministic stylometry measurements."""

    configuration_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    short_sentence_max_words: int = Field(default=5, ge=1)
    long_sentence_min_words: int = Field(default=20, ge=2)


class _CandidateArguments(TypedDict):
    spans: tuple[AddressedSpan, ...]
    fallback_span: AddressedSpan
    opportunities: int


class _CommonCandidateArguments(TypedDict):
    fallback_span: AddressedSpan
    opportunities: int


def _specification(
    *,
    analyzer_id: str,
    category: AnalyzerCategory,
    features: Iterable[FeatureReference],
    required_inputs: tuple[AnalyzerInput, ...],
    config: StylometryAnalyzerConfig,
    supported_languages: tuple[str, ...] = (),
) -> AnalyzerSpecification:
    return AnalyzerSpecification(
        analyzer_id=analyzer_id,
        version=_VERSION,
        category=category,
        supported_features=tuple(features),
        required_inputs=required_inputs,
        all_platforms=True,
        all_languages=not supported_languages,
        supported_languages=supported_languages,
        priority=110,
        measurement_class=MeasurementClass.DETERMINISTIC,
        configuration_hash=config.configuration_hash,
    )


def _feature_values(binding: ContractModel) -> tuple[FeatureReference, ...]:
    return tuple(value for _, value in binding if isinstance(value, FeatureReference))


def _candidate(
    feature: FeatureReference,
    value: float,
    unit: str,
    spans: tuple[AddressedSpan, ...],
    *,
    fallback_span: AddressedSpan,
    opportunities: int,
) -> MeasurementCandidate:
    evidence = (fallback_span.id, *(span.id for span in spans if span.id != fallback_span.id))
    return MeasurementCandidate(
        feature=feature,
        value=ScalarValue(value=value, unit=unit),
        evidence_span_ids=evidence,
        opportunity_count=opportunities,
    )


def _lengths(context: AnalyzerContext, spans: tuple[AddressedSpan, ...]) -> tuple[int, ...]:
    return tuple(
        len(_WORD_PATTERN.findall(context.analyzed_document.text_for(span))) for span in spans
    )


def _percentile(values: tuple[int, ...], quantile: float) -> float:
    """Return a linearly interpolated percentile with defined singleton behavior."""

    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _population_stddev(values: tuple[int, ...]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sqrt(sum((value - mean) ** 2 for value in values) / len(values))


class DistributionalStylometryAnalyzer:
    """Measure within-document length distributions without long-document dominance."""

    def __init__(
        self,
        *,
        features: DistributionalStylometryFeatures,
        config: StylometryAnalyzerConfig,
    ) -> None:
        if config.long_sentence_min_words <= config.short_sentence_max_words:
            raise ValueError("long sentence threshold must exceed short sentence threshold")
        self._features = features
        self._config = config
        self._specification = _specification(
            analyzer_id="tier1.distributional_stylometry",
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
        """Return document-level distribution summaries backed by structural spans."""

        analyzed = context.analyzed_document
        sentences = analyzed.sentences
        paragraphs = analyzed.paragraphs
        sentence_lengths = _lengths(context, sentences)
        paragraph_lengths = _lengths(context, paragraphs)
        sentence_count = len(sentence_lengths)
        paragraph_count = len(paragraph_lengths)
        sentences_by_paragraph = Counter(span.paragraph_id for span in sentences)
        single_sentence_paragraphs = sum(
            sentences_by_paragraph[paragraph.id] == 1 for paragraph in paragraphs
        )
        sentence_arguments: _CandidateArguments = {
            "spans": sentences,
            "fallback_span": analyzed.document_span,
            "opportunities": sentence_count,
        }
        paragraph_arguments: _CandidateArguments = {
            "spans": paragraphs,
            "fallback_span": analyzed.document_span,
            "opportunities": paragraph_count,
        }
        return (
            _candidate(
                self._features.sentence_p25_words,
                _percentile(sentence_lengths, 0.25),
                "words_per_sentence",
                **sentence_arguments,
            ),
            _candidate(
                self._features.sentence_median_words,
                _percentile(sentence_lengths, 0.5),
                "words_per_sentence",
                **sentence_arguments,
            ),
            _candidate(
                self._features.sentence_p75_words,
                _percentile(sentence_lengths, 0.75),
                "words_per_sentence",
                **sentence_arguments,
            ),
            _candidate(
                self._features.sentence_length_stddev,
                _population_stddev(sentence_lengths),
                "words_per_sentence",
                **sentence_arguments,
            ),
            _candidate(
                self._features.short_sentence_ratio,
                (
                    sum(
                        length <= self._config.short_sentence_max_words
                        for length in sentence_lengths
                    )
                    / sentence_count
                    if sentence_count
                    else 0.0
                ),
                "ratio",
                **sentence_arguments,
            ),
            _candidate(
                self._features.long_sentence_ratio,
                (
                    sum(
                        length >= self._config.long_sentence_min_words
                        for length in sentence_lengths
                    )
                    / sentence_count
                    if sentence_count
                    else 0.0
                ),
                "ratio",
                **sentence_arguments,
            ),
            _candidate(
                self._features.paragraph_median_words,
                _percentile(paragraph_lengths, 0.5),
                "words_per_paragraph",
                **paragraph_arguments,
            ),
            _candidate(
                self._features.paragraph_length_stddev,
                _population_stddev(paragraph_lengths),
                "words_per_paragraph",
                **paragraph_arguments,
            ),
            _candidate(
                self._features.single_sentence_paragraph_ratio,
                single_sentence_paragraphs / paragraph_count if paragraph_count else 0.0,
                "ratio",
                **paragraph_arguments,
            ),
        )


class RhetoricalPositionAnalyzer:
    """Measure where visible questions and opener/closer forms appear in a document."""

    def __init__(
        self,
        *,
        features: RhetoricalPositionFeatures,
        config: StylometryAnalyzerConfig,
    ) -> None:
        self._features = features
        self._specification = _specification(
            analyzer_id="tier1.rhetorical_position",
            category=AnalyzerCategory.RHETORICAL,
            features=_feature_values(features),
            required_inputs=(AnalyzerInput.DOCUMENT, AnalyzerInput.SENTENCES),
            config=config,
        )

    @property
    def specification(self) -> AnalyzerSpecification:
        """Return exact analyzer capabilities."""

        return self._specification

    async def analyze(self, context: AnalyzerContext) -> tuple[MeasurementCandidate, ...]:
        """Return deterministic opener shape and normalized question placement."""

        analyzed = context.analyzed_document
        sentences = analyzed.sentences
        opening = sentences[0] if sentences else analyzed.document_span
        closing = sentences[-1] if sentences else analyzed.document_span
        opening_text = analyzed.text_for(opening)
        closing_text = analyzed.text_for(closing)
        opening_words = _opening_words(opening_text)
        question_spans = tuple(span for span in sentences if "?" in analyzed.text_for(span))
        denominator = max(len(sentences) - 1, 1)
        mean_question_position = (
            sum(span.ordinal / denominator for span in question_spans) / len(question_spans)
            if question_spans
            else 0.0
        )
        opening_evidence = (opening,)
        closing_evidence = (closing,)
        question_evidence = question_spans or sentences
        common: _CommonCandidateArguments = {
            "fallback_span": analyzed.document_span,
            "opportunities": 1,
        }
        return (
            _candidate(
                self._features.opening_sentence_words,
                len(opening_words),
                "words",
                opening_evidence,
                **common,
            ),
            _candidate(
                self._features.opening_question_indicator,
                float("?" in opening_text),
                "binary",
                opening_evidence,
                **common,
            ),
            _candidate(
                self._features.closing_question_indicator,
                float("?" in closing_text),
                "binary",
                closing_evidence,
                **common,
            ),
            _candidate(
                self._features.question_position_mean,
                mean_question_position,
                "normalized_position",
                question_evidence,
                fallback_span=analyzed.document_span,
                opportunities=len(sentences),
            ),
        )


def _opening_words(text: str) -> tuple[str, ...]:
    return tuple(
        word.casefold().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
        for word in _WORD_PATTERN.findall(text)
    )


class OpeningStanceAnalyzer:
    """Measure explicit English audience and author stance in the opening sentence."""

    def __init__(
        self,
        *,
        features: OpeningStanceFeatures,
        config: StylometryAnalyzerConfig,
    ) -> None:
        self._features = features
        self._specification = _specification(
            analyzer_id="tier1.opening_stance_en",
            category=AnalyzerCategory.RHETORICAL,
            features=_feature_values(features),
            required_inputs=(AnalyzerInput.DOCUMENT, AnalyzerInput.SENTENCES),
            config=config,
            supported_languages=("en",),
        )

    @property
    def specification(self) -> AnalyzerSpecification:
        """Return English-only analyzer capabilities."""

        return self._specification

    async def analyze(self, context: AnalyzerContext) -> tuple[MeasurementCandidate, ...]:
        """Return explicit opening pronoun indicators without semantic inference."""

        analyzed = context.analyzed_document
        opening = analyzed.sentences[0] if analyzed.sentences else analyzed.document_span
        opening_words = _opening_words(analyzed.text_for(opening))
        arguments: _CandidateArguments = {
            "spans": (opening,),
            "fallback_span": analyzed.document_span,
            "opportunities": 1,
        }
        return (
            _candidate(
                self._features.opening_first_person_indicator,
                float(bool(_FIRST_PERSON.intersection(opening_words))),
                "binary",
                **arguments,
            ),
            _candidate(
                self._features.opening_second_person_indicator,
                float(bool(_SECOND_PERSON.intersection(opening_words))),
                "binary",
                **arguments,
            ),
        )
