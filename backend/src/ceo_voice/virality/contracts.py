"""Strict contracts for corpora, evidence, observations, aggregates, and releases."""

from datetime import datetime
from math import isfinite
from typing import Self
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from ceo_voice.ingestion import CleanDocument
from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import DocumentType, Platform
from ceo_voice.virality.enums import (
    EvidenceUnit,
    MetricCollectionMethod,
    PatternAuthority,
    PatternChangeStatus,
    PerformanceBasis,
    PublicationStatus,
    StructuralDimension,
    ValidationCode,
    ValidationSeverity,
)


class Version(ContractModel):
    """Small domain-local semantic version; virality does not depend on HVM primitives."""

    major: int = Field(ge=0)
    minor: int = Field(ge=0)
    patch: int = Field(ge=0)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class FeatureReference(ContractModel):
    """Exact reference to one structural feature definition."""

    feature_id: NonEmptyStr
    version: Version


class RegistryReference(ContractModel):
    """Content-addressed structural registry snapshot."""

    registry_id: UUID
    version: Version
    snapshot_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


class StructuralFeatureDefinition(ContractModel):
    """Governed vocabulary for one structural decision, never a lexical identity feature."""

    reference: FeatureReference
    display_name: NonEmptyStr
    description: NonEmptyStr
    dimension: StructuralDimension
    allowed_patterns: tuple[NonEmptyStr, ...] = Field(min_length=1)
    extractor_id: NonEmptyStr
    platform_aware: bool = True

    @model_validator(mode="after")
    def validate_patterns(self) -> Self:
        if len(self.allowed_patterns) != len(set(self.allowed_patterns)):
            raise ValueError("allowed structural patterns must be unique")
        return self


class PerformanceMetrics(ContractModel):
    """One time-pinned outcome snapshot; missing denominators stay explicit."""

    reactions: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    saves: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    impressions: int | None = Field(default=None, ge=0)
    audience_size: int | None = Field(default=None, ge=0)
    collected_at: UtcDatetime
    method: MetricCollectionMethod
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class NormalizedPerformance(ContractModel):
    """Transparent heuristic score and its comparability limitations."""

    weighted_engagement: float = Field(ge=0)
    score_per_thousand: float = Field(ge=0)
    basis: PerformanceBasis
    denominator: int | None = Field(default=None, ge=1)
    confounded: bool
    limitations: tuple[NonEmptyStr, ...]
    normalizer_version: Version

    @model_validator(mode="after")
    def validate_numbers(self) -> Self:
        if not isfinite(self.weighted_engagement) or not isfinite(self.score_per_thousand):
            raise ValueError("normalized performance values must be finite")
        return self


class ViralityCorpusItem(ContractModel):
    """One authorized social post and its outcome snapshot."""

    document: CleanDocument
    performance: PerformanceMetrics

    @model_validator(mode="after")
    def validate_item(self) -> Self:
        if self.document.platform is None:
            raise ValueError("virality corpus documents require a platform")
        if self.document.document_type is not DocumentType.SOCIAL_POST:
            raise ValueError("virality v1 accepts social posts only")
        if (
            self.document.publication_date is not None
            and self.performance.collected_at < self.document.publication_date
        ):
            raise ValueError("performance cannot be collected before publication")
        return self


class ViralityCorpus(ContractModel):
    """Versioned cross-leader dataset for learning reusable structural patterns."""

    id: UUID
    tenant_id: UUID
    library_id: UUID
    dataset_version: Version
    label: NonEmptyStr
    items: tuple[ViralityCorpusItem, ...] = Field(min_length=1)
    created_at: UtcDatetime

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        keys = tuple((item.document.id, item.document.version) for item in self.items)
        if len(keys) != len(set(keys)):
            raise ValueError("virality corpus documents must be unique by version")
        if any(item.document.tenant_id != self.tenant_id for item in self.items):
            raise ValueError("virality corpus documents must share the tenant")
        return self


