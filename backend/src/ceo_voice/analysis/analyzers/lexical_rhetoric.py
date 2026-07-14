"""English lexical, discourse, repetition, and rhetorical-marker analyzers."""

import re
from collections import Counter
from collections.abc import Iterable

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

_VERSION = SemanticVersion.parse("1.0.0")
_WORD_PATTERN = re.compile(r"\b\w+(?:['\N{RIGHT SINGLE QUOTATION MARK}.-]\w+)*\b", re.UNICODE)
_NUMERIC_OPENING = re.compile(r"^\s*(?:[#*_-]\s*)?\d", re.UNICODE)
_FUNCTION_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "because",
        "but",
        "by",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "hers",
        "him",
        "his",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "ours",
        "she",
        "so",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "they",
        "this",
        "to",
        "us",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
        "yours",
    }
)
_FIRST_PERSON_PLURAL = frozenset({"we", "we're", "we've", "we'll", "us", "our", "ours"})
_SECOND_PERSON = frozenset({"you", "you're", "you've", "you'll", "your", "yours"})
_HEDGE_MARKERS = (
    ("apparently",),
    ("could",),
    ("i", "think"),
    ("may",),
    ("might",),
    ("perhaps",),
    ("possibly",),
    ("seems",),
    ("we", "believe"),
    ("we", "think"),
)
_CERTAINTY_MARKERS = (
    ("always",),
    ("certainly",),
    ("clearly",),
    ("definitely",),
    ("must",),
    ("never",),
    ("will",),
    ("without", "doubt"),
)
_CONTRAST_MARKERS = (
    ("although",),
    ("but",),
    ("however",),
    ("instead",),
    ("on", "the", "other", "hand"),
    ("while",),
    ("yet",),
)
_CAUSAL_MARKERS = (
    ("as", "a", "result"),
    ("because",),
    ("so",),
    ("therefore",),
    ("thus",),
    ("which", "means"),
)
_ADDITIVE_MARKERS = (
    ("also",),
    ("and",),
    ("finally",),
    ("first",),
    ("furthermore",),
    ("in", "addition"),
    ("moreover",),
    ("second",),
)
_ANNOUNCEMENT_MARKERS = (
    ("announcing",),
    ("excited", "to"),
    ("introducing",),
    ("today",),
    ("we", "are", "launching"),
    ("we're", "launching"),
)
_CTA_MARKERS = (
    ("check", "out"),
    ("join", "us"),
    ("learn", "more"),
    ("let", "me", "know"),
    ("read", "more"),
    ("share", "your"),
    ("sign", "up"),
    ("tell", "us"),
    ("try", "it"),
)


class EnglishLexicalSignatureFeatures(ContractModel):
    """Bindings for English token-choice and stance-marker measurements."""

    function_word_ratio: FeatureReference
    moving_average_type_token_ratio: FeatureReference
    apostrophized_word_ratio: FeatureReference
    first_person_plural_ratio: FeatureReference
    second_person_pronoun_ratio: FeatureReference
    hedge_marker_rate: FeatureReference
    certainty_marker_rate: FeatureReference


class EnglishDiscourseMarkerFeatures(ContractModel):
    """Bindings for sentence-initial English transition behavior."""

    transition_sentence_ratio: FeatureReference
    contrast_transition_ratio: FeatureReference
    causal_transition_ratio: FeatureReference
    additive_transition_ratio: FeatureReference


class RepetitionSignatureFeatures(ContractModel):
    """Bindings for token and sentence-opening phrase reuse."""

    repeated_sentence_opening_ratio: FeatureReference
    repeated_bigram_ratio: FeatureReference
    repeated_trigram_ratio: FeatureReference


class EnglishRhetoricalMarkerFeatures(ContractModel):
    """Bindings for visible English opener and closing CTA markers."""

    numeric_opening_indicator: FeatureReference
    announcement_opening_indicator: FeatureReference
    closing_cta_marker_indicator: FeatureReference


class LexicalRhetoricConfig(ContractModel):
    """Versioned token-window settings for lexical and repetition analyzers."""

    configuration_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    mattr_window_words: int = Field(default=50, ge=5, le=500)
    sentence_opening_words: int = Field(default=2, ge=1, le=10)


def _specification(
    analyzer_id: str,
    category: AnalyzerCategory,
    features: Iterable[FeatureReference],
    inputs: tuple[AnalyzerInput, ...],
    config: LexicalRhetoricConfig,
) -> AnalyzerSpecification:
    return AnalyzerSpecification(
        analyzer_id=analyzer_id,
        version=_VERSION,
        category=category,
        supported_features=tuple(features),
        required_inputs=inputs,
        all_platforms=True,
        all_languages=False,
        supported_languages=("en",),
        priority=120,
        measurement_class=MeasurementClass.DETERMINISTIC,
        configuration_hash=config.configuration_hash,
    )


