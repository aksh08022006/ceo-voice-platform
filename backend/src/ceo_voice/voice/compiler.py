"""Interface-driven orchestration from observations to a structurally valid HVM release."""

from typing import Protocol, Self
from uuid import UUID

from pydantic import Field, ValidationError, model_validator

from ceo_voice.core.exceptions import HVMValidationError, ProfileCompilationError
from ceo_voice.models.base import ContractModel, UtcDatetime
from ceo_voice.voice.components import (
    ExplicitPreference,
    NegativeConstraint,
    ProfileComponents,
    Prototype,
)
from ceo_voice.voice.evidence import EvidenceSnapshot, EvidenceUnit
from ceo_voice.voice.identity import ProfileLineage, VoiceIdentity
from ceo_voice.voice.observations import Observation
from ceo_voice.voice.ports import (
    AggregationRequest,
    Aggregator,
    ConditionalResidualEstimationRequest,
    ConditionalResidualEstimator,
    ConfidenceEstimationRequest,
    ConfidenceEstimator,
    DriftEstimationRequest,
    DriftEstimator,
    FeatureRegistryReader,
    InteractionEstimationRequest,
    InteractionEstimator,
    PartialPooler,
    PartialPoolingRequest,
    ReleaseValidator,
    ResidualComputationRequest,
    ResidualComputer,
)
from ceo_voice.voice.primitives import SemanticVersion
from ceo_voice.voice.releases import CompiledProfile, HVMRelease
from ceo_voice.voice.validation import ReleaseValidationSubject


class _Identified(Protocol):
    """Structural type used only for deterministic component ordering."""

    id: UUID


class CompilationRequest(ContractModel):
    """Complete deterministic input for one HVM compilation run."""

    build_id: UUID = Field(description="Stable compilation-run identifier.")
    release_id: UUID = Field(description="Release identifier chosen by the caller.")
    release_version: int = Field(ge=1, description="Next lineage release version.")
    validation_report_id: UUID = Field(description="Validation report identifier chosen by caller.")
    identity: VoiceIdentity = Field(description="Governed target writing identity.")
    lineage: ProfileLineage = Field(description="Target profile lineage.")
    evidence_snapshot: EvidenceSnapshot = Field(description="Pinned evidence manifest.")
    evidence_units: tuple[EvidenceUnit, ...] = Field(min_length=1)
    observations: tuple[Observation, ...] = Field(min_length=1)
    prototypes: tuple[Prototype, ...] = Field(default_factory=tuple)
    negative_constraints: tuple[NegativeConstraint, ...] = Field(default_factory=tuple)
    explicit_preferences: tuple[ExplicitPreference, ...] = Field(default_factory=tuple)
    previous_release: HVMRelease | None = Field(default=None)
    created_at: UtcDatetime = Field(description="UTC release sealing time.")
    validated_at: UtcDatetime = Field(description="UTC structural-validation time.")

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        """Reject duplicate inputs and inconsistent identity-lineage ownership."""

        if self.identity.tenant_id != self.lineage.tenant_id:
            raise ValueError("identity and lineage must share a tenant")
        if self.identity.id != self.lineage.voice_identity_id:
            raise ValueError("lineage must reference the requested voice identity")
        if self.evidence_snapshot.tenant_id != self.identity.tenant_id:
            raise ValueError("evidence snapshot must share the identity tenant")
        if self.evidence_snapshot.voice_identity_id != self.identity.id:
            raise ValueError("evidence snapshot must reference the requested identity")
        for name, values in (
            ("evidence units", tuple(item.id for item in self.evidence_units)),
            ("observations", tuple(item.id for item in self.observations)),
            ("prototypes", tuple(item.id for item in self.prototypes)),
            ("negative constraints", tuple(item.id for item in self.negative_constraints)),
            ("explicit preferences", tuple(item.id for item in self.explicit_preferences)),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"compilation {name} must have unique IDs")
        return self


