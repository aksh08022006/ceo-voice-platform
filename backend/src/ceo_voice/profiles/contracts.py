"""Immutable contracts for corpus-to-profile orchestration and published artifacts."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from ceo_voice.analysis import ObservationSet
from ceo_voice.ingestion import CleanDocument
from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import DocumentSourceType, Platform
from ceo_voice.profiles.enums import (
    BuildStage,
    CorpusHealthStatus,
    ProfileAuthority,
    ProgressKind,
)
from ceo_voice.voice import (
    BaselineReference,
    EvidenceUnit,
    FeatureReference,
    ManagedRelease,
    Observation,
    ProfileLineage,
    ReleaseStatus,
    RetrievalProjection,
    ScalarValue,
    SourceModality,
    ValidationReport,
    VoiceIdentity,
)


class CuratedDocument(ContractModel):
    """One approved clean document with explicit production modality."""

    document: CleanDocument
    source_modality: SourceModality


class CuratedCorpus(ContractModel):
    """Complete point-in-time corpus selected for one profile build."""

    identity: VoiceIdentity
    lineage: ProfileLineage
    documents: tuple[CuratedDocument, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        """Require one tenant, leader, lineage, and latest-only document set."""

        if self.identity.tenant_id != self.lineage.tenant_id:
            raise ValueError("identity and lineage must share a tenant")
        if self.identity.id != self.lineage.voice_identity_id:
            raise ValueError("lineage must reference the corpus identity")
        document_ids = tuple(item.document.id for item in self.documents)
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("curated corpus must contain one version per document ID")
        for item in self.documents:
            if item.document.tenant_id != self.identity.tenant_id:
                raise ValueError("corpus documents must share the identity tenant")
            if item.document.ceo_id != self.identity.leader_id:
                raise ValueError("corpus documents must belong to the identity leader")
        return self


class ProfileBuildManifest(ContractModel):
    """CLI-serializable command for a restartable profile build."""

    corpus: CuratedCorpus
    actor_id: UUID = Field(description="Authorized actor publishing the release.")
    requested_at: UtcDatetime = Field(description="Initial build request time.")
    publish: bool = Field(default=True, description="Activate after validation and approval.")


class ProfileBuildPolicy(ContractModel):
    """Explicit operational gates; scientific confidence is not hidden here."""

    maximum_parallel_documents: int = Field(default=8, ge=1, le=128)
    minimum_successful_documents: int = Field(default=1, ge=1)
    maximum_failed_fraction: float = Field(default=0.25, ge=0, le=1)
    production_minimum_documents: int = Field(default=20, ge=1)
    production_minimum_platforms: int = Field(default=2, ge=1)


class ScalarFeatureBaseline(ContractModel):
    """One explicit scalar baseline used to form a leader residual."""

    feature: FeatureReference
    reference: BaselineReference
    value: ScalarValue


class ScalarBaselineSnapshot(ContractModel):
    """Complete baseline coverage required by the descriptive scalar compiler."""

    baselines: tuple[ScalarFeatureBaseline, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_features(self) -> Self:
        """Require exactly one baseline per feature reference."""

        features = tuple(item.feature for item in self.baselines)
        if len(features) != len(set(features)):
            raise ValueError("scalar baseline features must be unique")
        return self

    def get(self, feature: FeatureReference) -> ScalarFeatureBaseline:
        """Resolve an exact feature baseline or raise ``KeyError``."""

        for baseline in self.baselines:
            if baseline.feature == feature:
                return baseline
        raise KeyError(feature)


class ObservationCacheKey(ContractModel):
    """Every immutable input required to reuse one document observation set."""

    analysis_run_id: UUID
    document_id: UUID
    document_version: int = Field(ge=1)
    document_fingerprint: NonEmptyStr
    registry_snapshot_hash: NonEmptyStr


class DocumentAnalysisFailure(ContractModel):
    """Safe failure record retained without leaking document content."""

    document_id: UUID
    document_version: int = Field(ge=1)
    code: NonEmptyStr
    message: NonEmptyStr


class CorpusObservationBatch(ContractModel):
    """Canonical batch result from cached and newly analyzed documents."""

    observation_sets: tuple[ObservationSet, ...]
    failures: tuple[DocumentAnalysisFailure, ...]
    analyzed_documents: int = Field(ge=0)
    reused_documents: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        """Keep batch accounting and observation-set document identity unambiguous."""

        if self.analyzed_documents + self.reused_documents != len(self.observation_sets):
            raise ValueError("batch counts must equal successful observation sets")
        document_ids = tuple(item.document_id for item in self.observation_sets)
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("batch observation sets must be unique by document")
        return self


class CorpusHealthIssue(ContractModel):
    """Human- and machine-readable corpus limitation."""

    code: NonEmptyStr
    message: NonEmptyStr
    blocking: bool


class CorpusHealthReport(ContractModel):
    """Coverage and failure report for the exact corpus used by a release."""

    corpus_hash: NonEmptyStr
    status: CorpusHealthStatus
    total_documents: int = Field(ge=1)
    successful_documents: int = Field(ge=0)
    partial_documents: int = Field(ge=0)
    failed_documents: int = Field(ge=0)
    reused_documents: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    observed_feature_count: int = Field(ge=0)
    evidence_unit_count: int = Field(ge=0)
    total_characters: int = Field(ge=0)
    total_words: int = Field(ge=0)
    platforms: tuple[Platform, ...]
    languages: tuple[NonEmptyStr, ...]
    sources: tuple[DocumentSourceType, ...]
    earliest_publication: datetime | None
    latest_publication: datetime | None
    missing_publication_dates: int = Field(ge=0)
    failed_analyzers: int = Field(ge=0)
    build_eligible: bool
    generation_ready: bool
    issues: tuple[CorpusHealthIssue, ...]


class FeatureInspection(ContractModel):
    """One compact, explainable published profile component."""

    feature: FeatureReference
    display_name: NonEmptyStr
    dimension: NonEmptyStr
    value: ScalarValue
    decision_state: NonEmptyStr
    confidence_coverage: float = Field(ge=0, le=1)
    evidence_count: int = Field(ge=0)
    platform: Platform | None


class ProfileInspectionReport(ContractModel):
    """Deterministic human-readable view over one exact release."""

    release_id: UUID
    release_version: int = Field(ge=1)
    release_status: ReleaseStatus
    release_content_hash: NonEmptyStr
    authority: ProfileAuthority
    summary: NonEmptyStr
    features: tuple[FeatureInspection, ...]
    limitations: tuple[NonEmptyStr, ...]
    generated_at: UtcDatetime


class BuildCheckpoint(ContractModel):
    """Durable workflow identity and current restart stage."""

    build_id: UUID
    corpus_hash: NonEmptyStr
    voice_identity_id: UUID
    lineage_id: UUID
    release_id: UUID
    release_version: int = Field(ge=1)
    validation_report_id: UUID
    evidence_snapshot_id: UUID
    projection_id: UUID
    stage: BuildStage
    requested_at: UtcDatetime
    updated_at: UtcDatetime
    last_error_code: NonEmptyStr | None = None


class ProgressEvent(ContractModel):
    """Transport-neutral workflow progress event."""

    build_id: UUID
    kind: ProgressKind
    stage: BuildStage
    completed: int = Field(ge=0)
    total: int = Field(ge=0)
    occurred_at: UtcDatetime
    document_id: UUID | None = None
    message: NonEmptyStr


class PublishedVoiceProfile(ContractModel):
    """Complete published artifact retaining release, evidence, reports, and projection."""

    build_id: UUID
    corpus_hash: NonEmptyStr
    managed_release: ManagedRelease
    validation_report: ValidationReport
    observations: tuple[Observation, ...] = Field(min_length=1)
    evidence_units: tuple[EvidenceUnit, ...] = Field(min_length=1)
    corpus_health: CorpusHealthReport
    inspection: ProfileInspectionReport
    retrieval_projection: RetrievalProjection
    published_at: UtcDatetime

    @model_validator(mode="after")
    def validate_artifact(self) -> Self:
        """Pin every derived artifact to the same immutable release."""

        release = self.managed_release.release
        if self.validation_report != self.managed_release.validation_report:
            raise ValueError("published validation report must match lifecycle state")
        if self.inspection.release_id != release.id:
            raise ValueError("inspection report must reference the published release")
        if self.retrieval_projection.release_id != release.id:
            raise ValueError("retrieval projection must reference the published release")
        if self.retrieval_projection.release_content_hash != release.content_hash:
            raise ValueError("retrieval projection must pin the release content")
        observation_ids = {item.id for item in self.observations}
        if observation_ids != {item.observation_id for item in release.observation_references}:
            raise ValueError("published observations must exactly match release references")
        return self
