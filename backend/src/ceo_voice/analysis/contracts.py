"""Immutable contracts shared by analyzers and orchestration services."""

from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from ceo_voice.analysis.enums import (
    AnalysisRunStatus,
    AnalyzerCategory,
    AnalyzerInput,
    AnalyzerRunStatus,
    ConfidenceMethod,
)
from ceo_voice.ingestion import CleanDocument
from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import Platform
from ceo_voice.voice.enums import (
    EvidenceUnitType,
    MeasurementClass,
    ObservationState,
    SourceModality,
)
from ceo_voice.voice.evidence import EvidenceSnapshot, EvidenceUnit, EvidenceWeightComponents
from ceo_voice.voice.identity import VoiceIdentity
from ceo_voice.voice.observations import Observation
from ceo_voice.voice.primitives import (
    FeatureReference,
    RegistryReference,
    SemanticVersion,
    Sha256Digest,
    UnitInterval,
)
from ceo_voice.voice.values import VoiceValue


class AnalyzerDependency(ContractModel):
    """Version-compatible dependency on another registered analyzer."""

    analyzer_id: NonEmptyStr = Field(description="Stable dependency analyzer identifier.")
    minimum_version: SemanticVersion = Field(description="Lowest compatible dependency version.")
    maximum_major: int | None = Field(
        default=None,
        ge=0,
        description="Optional inclusive major-version compatibility ceiling.",
    )

    def accepts(self, version: SemanticVersion) -> bool:
        """Return whether ``version`` satisfies this dependency constraint."""

        if version.compare_precedence(self.minimum_version) < 0:
            return False
        return self.maximum_major is None or version.major <= self.maximum_major