class ProfileCompiler:
    """Coordinate injected HVM stages without implementing statistics or feature logic."""

    def __init__(
        self,
        *,
        registry: FeatureRegistryReader,
        aggregator: Aggregator,
        partial_pooler: PartialPooler,
        residual_computer: ResidualComputer,
        conditional_residual_estimator: ConditionalResidualEstimator,
        interaction_estimator: InteractionEstimator,
        drift_estimator: DriftEstimator,
        confidence_estimator: ConfidenceEstimator,
        validator: ReleaseValidator,
        compiler_version: SemanticVersion,
    ) -> None:
        self._registry = registry
        self._aggregator = aggregator
        self._partial_pooler = partial_pooler
        self._residual_computer = residual_computer
        self._conditional_residual_estimator = conditional_residual_estimator
        self._interaction_estimator = interaction_estimator
        self._drift_estimator = drift_estimator
        self._confidence_estimator = confidence_estimator
        self._validator = validator
        self._compiler_version = compiler_version

    def compile(self, request: CompilationRequest) -> CompiledProfile:
        """Run injected stages in order and seal a validated immutable release.

        Raises:
            ProfileCompilationError: If a stage omits mandatory output or changes component
                identity during confidence estimation.
            HVMValidationError: If the assembled release fails structural validation.
        """

        registry_reference = self._registry.reference
        evidence_units = tuple(sorted(request.evidence_units, key=lambda item: item.id.int))
        observations = tuple(sorted(request.observations, key=lambda item: item.id.int))
        aggregates = self._aggregator.aggregate(
            AggregationRequest(
                build_id=request.build_id,
                registry=registry_reference,
                observations=observations,
                evidence_units=evidence_units,
            )
        )
        self._require_non_empty(aggregates, stage="aggregation")

        pooled_aggregates = self._partial_pooler.pool(
            PartialPoolingRequest(
                build_id=request.build_id,
                registry=registry_reference,
                aggregates=aggregates,
            )
        )
        self._require_non_empty(pooled_aggregates, stage="partial_pooling")

        residuals = self._residual_computer.compute(
            ResidualComputationRequest(
                build_id=request.build_id,
                voice_identity_id=request.identity.id,
                registry=registry_reference,
                pooled_aggregates=pooled_aggregates,
            )
        )
        self._require_non_empty(residuals, stage="residual_computation")

        conditional_residuals = self._conditional_residual_estimator.estimate(
            ConditionalResidualEstimationRequest(
                build_id=request.build_id,
                registry=registry_reference,
                observations=observations,
                core_residuals=residuals,
            )
        )
        interactions = self._interaction_estimator.estimate(
            InteractionEstimationRequest(
                build_id=request.build_id,
                registry=registry_reference,
                observations=observations,
                aggregates=pooled_aggregates,
                residuals=residuals,
            )
        )
        drift_states = self._drift_estimator.estimate(
            DriftEstimationRequest(
                build_id=request.build_id,
                registry=registry_reference,
                observations=observations,
                residuals=residuals,
                previous_release=request.previous_release,
            )
        )
        provisional = ProfileComponents(
            aggregates=self._ordered(pooled_aggregates),
            residuals=self._ordered(residuals),
            conditional_residuals=self._ordered(conditional_residuals),
            interactions=self._ordered(interactions),
            drift_states=self._ordered(drift_states),
        )
        components = self._confidence_estimator.estimate(
            ConfidenceEstimationRequest(
                build_id=request.build_id,
                registry=registry_reference,
                observations=observations,
                components=provisional,
            )
        )
        if not self._preserves_component_content(provisional, components):
            raise ProfileCompilationError(
                "confidence estimator changed component identity or non-confidence content",
                details={"build_id": str(request.build_id)},
            )

        try:
            release = HVMRelease(
                id=request.release_id,
                tenant_id=request.identity.tenant_id,
                voice_identity_id=request.identity.id,
                lineage_id=request.lineage.id,
                version=request.release_version,
                previous_release_id=(
                    request.previous_release.id if request.previous_release is not None else None
                ),
                registry=registry_reference,
                evidence_snapshot=request.evidence_snapshot.reference,
                observation_references=tuple(item.reference for item in observations),
                components=components,
                prototypes=self._ordered(request.prototypes),
                negative_constraints=self._ordered(request.negative_constraints),
                explicit_preferences=self._ordered(request.explicit_preferences),
                validation_report_id=request.validation_report_id,
                compiler_version=self._compiler_version,
                created_at=request.created_at,
            )
        except ValidationError as exc:
            raise ProfileCompilationError(
                "compilation stages produced an invalid release payload",
                details={"build_id": str(request.build_id), "error_count": exc.error_count()},
            ) from exc
        subject = ReleaseValidationSubject(
            identity=request.identity,
            lineage=request.lineage,
            release=release,
            evidence_snapshot=request.evidence_snapshot,
            evidence_units=evidence_units,
            observations=observations,
            previous_release=request.previous_release,
        )
        report = self._validator.validate(
            subject,
            report_id=request.validation_report_id,
            validated_at=request.validated_at,
        )
        if not report.is_valid():
            raise HVMValidationError(
                "compiled HVM release failed structural validation",
                details={
                    "release_id": str(release.id),
                    "report_id": str(report.id),
                    "issue_codes": tuple(issue.code for issue in report.issues),
                },
            )
        return CompiledProfile(release=release, validation_report=report)

    @staticmethod
    def _require_non_empty(values: tuple[object, ...], *, stage: str) -> None:
        if not values:
            raise ProfileCompilationError(
                "compilation stage returned no mandatory components",
                details={"stage": stage},
            )

    @staticmethod
    def _ordered[T: _Identified](values: tuple[T, ...]) -> tuple[T, ...]:
        """Canonicalize domain objects that expose UUID identifiers."""

        return tuple(sorted(values, key=lambda item: item.id.int))

    @staticmethod
    def _preserves_component_content(before: ProfileComponents, after: ProfileComponents) -> bool:
        """Allow confidence replacement while forbidding every other component change."""

        before_groups: tuple[tuple[ContractModel, ...], ...] = (
            before.aggregates,
            before.residuals,
            before.conditional_residuals,
            before.interactions,
            before.drift_states,
        )
        after_groups: tuple[tuple[ContractModel, ...], ...] = (
            after.aggregates,
            after.residuals,
            after.conditional_residuals,
            after.interactions,
            after.drift_states,
        )
        if tuple(len(group) for group in before_groups) != tuple(
            len(group) for group in after_groups
        ):
            return False
        for before_group, after_group in zip(before_groups, after_groups, strict=True):
            for before_item, after_item in zip(before_group, after_group, strict=True):
                if before_item.model_dump(exclude={"confidence"}) != after_item.model_dump(
                    exclude={"confidence"}
                ):
                    return False
        return True
