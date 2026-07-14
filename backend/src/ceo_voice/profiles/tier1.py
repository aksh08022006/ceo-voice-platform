"""Versioned default Tier 1 feature catalog and analyzer composition."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from ceo_voice.analysis import (
    Analyzer,
    DeterministicAnalyzerConfig,
    DistributionalStylometryAnalyzer,
    DistributionalStylometryFeatures,
    DocumentStatisticsAnalyzer,
    DocumentStatisticsFeatures,
    FormattingAnalyzer,
    FormattingFeatures,
    OpeningStanceAnalyzer,
    OpeningStanceFeatures,
    RhetoricalPositionAnalyzer,
    RhetoricalPositionFeatures,
    StructuralAnalyzer,
    StructuralFeatures,
    StylometryAnalyzerConfig,
    SymbolUsageAnalyzer,
    SymbolUsageFeatures,
)
from ceo_voice.profiles.contracts import (
    ScalarBaselineSnapshot,
    ScalarFeatureBaseline,
)
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.voice import (
    AggregationStrategyReference,
    BaselineReference,
    ConfidenceComponent,
    ConfidenceModelDefinition,
    DownstreamPermission,
    EvidenceRequirements,
    EvidenceRole,
    EvidenceUnitType,
    FeatureDefinition,
    FeatureRegistry,
    FeatureValueType,
    LanguageApplicability,
    MeasurementClass,
    PlatformApplicability,
    ScalarValue,
    SemanticVersion,
    SourceModality,
    VoiceDimension,
)

_FEATURE_VERSION = SemanticVersion.parse("1.0.0")
_REGISTRY_VERSION = SemanticVersion.parse("1.1.0")
_CREATED_AT = datetime(2026, 1, 1, tzinfo=UTC)
_REGISTRY_ID = uuid5(NAMESPACE_URL, "ceo-voice:tier1-feature-registry")
_BASELINE_ID = uuid5(NAMESPACE_URL, "ceo-voice:descriptive-zero-baseline")


@dataclass(frozen=True, slots=True)
class _Declaration:
    binding: str
    feature_id: str
    display_name: str
    dimension: VoiceDimension
    unit: str
    opportunity: str
    supported_languages: tuple[str, ...] = ()


_DECLARATIONS = (
    _Declaration(
        "character_count",
        "analysis.character-count",
        "Character count",
        VoiceDimension.ORTHOGRAPHIC,
        "unicode_characters",
        "unicode character",
    ),
    _Declaration(
        "word_count", "analysis.word-count", "Word count", VoiceDimension.LEXICAL, "words", "word"
    ),
    _Declaration(
        "reading_time",
        "analysis.reading-time",
        "Estimated reading time",
        VoiceDimension.RHYTHMIC,
        "seconds",
        "word",
    ),
    _Declaration(
        "document_length",
        "analysis.document-length",
        "Document length",
        VoiceDimension.LAYOUT,
        "unicode_characters",
        "unicode character",
    ),
    _Declaration(
        "thread_length",
        "analysis.thread-length",
        "Declared thread length",
        VoiceDimension.PLATFORM_ADAPTATION,
        "posts",
        "document",
    ),
    _Declaration(
        "sentence_count",
        "analysis.sentence-count",
        "Sentence count",
        VoiceDimension.RHYTHMIC,
        "sentences",
        "sentence",
    ),
    _Declaration(
        "mean_sentence_words",
        "analysis.mean-sentence-words",
        "Mean sentence length",
        VoiceDimension.RHYTHMIC,
        "words_per_sentence",
        "sentence",
    ),
    _Declaration(
        "paragraph_count",
        "analysis.paragraph-count",
        "Paragraph count",
        VoiceDimension.LAYOUT,
        "paragraphs",
        "paragraph",
    ),
    _Declaration(
        "mean_paragraph_words",
        "analysis.mean-paragraph-words",
        "Mean paragraph length",
        VoiceDimension.LAYOUT,
        "words_per_paragraph",
        "paragraph",
    ),
    _Declaration(
        "line_break_count",
        "analysis.line-break-count",
        "Line break count",
        VoiceDimension.LAYOUT,
        "line_breaks",
        "line",
    ),
    _Declaration(
        "list_item_count",
        "analysis.list-item-count",
        "List item count",
        VoiceDimension.LAYOUT,
        "list_items",
        "line",
    ),
    _Declaration(
        "heading_count",
        "analysis.heading-count",
        "Heading count",
        VoiceDimension.LAYOUT,
        "headings",
        "line",
    ),
    _Declaration(
        "emoji_count",
        "analysis.emoji-count",
        "Emoji code-point count",
        VoiceDimension.ORTHOGRAPHIC,
        "emoji_codepoints",
        "unicode character",
    ),
    _Declaration(
        "punctuation_count",
        "analysis.punctuation-count",
        "Punctuation count",
        VoiceDimension.ORTHOGRAPHIC,
        "punctuation_characters",
        "unicode character",
    ),
    _Declaration(
        "question_frequency",
        "analysis.question-frequency",
        "Question-mark frequency",
        VoiceDimension.ORTHOGRAPHIC,
        "marks_per_sentence",
        "sentence",
    ),
    _Declaration(
        "exclamation_frequency",
        "analysis.exclamation-frequency",
        "Exclamation-mark frequency",
        VoiceDimension.ORTHOGRAPHIC,
        "marks_per_sentence",
        "sentence",
    ),
    _Declaration(
        "link_count",
        "analysis.link-count",
        "Link count",
        VoiceDimension.PLATFORM_ADAPTATION,
        "links",
        "unicode character",
    ),
    _Declaration(
        "hashtag_count",
        "analysis.hashtag-count",
        "Hashtag count",
        VoiceDimension.PLATFORM_ADAPTATION,
        "hashtags",
        "unicode character",
    ),
    _Declaration(
        "mention_count",
        "analysis.mention-count",
        "Mention count",
        VoiceDimension.PLATFORM_ADAPTATION,
        "mentions",
        "unicode character",
    ),
    _Declaration(
        "capitalization_ratio",
        "analysis.capitalization-ratio",
        "Uppercase character ratio",
        VoiceDimension.ORTHOGRAPHIC,
        "ratio",
        "cased character",
    ),
    _Declaration(
        "uppercase_word_ratio",
        "analysis.uppercase-word-ratio",
        "Uppercase word ratio",
        VoiceDimension.ORTHOGRAPHIC,
        "ratio",
        "cased word",
    ),
    _Declaration(
        "blank_line_count",
        "analysis.blank-line-count",
        "Blank line count",
        VoiceDimension.LAYOUT,
        "blank_lines",
        "line",
    ),
    _Declaration(
        "repeated_whitespace_count",
        "analysis.repeated-whitespace-count",
        "Repeated whitespace runs",
        VoiceDimension.LAYOUT,
        "runs",
        "unicode character",
    ),
    _Declaration(
        "sentence_p25_words",
        "analysis.sentence-p25-words",
        "Sentence length 25th percentile",
        VoiceDimension.RHYTHMIC,
        "words_per_sentence",
        "sentence",
    ),
    _Declaration(
        "sentence_median_words",
        "analysis.sentence-median-words",
        "Median sentence length",
        VoiceDimension.RHYTHMIC,
        "words_per_sentence",
        "sentence",
    ),
    _Declaration(
        "sentence_p75_words",
        "analysis.sentence-p75-words",
        "Sentence length 75th percentile",
        VoiceDimension.RHYTHMIC,
        "words_per_sentence",
        "sentence",
    ),
    _Declaration(
        "sentence_length_stddev",
        "analysis.sentence-length-stddev",
        "Sentence length standard deviation",
        VoiceDimension.RHYTHMIC,
        "words_per_sentence",
        "sentence",
    ),
    _Declaration(
        "short_sentence_ratio",
        "analysis.short-sentence-ratio",
        "Short sentence ratio",
        VoiceDimension.RHYTHMIC,
        "ratio",
        "sentence",
    ),
    _Declaration(
        "long_sentence_ratio",
        "analysis.long-sentence-ratio",
        "Long sentence ratio",
        VoiceDimension.RHYTHMIC,
        "ratio",
        "sentence",
    ),
    _Declaration(
        "paragraph_median_words",
        "analysis.paragraph-median-words",
        "Median paragraph length",
        VoiceDimension.LAYOUT,
        "words_per_paragraph",
        "paragraph",
    ),
    _Declaration(
        "paragraph_length_stddev",
        "analysis.paragraph-length-stddev",
        "Paragraph length standard deviation",
        VoiceDimension.LAYOUT,
        "words_per_paragraph",
        "paragraph",
    ),
    _Declaration(
        "single_sentence_paragraph_ratio",
        "analysis.single-sentence-paragraph-ratio",
        "Single-sentence paragraph ratio",
        VoiceDimension.LAYOUT,
        "ratio",
        "paragraph",
    ),
    _Declaration(
        "opening_sentence_words",
        "analysis.opening-sentence-words",
        "Opening sentence length",
        VoiceDimension.RHYTHMIC,
        "words",
        "document",
    ),
    _Declaration(
        "opening_question_indicator",
        "analysis.opening-question-indicator",
        "Opening question indicator",
        VoiceDimension.DISCOURSE_RHETORICAL,
        "binary",
        "document",
    ),
    _Declaration(
        "opening_first_person_indicator",
        "analysis.opening-first-person-indicator",
        "First-person opening indicator",
        VoiceDimension.NARRATIVE_PERSPECTIVE,
        "binary",
        "document",
        ("en",),
    ),
    _Declaration(
        "opening_second_person_indicator",
        "analysis.opening-second-person-indicator",
        "Second-person opening indicator",
        VoiceDimension.AUDIENCE_INTERPERSONAL,
        "binary",
        "document",
        ("en",),
    ),
    _Declaration(
        "closing_question_indicator",
        "analysis.closing-question-indicator",
        "Closing question indicator",
        VoiceDimension.DISCOURSE_RHETORICAL,
        "binary",
        "document",
    ),
    _Declaration(
        "question_position_mean",
        "analysis.question-position-mean",
        "Mean normalized question position",
        VoiceDimension.DISCOURSE_RHETORICAL,
        "normalized_position",
        "sentence",
    ),
)


@dataclass(frozen=True, slots=True)
class Tier1Runtime:
    """Complete default runtime inputs needed by analysis and scalar compilation."""

    registry: FeatureRegistry
    analyzers: tuple[Analyzer, ...]
    baselines: ScalarBaselineSnapshot


def build_tier1_runtime() -> Tier1Runtime:
    """Build the pinned default feature registry, analyzers, and explicit zero baselines."""

    definitions = tuple(_definition(item) for item in _DECLARATIONS)
    registry = FeatureRegistry.build(
        registry_id=_REGISTRY_ID,
        version=_REGISTRY_VERSION,
        definitions=definitions,
        created_at=_CREATED_AT,
    )
    references = {
        item.binding: definition.reference
        for item, definition in zip(_DECLARATIONS, definitions, strict=True)
    }
    configuration_hash = sha256_text(
        "tier1-runtime:1.1.0:" + ",".join(item.feature_id for item in _DECLARATIONS)
    )
    config = DeterministicAnalyzerConfig(configuration_hash=configuration_hash)
    stylometry_config = StylometryAnalyzerConfig(
        configuration_hash=sha256_text(
            "tier1-stylometry:1.0.0:short<=5:long>=20:linear-percentiles"
        )
    )
    analyzers: tuple[Analyzer, ...] = (
        DocumentStatisticsAnalyzer(
            features=DocumentStatisticsFeatures(
                **{key: references[key] for key in DocumentStatisticsFeatures.model_fields}
            ),
            config=config,
        ),
        StructuralAnalyzer(
            features=StructuralFeatures(
                **{key: references[key] for key in StructuralFeatures.model_fields}
            ),
            config=config,
        ),
        SymbolUsageAnalyzer(
            features=SymbolUsageFeatures(
                **{key: references[key] for key in SymbolUsageFeatures.model_fields}
            ),
            config=config,
        ),
        FormattingAnalyzer(
            features=FormattingFeatures(
                **{key: references[key] for key in FormattingFeatures.model_fields}
            ),
            config=config,
        ),
        DistributionalStylometryAnalyzer(
            features=DistributionalStylometryFeatures(
                **{key: references[key] for key in DistributionalStylometryFeatures.model_fields}
            ),
            config=stylometry_config,
        ),
        RhetoricalPositionAnalyzer(
            features=RhetoricalPositionFeatures(
                **{key: references[key] for key in RhetoricalPositionFeatures.model_fields}
            ),
            config=stylometry_config,
        ),
        OpeningStanceAnalyzer(
            features=OpeningStanceFeatures(
                **{key: references[key] for key in OpeningStanceFeatures.model_fields}
            ),
            config=stylometry_config,
        ),
    )
    baseline_hash = sha256_text("descriptive-zero-baseline:1.1.0")
    baselines = ScalarBaselineSnapshot(
        baselines=tuple(
            ScalarFeatureBaseline(
                feature=definition.reference,
                reference=BaselineReference(
                    baseline_id=_BASELINE_ID,
                    version=_REGISTRY_VERSION,
                    cohort_definition_hash=baseline_hash,
                ),
                value=ScalarValue(value=0, unit=declaration.unit),
            )
            for declaration, definition in zip(_DECLARATIONS, definitions, strict=True)
        )
    )
    return Tier1Runtime(registry=registry, analyzers=analyzers, baselines=baselines)


def _definition(declaration: _Declaration) -> FeatureDefinition:
    return FeatureDefinition(
        feature_id=declaration.feature_id,
        semantic_version=_FEATURE_VERSION,
        display_name=declaration.display_name,
        description=(
            f"Deterministic descriptive measurement of {declaration.display_name.lower()}."
        ),
        dimension=declaration.dimension,
        observation_scope=EvidenceUnitType.DOCUMENT,
        opportunity_unit=declaration.opportunity,
        measurement_pipeline=(MeasurementClass.DETERMINISTIC,),
        supported_languages=LanguageApplicability(
            all_languages=not declaration.supported_languages,
            languages=declaration.supported_languages,
        ),
        supported_platforms=PlatformApplicability(all_platforms=True, platforms=()),
        supported_modalities=(SourceModality.AUTHORED_WRITTEN,),
        value_type=FeatureValueType.SCALAR,
        confidence_model=ConfidenceModelDefinition(
            model_id="confidence.evidence-derived-descriptive",
            version=_FEATURE_VERSION,
            required_components=tuple(ConfidenceComponent),
            calibration_required=False,
        ),
        aggregation_strategy=AggregationStrategyReference(
            strategy_id="aggregation.descriptive-arithmetic-mean",
            version=_FEATURE_VERSION,
            output_value_type=FeatureValueType.SCALAR,
        ),
        downstream_permissions=(
            DownstreamPermission.EXPLORE,
            DownstreamPermission.RETRIEVE,
            DownstreamPermission.EVALUATE,
            DownstreamPermission.EXPLAIN,
        ),
        evidence_requirements=EvidenceRequirements(
            minimum_evidence_units=1,
            minimum_independent_clusters=1,
            required_roles=(EvidenceRole.SUPPORT,),
            allowed_modalities=(SourceModality.AUTHORED_WRITTEN,),
            requires_target_attribution=True,
            requires_rights_admissibility=True,
        ),
        nuisance_controls=(),
        minimum_text_characters=1,
    )