def _feature_values(binding: ContractModel) -> tuple[FeatureReference, ...]:
    return tuple(value for _, value in binding if isinstance(value, FeatureReference))


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(
        token.casefold().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'")
        for token in _WORD_PATTERN.findall(text)
    )


def _candidate(
    feature: FeatureReference,
    value: float,
    unit: str,
    document_span: AddressedSpan,
    spans: tuple[AddressedSpan, ...],
    opportunities: int,
) -> MeasurementCandidate:
    evidence = (document_span.id, *(span.id for span in spans if span.id != document_span.id))
    return MeasurementCandidate(
        feature=feature,
        value=ScalarValue(value=value, unit=unit),
        evidence_span_ids=evidence,
        opportunity_count=opportunities,
    )


def _phrase_count(tokens: tuple[str, ...], phrases: tuple[tuple[str, ...], ...]) -> int:
    return sum(
        tuple(tokens[index : index + len(phrase)]) == phrase
        for phrase in phrases
        for index in range(len(tokens) - len(phrase) + 1)
    )


def _starts_with(tokens: tuple[str, ...], phrases: tuple[tuple[str, ...], ...]) -> bool:
    return any(tokens[: len(phrase)] == phrase for phrase in phrases)


def _mattr(tokens: tuple[str, ...], window: int) -> float:
    if not tokens:
        return 0.0
    selected_window = min(len(tokens), window)
    scores = tuple(
        len(set(tokens[start : start + selected_window])) / selected_window
        for start in range(len(tokens) - selected_window + 1)
    )
    return sum(scores) / len(scores)


def _repeated_ngram_ratio(tokens: tuple[str, ...], size: int) -> float:
    opportunities = len(tokens) - size + 1
    if opportunities <= 0:
        return 0.0
    counts = Counter(tuple(tokens[index : index + size]) for index in range(opportunities))
    repeated = sum(count - 1 for count in counts.values())
    return repeated / opportunities


class EnglishLexicalSignatureAnalyzer:
    """Measure English token-choice signatures without assigning psychological tone."""

    def __init__(
        self,
        *,
        features: EnglishLexicalSignatureFeatures,
        config: LexicalRhetoricConfig,
    ) -> None:
        self._features = features
        self._config = config
        self._specification = _specification(
            "tier1.lexical_signature_en",
            AnalyzerCategory.LEXICAL,
            _feature_values(features),
            (AnalyzerInput.DOCUMENT,),
            config,
        )

    @property
    def specification(self) -> AnalyzerSpecification:
        return self._specification

    async def analyze(self, context: AnalyzerContext) -> tuple[MeasurementCandidate, ...]:
        analyzed = context.analyzed_document
        tokens = _tokens(analyzed.document.content)
        count = len(tokens)
        denominator = count or 1
        arguments = (analyzed.document_span, (), count)
        return (
            _candidate(
                self._features.function_word_ratio,
                sum(token in _FUNCTION_WORDS for token in tokens) / denominator,
                "ratio",
                *arguments,
            ),
            _candidate(
                self._features.moving_average_type_token_ratio,
                _mattr(tokens, self._config.mattr_window_words),
                "ratio",
                *arguments,
            ),
            _candidate(
                self._features.apostrophized_word_ratio,
                sum("'" in token for token in tokens) / denominator,
                "ratio",
                *arguments,
            ),
            _candidate(
                self._features.first_person_plural_ratio,
                sum(token in _FIRST_PERSON_PLURAL for token in tokens) / denominator,
                "ratio",
                *arguments,
            ),
            _candidate(
                self._features.second_person_pronoun_ratio,
                sum(token in _SECOND_PERSON for token in tokens) / denominator,
                "ratio",
                *arguments,
            ),
            _candidate(
                self._features.hedge_marker_rate,
                _phrase_count(tokens, _HEDGE_MARKERS) * 100 / denominator,
                "markers_per_100_words",
                *arguments,
            ),
            _candidate(
                self._features.certainty_marker_rate,
                _phrase_count(tokens, _CERTAINTY_MARKERS) * 100 / denominator,
                "markers_per_100_words",
                *arguments,
            ),
        )