class EvidenceSpan(ContractModel):
    """Content-free source address proving a structural classification."""

    id: UUID
    tenant_id: UUID
    corpus_id: UUID
    document_id: UUID
    document_version: int = Field(ge=1)
    unit: EvidenceUnit
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_span(self) -> Self:
        if self.end <= self.start:
            raise ValueError("evidence span end must exceed start")
        return self


class PatternMeasurement(ContractModel):
    """Extractor output before centralized evidence and provenance construction."""

    feature: FeatureReference
    pattern_key: NonEmptyStr
    label: NonEmptyStr
    unit: EvidenceUnit
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class StructuralObservation(ContractModel):
    """Evidence-backed structural classification for one post."""

    id: UUID
    tenant_id: UUID
    corpus_id: UUID
    document_id: UUID
    document_version: int = Field(ge=1)
    leader_id: UUID
    platform: Platform
    publication_date: UtcDatetime | None
    feature: FeatureReference
    pattern_key: NonEmptyStr
    label: NonEmptyStr
    evidence_ids: tuple[UUID, ...] = Field(min_length=1)
    performance: NormalizedPerformance
    extractor_id: NonEmptyStr
    extractor_version: Version
    created_at: UtcDatetime


class AggregationPolicy(ContractModel):
    """Explicit support gates for reusable descriptive patterns."""

    minimum_documents: int = Field(default=3, ge=1)
    minimum_leaders: int = Field(default=2, ge=1)


class PatternAggregate(ContractModel):
    """Cross-document structural pattern with observational performance association."""

    id: UUID
    tenant_id: UUID
    feature: FeatureReference
    dimension: StructuralDimension
    pattern_key: NonEmptyStr
    label: NonEmptyStr
    platform: Platform
    supporting_observation_ids: tuple[UUID, ...] = Field(min_length=1, max_length=25)
    supporting_evidence_ids: tuple[UUID, ...] = Field(min_length=1, max_length=25)
    support_count: int = Field(ge=1)
    leader_count: int = Field(ge=1)
    prevalence: float = Field(ge=0, le=1)
    mean_performance: float = Field(ge=0)
    platform_mean_performance: float = Field(ge=0)
    observed_relative_difference: float | None
    standard_error: float | None = Field(default=None, ge=0)
    comparable_fraction: float = Field(ge=0, le=1)
    earliest_publication: UtcDatetime | None
    latest_publication: UtcDatetime | None
    authority: PatternAuthority

    @model_validator(mode="after")
    def validate_statistics(self) -> Self:
        values = (
            self.prevalence,
            self.mean_performance,
            self.platform_mean_performance,
            self.comparable_fraction,
        )
        if any(not isfinite(item) for item in values):
            raise ValueError("aggregate statistics must be finite")
        if self.observed_relative_difference is not None and not isfinite(
            self.observed_relative_difference
        ):
            raise ValueError("relative difference must be finite")
        return self


class ValidationIssue(ContractModel):
    """One stable structural release finding."""

    code: ValidationCode
    severity: ValidationSeverity
    message: NonEmptyStr
    path: NonEmptyStr


class ValidationReport(ContractModel):
    """Complete validation result for one candidate release."""

    id: UUID
    release_id: UUID
    validator_version: Version
    issues: tuple[ValidationIssue, ...]
    validated_at: UtcDatetime

    def is_valid(self) -> bool:
        return not any(item.severity is ValidationSeverity.ERROR for item in self.issues)


class ViralityRelease(ContractModel):
    """Immutable Virality Knowledge Representation snapshot."""

    id: UUID
    tenant_id: UUID
    library_id: UUID
    version: int = Field(ge=1)
    previous_release_id: UUID | None
    corpus_id: UUID
    corpus_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    registry: RegistryReference
    aggregation_policy: AggregationPolicy
    analysis_snapshot: "AnalysisSnapshot"
    patterns: tuple[PatternAggregate, ...] = Field(min_length=1)
    created_at: UtcDatetime
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