class AnalyzerSpecification(ContractModel):
    """Declarative analyzer capabilities used without inspecting implementation code."""

    analyzer_id: NonEmptyStr = Field(description="Stable analyzer identifier.")
    version: SemanticVersion = Field(description="Exact analyzer implementation version.")
    category: AnalyzerCategory = Field(description="Analyzer family.")
    supported_features: tuple[FeatureReference, ...] = Field(
        min_length=1, description="Exact feature definitions this analyzer can emit."
    )
    required_inputs: tuple[AnalyzerInput, ...] = Field(
        min_length=1, description="Document-analysis artifacts required by the analyzer."
    )
    all_platforms: bool = Field(description="Whether every platform is supported.")
    supported_platforms: tuple[Platform, ...] = Field(
        default_factory=tuple, description="Explicit platform support when not universal."
    )
    all_languages: bool = Field(description="Whether every language is supported.")
    supported_languages: tuple[NonEmptyStr, ...] = Field(
        default_factory=tuple, description="Explicit BCP 47 language support."
    )
    priority: int = Field(default=100, ge=0, description="Lower values run first within a level.")
    measurement_class: MeasurementClass = Field(description="Production method classification.")
    dependencies: tuple[AnalyzerDependency, ...] = Field(
        default_factory=tuple, description="Analyzer prerequisites."
    )
    configuration_hash: Sha256Digest = Field(
        description="Digest of behavior-affecting analyzer configuration."
    )

    @model_validator(mode="after")
    def validate_capabilities(self) -> Self:
        """Reject ambiguous feature, input, scope, and dependency declarations."""

        for values, label in (
            (self.supported_features, "supported features"),
            (self.required_inputs, "required inputs"),
            (self.supported_platforms, "supported platforms"),
            (self.supported_languages, "supported languages"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
        dependency_ids = tuple(item.analyzer_id for item in self.dependencies)
        if len(dependency_ids) != len(set(dependency_ids)):
            raise ValueError("analyzer dependencies must be unique")
        if self.analyzer_id in dependency_ids:
            raise ValueError("an analyzer cannot depend on itself")
        if self.all_platforms == bool(self.supported_platforms):
            raise ValueError("declare either all platforms or an explicit platform set")
        if self.all_languages == bool(self.supported_languages):
            raise ValueError("declare either all languages or an explicit language set")
        return self

    def supports(self, document: CleanDocument) -> bool:
        """Return whether document language and platform are within declared scope."""

        platform_supported = self.all_platforms or document.platform in self.supported_platforms
        language_supported = self.all_languages or document.language in self.supported_languages
        return platform_supported and language_supported


class AddressedSpan(ContractModel):
    """Stable structural span produced by document analysis."""

    id: UUID = Field(description="Deterministic span identifier.")
    unit_type: EvidenceUnitType = Field(description="Document structural unit.")
    start_offset: int = Field(ge=0, description="Inclusive Unicode character offset.")
    end_offset: int = Field(ge=1, description="Exclusive Unicode character offset.")
    ordinal: int = Field(ge=0, description="Zero-based position among peer units.")
    paragraph_id: UUID | None = Field(default=None, description="Containing paragraph identifier.")
    sentence_id: UUID | None = Field(
        default=None, description="Sentence identifier when applicable."
    )

    @model_validator(mode="after")
    def validate_offsets(self) -> Self:
        """Reject empty or structurally inconsistent spans."""

        if self.end_offset <= self.start_offset:
            raise ValueError("span end offset must be greater than start offset")
        if self.unit_type is EvidenceUnitType.SENTENCE and self.sentence_id != self.id:
            raise ValueError("sentence spans must identify themselves")
        if self.unit_type is EvidenceUnitType.PARAGRAPH and self.paragraph_id != self.id:
            raise ValueError("paragraph spans must identify themselves")
        return self


class AnalyzedDocument(ContractModel):
    """Source-neutral document plus deterministic structural addressing."""

    document: CleanDocument = Field(description="Immutable ingestion projection.")
    segmentation_version: SemanticVersion = Field(description="Exact segmentation policy version.")
    document_span: AddressedSpan = Field(description="Whole-document evidence span.")
    paragraphs: tuple[AddressedSpan, ...] = Field(description="Ordered non-empty paragraphs.")
    sentences: tuple[AddressedSpan, ...] = Field(description="Ordered sentence spans.")
    lines: tuple[AddressedSpan, ...] = Field(description="Ordered non-empty line spans.")

    def text_for(self, span: AddressedSpan) -> str:
        """Return exact source text for an addressed span."""

        return self.document.content[span.start_offset : span.end_offset]

    def span(self, span_id: UUID) -> AddressedSpan:
        """Resolve an evidence span or raise ``KeyError``."""

        for item in (self.document_span, *self.paragraphs, *self.sentences, *self.lines):
            if item.id == span_id:
                return item
        raise KeyError(span_id)


class AnalysisRequest(ContractModel):
    """Complete deterministic context for one document analysis."""

    run_id: UUID = Field(description="Caller-controlled stable analysis run identifier.")
    document: CleanDocument = Field(description="Clean immutable source document.")
    voice_identity: VoiceIdentity = Field(description="Governed target voice identity.")
    source_modality: SourceModality = Field(description="Governed source-production modality.")
    event_time: UtcDatetime = Field(description="Behavior time selected by upstream policy.")
    created_at: UtcDatetime = Field(description="Deterministic observation creation timestamp.")

    @model_validator(mode="after")
    def validate_ownership(self) -> Self:
        """Keep tenant and leader attribution aligned with the clean document."""

        if self.document.tenant_id != self.voice_identity.tenant_id:
            raise ValueError("document and voice identity must share a tenant")
        if self.document.ceo_id != self.voice_identity.leader_id:
            raise ValueError("document CEO and voice identity leader must match")
        return self


class MeasurementCandidate(ContractModel):
    """Analyzer-emitted claim awaiting centralized observation construction."""

    feature: FeatureReference = Field(description="Exact feature measured.")
    state: ObservationState = Field(default=ObservationState.OBSERVED)
    value: VoiceValue | None = Field(description="Typed HVM value when observed.")
    evidence_span_ids: tuple[UUID, ...] = Field(
        min_length=1, description="Addressed spans supporting this claim."
    )
    opportunity_count: int = Field(ge=0, description="Applicable measurement opportunities.")

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        """Enforce value-state and evidence uniqueness before orchestration."""

        if self.state is ObservationState.OBSERVED and self.value is None:
            raise ValueError("observed candidates require a value")
        if self.state is not ObservationState.OBSERVED and self.value is not None:
            raise ValueError("non-observed candidates cannot contain a value")
        if len(self.evidence_span_ids) != len(set(self.evidence_span_ids)):
            raise ValueError("candidate evidence spans must be unique")
        return self


class AnalyzerContext(ContractModel):
    """Read-only compiler context presented to a pure analyzer."""

    request: AnalysisRequest
    analyzed_document: AnalyzedDocument
    dependency_results: dict[str, tuple[MeasurementCandidate, ...]] = Field(default_factory=dict)


class ConfidenceRequest(ContractModel):
    """Inputs supplied to an injected confidence-composition strategy."""

    method: ConfidenceMethod
    measurement_class: MeasurementClass
    analyzer: AnalyzerSpecification
    candidate: MeasurementCandidate
    evidence_count: int = Field(ge=1)


class ComposedConfidence(ContractModel):
    """Complete quality and evidence weights required by an HVM observation."""

    quality: UnitInterval
    evidence_weights: EvidenceWeightComponents


class AnalyzerExecutionRecord(ContractModel):
    """Deterministic trace entry; wall-clock metrics are emitted out of band."""

    analyzer_id: NonEmptyStr
    analyzer_version: SemanticVersion
    level: int = Field(ge=0)
    status: AnalyzerRunStatus
    candidate_count: int = Field(ge=0)
    error_code: NonEmptyStr | None = None


class ObservationSet(ContractModel):
    """Canonical analysis output consumed directly by HVM compilation inputs."""

    run_id: UUID
    tenant_id: UUID
    voice_identity_id: UUID
    document_id: UUID
    document_version: int = Field(ge=1)
    registry: RegistryReference
    status: AnalysisRunStatus
    observations: tuple[Observation, ...]
    evidence_units: tuple[EvidenceUnit, ...]
    execution_trace: tuple[AnalyzerExecutionRecord, ...]
    created_at: UtcDatetime

    @model_validator(mode="after")
    def validate_integrity(self) -> Self:
        """Reject duplicates, dangling evidence, and noncanonical result ordering."""

        observation_ids = tuple(item.id for item in self.observations)
        evidence_ids = tuple(item.id for item in self.evidence_units)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("observation identifiers must be unique")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence-unit identifiers must be unique")
        if observation_ids != tuple(sorted(observation_ids, key=lambda item: item.int)):
            raise ValueError("observations must use canonical identifier ordering")
        if evidence_ids != tuple(sorted(evidence_ids, key=lambda item: item.int)):
            raise ValueError("evidence units must use canonical identifier ordering")
        evidence_id_set = set(evidence_ids)
        if any(
            reference.evidence_unit_id not in evidence_id_set
            for observation in self.observations
            for reference in observation.evidence
        ):
            raise ValueError("observations contain dangling evidence references")
        if any(item.tenant_id != self.tenant_id for item in self.observations):
            raise ValueError("observations must share the observation-set tenant")
        if any(item.voice_identity_id != self.voice_identity_id for item in self.observations):
            raise ValueError("observations must share the observation-set identity")
        return self

    def to_evidence_snapshot(self, *, snapshot_id: UUID) -> EvidenceSnapshot:
        """Build the canonical evidence manifest expected by the HVM compiler."""

        return EvidenceSnapshot.build(
            snapshot_id=snapshot_id,
            tenant_id=self.tenant_id,
            voice_identity_id=self.voice_identity_id,
            evidence_units=self.evidence_units,
            created_at=self.created_at,
        )
