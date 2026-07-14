"""Deterministic fixtures for voice-analysis behavior tests."""

from datetime import UTC, datetime
from uuid import UUID

from ceo_voice.analysis import (
    Analyzer,
    ComposedConfidence,
    DeclaredConfidenceComposer,
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
from ceo_voice.ingestion import CleanDocument
from ceo_voice.models.enums import DocumentSourceType, DocumentType, Platform
from ceo_voice.voice import (
    AggregationStrategyReference,
    ConfidenceComponent,
    ConfidenceModelDefinition,
    DownstreamPermission,
    EvidenceRequirements,
    EvidenceRole,
    EvidenceUnitType,
    EvidenceWeightComponents,
    FeatureDefinition,
    FeatureReference,
    FeatureRegistry,
    FeatureValueType,
    LanguageApplicability,
    MeasurementClass,
    PlatformApplicability,
    SemanticVersion,
    SourceModality,
    TargetIdentityType,
    VoiceDimension,
    VoiceIdentity,
)

NOW = datetime(2026, 7, 14, 8, 0, tzinfo=UTC)
TENANT_ID = UUID(int=101)
LEADER_ID = UUID(int=102)
IDENTITY_ID = UUID(int=103)
DOCUMENT_ID = UUID(int=104)
REGISTRY_ID = UUID(int=105)
RUN_ID = UUID(int=106)
CONFIG_HASH = "b" * 64

FEATURE_IDS = (
    "analysis.character-count",
    "analysis.word-count",
    "analysis.reading-time",
    "analysis.document-length",
    "analysis.thread-length",
    "analysis.sentence-count",
    "analysis.mean-sentence-words",
    "analysis.paragraph-count",
    "analysis.mean-paragraph-words",
    "analysis.line-break-count",
    "analysis.list-item-count",
    "analysis.heading-count",
    "analysis.emoji-count",
    "analysis.punctuation-count",
    "analysis.question-frequency",
    "analysis.exclamation-frequency",
    "analysis.link-count",
    "analysis.hashtag-count",
    "analysis.mention-count",
    "analysis.capitalization-ratio",
    "analysis.uppercase-word-ratio",
    "analysis.blank-line-count",
    "analysis.repeated-whitespace-count",
    "analysis.sentence-p25-words",
    "analysis.sentence-median-words",
    "analysis.sentence-p75-words",
    "analysis.sentence-length-stddev",
    "analysis.short-sentence-ratio",
    "analysis.long-sentence-ratio",
    "analysis.paragraph-median-words",
    "analysis.paragraph-length-stddev",
    "analysis.single-sentence-paragraph-ratio",
    "analysis.opening-sentence-words",
    "analysis.opening-question-indicator",
    "analysis.opening-first-person-indicator",
    "analysis.opening-second-person-indicator",
    "analysis.closing-question-indicator",
    "analysis.question-position-mean",
)


def semver(value: str = "1.0.0") -> SemanticVersion:
    """Return a parsed semantic version."""

    return SemanticVersion.parse(value)


def clean_document(
    *,
    content: str = "# BUILD\n\nHello CEO world!  Visit https://example.com #Growth @team.\n- Ship fast? 🚀",
    metadata: dict[str, object] | None = None,
    platform: Platform | None = Platform.LINKEDIN,
    language: str = "en",
) -> CleanDocument:
    """Return one immutable clean ingestion projection."""

    return CleanDocument(
        id=DOCUMENT_ID,
        raw_document_id=UUID(int=107),
        tenant_id=TENANT_ID,
        ceo_id=LEADER_ID,
        external_id="source-1",
        source=DocumentSourceType.LINKEDIN,
        document_type=DocumentType.SOCIAL_POST,
        author="Example CEO",
        platform=platform,
        publication_date=NOW,
        title="Build",
        content=content,
        metadata=metadata or {},
        transformation_lineage={"cleaner": "1.0.0"},
        language=language,
        url="https://example.com/post",
        tags=("leadership",),
        raw_checksum="a" * 64,
        source_fingerprint="b" * 64,
        content_checksum="c" * 64,
        document_fingerprint="d" * 64,
        fetched_at=NOW,
        processed_at=NOW,
        source_version="1",
        version=1,
    )


def identity() -> VoiceIdentity:
    """Return the governed identity matching ``clean_document``."""

    return VoiceIdentity(
        id=IDENTITY_ID,
        tenant_id=TENANT_ID,
        leader_id=LEADER_ID,
        display_name="Example CEO",
        target_type=TargetIdentityType.PERSONAL_AUTHORSHIP,
        policy_version=semver(),
        created_at=NOW,
    )


def feature_definition(feature_id: str) -> FeatureDefinition:
    """Return a document-scoped scalar feature accepted by Tier 1 analyzers."""

    return FeatureDefinition(
        feature_id=feature_id,
        semantic_version=semver(),
        display_name=feature_id,
        description=f"Deterministic test definition for {feature_id}.",
        dimension=VoiceDimension.ORTHOGRAPHIC,
        observation_scope=EvidenceUnitType.DOCUMENT,
        opportunity_unit="document_opportunity",
        measurement_pipeline=(MeasurementClass.DETERMINISTIC,),
        supported_languages=LanguageApplicability(all_languages=True, languages=()),
        supported_platforms=PlatformApplicability(all_platforms=True, platforms=()),
        supported_modalities=(SourceModality.AUTHORED_WRITTEN,),
        value_type=FeatureValueType.SCALAR,
        confidence_model=ConfidenceModelDefinition(
            model_id="confidence.declared-deterministic",
            version=semver(),
            required_components=tuple(ConfidenceComponent),
            calibration_required=False,
        ),
        aggregation_strategy=AggregationStrategyReference(
            strategy_id="aggregation.scalar",
            version=semver(),
            output_value_type=FeatureValueType.SCALAR,
        ),
        downstream_permissions=tuple(DownstreamPermission),
        evidence_requirements=EvidenceRequirements(
            minimum_evidence_units=1,
            minimum_independent_clusters=1,
            required_roles=(EvidenceRole.SUPPORT,),
            allowed_modalities=(SourceModality.AUTHORED_WRITTEN,),
            requires_target_attribution=True,
            requires_rights_admissibility=True,
        ),
        minimum_text_characters=1,
    )


def registry(*, feature_ids: tuple[str, ...] = FEATURE_IDS) -> FeatureRegistry:
    """Return a canonical registry containing requested scalar definitions."""

    return FeatureRegistry.build(
        registry_id=REGISTRY_ID,
        version=semver(),
        definitions=tuple(feature_definition(item) for item in feature_ids),
        created_at=NOW,
    )


def feature_map() -> dict[str, FeatureReference]:
    """Return exact references keyed by the suffix used in bindings."""

    return {
        item.removeprefix("analysis.").replace("-", "_"): feature_definition(item).reference
        for item in FEATURE_IDS
    }


def analyzers() -> tuple[Analyzer, ...]:
    """Return all Tier 1 analyzers with registry-injected bindings."""

    values = feature_map()
    config = DeterministicAnalyzerConfig(configuration_hash=CONFIG_HASH)
    stylometry_config = StylometryAnalyzerConfig(configuration_hash=CONFIG_HASH)
    return (
        DocumentStatisticsAnalyzer(
            features=DocumentStatisticsFeatures(
                **{key: values[key] for key in DocumentStatisticsFeatures.model_fields}
            ),
            config=config,
        ),
        StructuralAnalyzer(
            features=StructuralFeatures(
                **{key: values[key] for key in StructuralFeatures.model_fields}
            ),
            config=config,
        ),
        SymbolUsageAnalyzer(
            features=SymbolUsageFeatures(
                **{key: values[key] for key in SymbolUsageFeatures.model_fields}
            ),
            config=config,
        ),
        FormattingAnalyzer(
            features=FormattingFeatures(
                **{key: values[key] for key in FormattingFeatures.model_fields}
            ),
            config=config,
        ),
        DistributionalStylometryAnalyzer(
            features=DistributionalStylometryFeatures(
                **{key: values[key] for key in DistributionalStylometryFeatures.model_fields}
            ),
            config=stylometry_config,
        ),
        RhetoricalPositionAnalyzer(
            features=RhetoricalPositionFeatures(
                **{key: values[key] for key in RhetoricalPositionFeatures.model_fields}
            ),
            config=stylometry_config,
        ),
        OpeningStanceAnalyzer(
            features=OpeningStanceFeatures(
                **{key: values[key] for key in OpeningStanceFeatures.model_fields}
            ),
            config=stylometry_config,
        ),
    )


def confidence_composer() -> DeclaredConfidenceComposer:
    """Return an exact confidence contract with no inference algorithm."""

    return DeclaredConfidenceComposer(
        ComposedConfidence(
            quality=1,
            evidence_weights=EvidenceWeightComponents(
                target_attribution=1,
                speaker_attribution=1,
                source_reliability=1,
                modality_admissibility=1,
                observation_quality=1,
                independence=1,
                context_relevance=1,
                temporal_relevance=1,
                rights_admissible=True,
            ),
        )
    )
