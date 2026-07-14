"""Evidence-backed structural engagement intelligence independent from personal voice."""

from ceo_voice.virality.builder import ViralityLibraryBuilder
from ceo_voice.virality.comparison import compare_releases
from ceo_voice.virality.composition import create_virality_builder
from ceo_voice.virality.contracts import (
    AggregationPolicy,
    AnalysisSnapshot,
    ComparisonReport,
    EvidenceSpan,
    ExtractionContext,
    ExtractorSpecification,
    FeatureReference,
    InspectionReport,
    NormalizedPerformance,
    PatternAggregate,
    PatternChange,
    PatternMeasurement,
    PatternSearchHit,
    PatternSearchQuery,
    PerformanceMetrics,
    PublishedRelease,
    RegistryReference,
    StructuralFeatureDefinition,
    StructuralObservation,
    ValidationReport,
    Version,
    ViralityCorpus,
    ViralityCorpusItem,
    ViralityProfile,
    ViralityRelease,
)
from ceo_voice.virality.enums import (
    EvidenceUnit,
    MetricCollectionMethod,
    PatternAuthority,
    PatternChangeStatus,
    PerformanceBasis,
    PublicationStatus,
    StructuralDimension,
)
from ceo_voice.virality.features import build_feature_registry
from ceo_voice.virality.normalization import PerformanceNormalizer
from ceo_voice.virality.registry import (
    ExtractorRegistry,
    StructuralExtractor,
    StructuralFeatureRegistry,
)
from ceo_voice.virality.search import PatternSearcher
from ceo_voice.virality.validation import ViralityReleaseValidator
from ceo_voice.virality.workspace import (
    InMemoryViralityWorkspace,
    JsonViralityWorkspace,
)

__all__ = [
    "AggregationPolicy",
    "AnalysisSnapshot",
    "ComparisonReport",
    "EvidenceSpan",
    "EvidenceUnit",
    "ExtractionContext",
    "ExtractorRegistry",
    "ExtractorSpecification",
    "FeatureReference",
    "InMemoryViralityWorkspace",
    "InspectionReport",
    "JsonViralityWorkspace",
    "MetricCollectionMethod",
    "NormalizedPerformance",
    "PatternAggregate",
    "PatternAuthority",
    "PatternChange",
    "PatternChangeStatus",
    "PatternMeasurement",
    "PatternSearchHit",
    "PatternSearchQuery",
    "PatternSearcher",
    "PerformanceBasis",
    "PerformanceMetrics",
    "PerformanceNormalizer",
    "PublicationStatus",
    "PublishedRelease",
    "RegistryReference",
    "StructuralDimension",
    "StructuralExtractor",
    "StructuralFeatureDefinition",
    "StructuralFeatureRegistry",
    "StructuralObservation",
    "ValidationReport",
    "Version",
    "ViralityCorpus",
    "ViralityCorpusItem",
    "ViralityLibraryBuilder",
    "ViralityProfile",
    "ViralityRelease",
    "ViralityReleaseValidator",
    "build_feature_registry",
    "compare_releases",
    "create_virality_builder",
]