class EnglishDiscourseMarkerAnalyzer:
    """Measure explicit sentence-initial English transition families."""

    def __init__(
        self,
        *,
        features: EnglishDiscourseMarkerFeatures,
        config: LexicalRhetoricConfig,
    ) -> None:
        self._features = features
        self._specification = _specification(
            "tier1.discourse_markers_en",
            AnalyzerCategory.RHETORICAL,
            _feature_values(features),
            (AnalyzerInput.DOCUMENT, AnalyzerInput.SENTENCES),
            config,
        )

    @property
    def specification(self) -> AnalyzerSpecification:
        return self._specification

    async def analyze(self, context: AnalyzerContext) -> tuple[MeasurementCandidate, ...]:
        analyzed = context.analyzed_document
        sentences = analyzed.sentences
        tokenized = tuple(_tokens(analyzed.text_for(span)) for span in sentences)
        denominator = len(sentences) or 1
        categories = (_CONTRAST_MARKERS, _CAUSAL_MARKERS, _ADDITIVE_MARKERS)
        values = tuple(
            sum(_starts_with(tokens, markers) for tokens in tokenized) / denominator
            for markers in categories
        )
        transition = (
            sum(
                any(_starts_with(tokens, markers) for markers in categories) for tokens in tokenized
            )
            / denominator
        )
        arguments = (analyzed.document_span, sentences, len(sentences))
        return (
            _candidate(
                self._features.transition_sentence_ratio,
                transition,
                "ratio",
                *arguments,
            ),
            _candidate(
                self._features.contrast_transition_ratio,
                values[0],
                "ratio",
                *arguments,
            ),
            _candidate(
                self._features.causal_transition_ratio,
                values[1],
                "ratio",
                *arguments,
            ),
            _candidate(
                self._features.additive_transition_ratio,
                values[2],
                "ratio",
                *arguments,
            ),
        )


class RepetitionSignatureAnalyzer:
    """Measure English token and sentence-opening repetition patterns."""

    def __init__(
        self,
        *,
        features: RepetitionSignatureFeatures,
        config: LexicalRhetoricConfig,
    ) -> None:
        self._features = features
        self._config = config
        self._specification = _specification(
            "tier1.repetition_signature_en",
            AnalyzerCategory.RHETORICAL,
            _feature_values(features),
            (AnalyzerInput.DOCUMENT, AnalyzerInput.SENTENCES),
            config,
        )

    @property
    def specification(self) -> AnalyzerSpecification:
        return self._specification

    async def analyze(self, context: AnalyzerContext) -> tuple[MeasurementCandidate, ...]:
        analyzed = context.analyzed_document
        tokens = _tokens(analyzed.document.content)
        openings = tuple(
            sentence_tokens[: self._config.sentence_opening_words]
            for span in analyzed.sentences
            if (sentence_tokens := _tokens(analyzed.text_for(span)))
        )
        opening_counts = Counter(openings)
        repeated_openings = sum(opening_counts[item] > 1 for item in openings)
        opening_ratio = repeated_openings / len(openings) if openings else 0.0
        return (
            _candidate(
                self._features.repeated_sentence_opening_ratio,
                opening_ratio,
                "ratio",
                analyzed.document_span,
                analyzed.sentences,
                len(openings),
            ),
            _candidate(
                self._features.repeated_bigram_ratio,
                _repeated_ngram_ratio(tokens, 2),
                "ratio",
                analyzed.document_span,
                analyzed.sentences,
                max(len(tokens) - 1, 0),
            ),
            _candidate(
                self._features.repeated_trigram_ratio,
                _repeated_ngram_ratio(tokens, 3),
                "ratio",
                analyzed.document_span,
                analyzed.sentences,
                max(len(tokens) - 2, 0),
            ),
        )


class EnglishRhetoricalMarkerAnalyzer:
    """Measure visible English announcement and CTA phrase markers."""

    def __init__(
        self,
        *,
        features: EnglishRhetoricalMarkerFeatures,
        config: LexicalRhetoricConfig,
    ) -> None:
        self._features = features
        self._specification = _specification(
            "tier1.rhetorical_markers_en",
            AnalyzerCategory.RHETORICAL,
            _feature_values(features),
            (AnalyzerInput.DOCUMENT, AnalyzerInput.SENTENCES),
            config,
        )

    @property
    def specification(self) -> AnalyzerSpecification:
        return self._specification

    async def analyze(self, context: AnalyzerContext) -> tuple[MeasurementCandidate, ...]:
        analyzed = context.analyzed_document
        opening = analyzed.sentences[0] if analyzed.sentences else analyzed.document_span
        closing = analyzed.sentences[-1] if analyzed.sentences else analyzed.document_span
        opening_text = analyzed.text_for(opening)
        opening_tokens = _tokens(opening_text)
        closing_tokens = _tokens(analyzed.text_for(closing))
        return (
            _candidate(
                self._features.numeric_opening_indicator,
                float(bool(_NUMERIC_OPENING.match(opening_text))),
                "binary",
                analyzed.document_span,
                (opening,),
                1,
            ),
            _candidate(
                self._features.announcement_opening_indicator,
                float(_starts_with(opening_tokens, _ANNOUNCEMENT_MARKERS)),
                "binary",
                analyzed.document_span,
                (opening,),
                1,
            ),
            _candidate(
                self._features.closing_cta_marker_indicator,
                float(_phrase_count(closing_tokens, _CTA_MARKERS) > 0),
                "binary",
                analyzed.document_span,
                (closing,),
                1,
            ),
        )
