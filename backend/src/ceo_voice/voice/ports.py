"""Dependency-inverted contracts for future HVM algorithms and persistence adapters."""

from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

from pydantic import Field

from ceo_voice.models.base import ContractModel, UtcDatetime
from ceo_voice.voice.components import (
    Aggregate,
    ConditionalResidual,
    DriftState,
    Interaction,
    ProfileComponents,
    Residual,
)
from ceo_voice.voice.evidence import EvidenceUnit
from ceo_voice.voice.observations import Observation
from ceo_voice.voice.primitives import (
    FeatureId,
    FeatureReference,
    RegistryReference,
    SemanticVersion,
)
from ceo_voice.voice.releases import HVMRelease, ManagedRelease, ReleaseChange, ValidationReport

if TYPE_CHECKING:
    from ceo_voice.voice.features import FeatureDefinition
    from ceo_voice.voice.validation import ReleaseValidationSubject


class AggregationRequest(ContractModel):
    """Typed input presented to an injected observation aggregator."""

    build_id: UUID = Field(description="Deterministic compilation-run identifier.")
    registry: RegistryReference = Field(description="Pinned feature registry.")
    observations: tuple[Observation, ...] = Field(min_length=1)
    evidence_units: tuple[EvidenceUnit, ...] = Field(min_length=1)


class PartialPoolingRequest(ContractModel):
    """Typed input presented to an injected partial-pooling implementation."""

    build_id: UUID = Field(description="Deterministic compilation-run identifier.")
    registry: RegistryReference = Field(description="Pinned feature registry.")
    aggregates: tuple[Aggregate, ...] = Field(min_length=1)


class ResidualComputationRequest(ContractModel):
    """Typed input for leader-versus-baseline residual computation."""

    build_id: UUID = Field(description="Deterministic compilation-run identifier.")
    voice_identity_id: UUID = Field(description="Target writing identity.")
    registry: RegistryReference = Field(description="Pinned feature registry.")
    pooled_aggregates: tuple[Aggregate, ...] = Field(min_length=1)


class ConditionalResidualEstimationRequest(ContractModel):
    """Typed input for context-specific residual estimation."""

    build_id: UUID = Field(description="Deterministic compilation-run identifier.")
    registry: RegistryReference = Field(description="Pinned feature registry.")
    observations: tuple[Observation, ...] = Field(min_length=1)
    core_residuals: tuple[Residual, ...] = Field(min_length=1)


class InteractionEstimationRequest(ContractModel):
    """Typed input for bounded feature-interaction estimation."""

    build_id: UUID = Field(description="Deterministic compilation-run identifier.")
    registry: RegistryReference = Field(description="Pinned feature registry.")
    observations: tuple[Observation, ...] = Field(min_length=1)
    aggregates: tuple[Aggregate, ...] = Field(min_length=1)
    residuals: tuple[Residual, ...] = Field(min_length=1)


class DriftEstimationRequest(ContractModel):
    """Typed input for temporal-regime estimation without prescribing an algorithm."""

    build_id: UUID = Field(description="Deterministic compilation-run identifier.")
    registry: RegistryReference = Field(description="Pinned feature registry.")
    observations: tuple[Observation, ...] = Field(min_length=1)
    residuals: tuple[Residual, ...] = Field(min_length=1)
    previous_release: HVMRelease | None = Field(
        default=None, description="Immediate predecessor used for point-in-time comparison."
    )


class ConfidenceEstimationRequest(ContractModel):
    """Typed component bundle presented to an injected confidence estimator."""

    build_id: UUID = Field(description="Deterministic compilation-run identifier.")
    registry: RegistryReference = Field(description="Pinned feature registry.")
    observations: tuple[Observation, ...] = Field(min_length=1)
    components: ProfileComponents = Field(description="Components requiring final confidence.")


@runtime_checkable
class FeatureRegistryReader(Protocol):
    """Read-only registry surface consumed by HVM services."""

    @property
    def reference(self) -> RegistryReference:
        """Return the exact registry snapshot reference."""

        ...

    def get(self, reference: FeatureReference) -> "FeatureDefinition":
        """Resolve one exact feature definition."""

        ...

    def resolve_latest(self, feature_id: FeatureId) -> "FeatureDefinition":
        """Resolve the highest-precedence definition for a stable ID."""

        ...

    def contains(self, reference: FeatureReference) -> bool:
        """Return whether an exact definition exists."""

        ...


@runtime_checkable
class Aggregator(Protocol):
    """Aggregate immutable observations without owning compilation orchestration."""

    def aggregate(self, request: AggregationRequest) -> tuple[Aggregate, ...]:
        """Return structurally complete aggregates."""

        ...


@runtime_checkable
class PartialPooler(Protocol):
    """Apply an implementation-defined hierarchical pooling contract."""

    def pool(self, request: PartialPoolingRequest) -> tuple[Aggregate, ...]:
        """Return pooled aggregates while preserving feature identity and evidence lineage."""

        ...


@runtime_checkable
class ResidualComputer(Protocol):
    """Compute leader residuals against versioned baselines."""

    def compute(self, request: ResidualComputationRequest) -> tuple[Residual, ...]:
        """Return leader-core residual components."""

        ...


@runtime_checkable
class ConditionalResidualEstimator(Protocol):
    """Estimate context deltas that inherit from core residuals."""

    def estimate(
        self, request: ConditionalResidualEstimationRequest
    ) -> tuple[ConditionalResidual, ...]:
        """Return supported conditional residuals; an empty tuple is explicit."""

        ...


@runtime_checkable
class InteractionEstimator(Protocol):
    """Estimate bounded, registered feature dependencies."""

    def estimate(self, request: InteractionEstimationRequest) -> tuple[Interaction, ...]:
        """Return supported interactions; an empty tuple is explicit."""

        ...


@runtime_checkable
class DriftEstimator(Protocol):
    """Estimate reviewable temporal-regime state without activating it."""

    def estimate(self, request: DriftEstimationRequest) -> tuple[DriftState, ...]:
        """Return drift-state candidates; an empty tuple means no candidate."""

        ...


@runtime_checkable
class ConfidenceEstimator(Protocol):
    """Populate complete confidence vectors without changing component identity or values."""

    def estimate(self, request: ConfidenceEstimationRequest) -> ProfileComponents:
        """Return the final confidence-bearing component bundle."""

        ...


@runtime_checkable
class ReleaseValidator(Protocol):
    """Validate a complete release bundle without statistical quality judgments."""

    @property
    def version(self) -> SemanticVersion:
        """Return the immutable validator version value."""

        ...

    def validate(
        self,
        subject: "ReleaseValidationSubject",
        *,
        report_id: UUID,
        validated_at: UtcDatetime,
    ) -> ValidationReport:
        """Return every structural issue in deterministic order."""

        ...


@runtime_checkable
class ReleaseCatalog(Protocol):
    """Persistence port for atomic, optimistic release-event stream updates."""

    async def get(self, tenant_id: UUID, release_id: UUID) -> ManagedRelease | None:
        """Return one tenant-scoped managed release."""

        ...

    async def list_lineage(self, tenant_id: UUID, lineage_id: UUID) -> tuple[ManagedRelease, ...]:
        """Return every release in one lineage."""

        ...

    async def commit(self, changes: tuple[ReleaseChange, ...]) -> None:
        """Atomically apply optimistic event-stream replacements."""

        ...