class PublishedRelease(ContractModel):
    """Catalog record for one immutable release and its current publication state."""

    release: ViralityRelease
    validation: ValidationReport
    status: PublicationStatus
    published_at: UtcDatetime

    @model_validator(mode="after")
    def validate_publication(self) -> Self:
        if self.validation.release_id != self.release.id:
            raise ValueError("publication validation must reference its release")
        if not self.validation.is_valid():
            raise ValueError("an invalid virality release cannot be published")
        return self


class InspectionPattern(ContractModel):
    """Compact human-review view of one reusable structural pattern."""

    feature_id: NonEmptyStr
    dimension: StructuralDimension
    pattern_key: NonEmptyStr
    label: NonEmptyStr
    platform: Platform
    support_count: int = Field(ge=1)
    leader_count: int = Field(ge=1)
    prevalence: float = Field(ge=0, le=1)
    observed_relative_difference: float | None
    authority: PatternAuthority


class InspectionReport(ContractModel):
    """Human-readable release summary and scientific limitations."""

    release_id: UUID
    release_version: int = Field(ge=1)
    summary: NonEmptyStr
    corpus_documents: int = Field(ge=1)
    corpus_leaders: int = Field(ge=1)
    comparable_documents: int = Field(ge=0)
    platforms: tuple[Platform, ...]
    patterns: tuple[InspectionPattern, ...]
    limitations: tuple[NonEmptyStr, ...]
    generated_at: UtcDatetime


class ViralityProfile(ContractModel):
    """Complete published library artifact for search, comparison, and inspection."""

    publication: PublishedRelease
    inspection: InspectionReport
    build_fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        release = self.publication.release
        if self.inspection.release_id != release.id:
            raise ValueError("inspection must reference the published release")
        if self.inspection.release_version != release.version:
            raise ValueError("inspection version must match the published release")
        return self


class PatternSearchQuery(ContractModel):
    """Exact faceted search over a published structural pattern library."""

    platform: Platform | None = None
    dimensions: tuple[StructuralDimension, ...] = ()
    feature_ids: tuple[NonEmptyStr, ...] = ()
    minimum_support: int = Field(default=1, ge=1)
    authority: PatternAuthority | None = None
    limit: int = Field(default=20, ge=1, le=200)


class PatternSearchHit(ContractModel):
    """Explainable exact-match result; this is not semantic retrieval."""

    pattern: PatternAggregate
    explanation: NonEmptyStr


class PatternChange(ContractModel):
    """One matched structural pattern difference across releases."""

    feature: FeatureReference
    pattern_key: NonEmptyStr
    platform: Platform
    status: PatternChangeStatus
    support_delta: int
    prevalence_delta: float
    performance_difference_delta: float | None


class ComparisonReport(ContractModel):
    """Deterministic release-to-release structural diff."""

    previous_release_id: UUID
    current_release_id: UUID
    changes: tuple[PatternChange, ...]
    compared_at: UtcDatetime


class CorpusAnalysis(ContractModel):
    """Centralized structural observation pipeline output."""

    observations: tuple[StructuralObservation, ...]
    evidence: tuple[EvidenceSpan, ...]
    normalized_performance: tuple[NormalizedPerformance, ...]


class AnalysisSnapshot(ContractModel):
    """Compact content-addressed pointer to the full structural observation dataset."""

    id: UUID
    corpus_id: UUID
    observation_count: int = Field(ge=1)
    evidence_count: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


class ExtractionContext(ContractModel):
    """Minimal input exposed to a structural extractor."""

    document: CleanDocument
    performance: NormalizedPerformance


class ExtractorSpecification(ContractModel):
    """Versioned ownership declaration for a structural extractor."""

    extractor_id: NonEmptyStr
    version: Version
    features: tuple[FeatureReference, ...] = Field(min_length=1)


def publication_window(
    observations: tuple[StructuralObservation, ...],
) -> tuple[datetime | None, datetime | None]:
    """Return the exact temporal window represented by observations."""

    dates = tuple(item.publication_date for item in observations if item.publication_date)
    return (min(dates), max(dates)) if dates else (None, None)
