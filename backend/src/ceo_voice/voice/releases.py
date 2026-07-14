"""Sealed HVM releases, structural reports, lifecycle events, and retrieval projections."""

from datetime import datetime
from typing import Self, cast
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime, normalize_utc_datetime
from ceo_voice.utils.hashing import sha256_text
from ceo_voice.utils.json import dumps_json
from ceo_voice.voice.components import (
    ExplicitPreference,
    NegativeConstraint,
    ProfileComponents,
    Prototype,
)
from ceo_voice.voice.enums import (
    ReleaseEventType,
    ReleaseStatus,
    RetrievalProjectionType,
    ValidationCode,
    ValidationSeverity,
)
from ceo_voice.voice.evidence import EvidenceSnapshotReference
from ceo_voice.voice.observations import ObservationReference
from ceo_voice.voice.primitives import (
    FeatureReference,
    RegistryReference,
    SemanticVersion,
    Sha256Digest,
)


class HVMRelease(ContractModel):
    """Sealed, reproducible Hierarchical Voice Model payload.

    Lifecycle state is intentionally absent from this object. Creation, validation, approval,
    activation, supersession, and rollback are immutable events around the sealed payload, so no
    release content is rewritten when operational state changes.
    """

    id: UUID = Field(description="Stable immutable release identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Governed target writing identity.")
    lineage_id: UUID = Field(description="Profile lineage containing the release.")
    version: int = Field(ge=1, description="Monotonic release version within the lineage.")
    previous_release_id: UUID | None = Field(
        default=None, description="Immediate predecessor release when version is greater than one."
    )
    registry: RegistryReference = Field(description="Pinned feature-registry snapshot.")
    evidence_snapshot: EvidenceSnapshotReference = Field(description="Pinned evidence manifest.")
    observation_references: tuple[ObservationReference, ...] = Field(
        min_length=1, description="Content-addressed observations admitted to the build."
    )
    components: ProfileComponents = Field(description="Aggregates and modeled components.")
    prototypes: tuple[Prototype, ...] = Field(default_factory=tuple)
    negative_constraints: tuple[NegativeConstraint, ...] = Field(default_factory=tuple)
    explicit_preferences: tuple[ExplicitPreference, ...] = Field(default_factory=tuple)
    validation_report_id: UUID = Field(description="Structural validation report pinned at build.")
    compiler_version: SemanticVersion = Field(description="Exact orchestration contract version.")
    created_at: UtcDatetime = Field(description="UTC release sealing time.")

    @model_validator(mode="after")
    def validate_release(self) -> Self:
        """Enforce lineage shape, unique IDs, and component ownership."""

        if self.version == 1 and self.previous_release_id is not None:
            raise ValueError("first release must not reference a predecessor")
        if self.version > 1 and self.previous_release_id is None:
            raise ValueError("later releases require an immediate predecessor")
        if not self.components.aggregates:
            raise ValueError("an HVM release requires at least one aggregate")
        if not self.components.residuals:
            raise ValueError("an HVM release requires at least one leader residual")
        observation_ids = tuple(item.observation_id for item in self.observation_references)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("release observation IDs must be unique")

        component_groups = (
            self.components.aggregates,
            self.components.residuals,
            self.components.conditional_residuals,
            self.components.interactions,
            self.components.drift_states,
            self.prototypes,
            self.negative_constraints,
            self.explicit_preferences,
        )
        identifiers = tuple(component.id for group in component_groups for component in group)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("release component IDs must be globally unique")
        components = tuple(component for group in component_groups for component in group)
        if any(component.tenant_id != self.tenant_id for component in components):
            raise ValueError("release components must share the release tenant")
        if any(component.voice_identity_id != self.voice_identity_id for component in components):
            raise ValueError("release components must share the release identity")
        return self

    @property
    def content_hash(self) -> str:
        """Return a deterministic digest of the complete sealed release payload."""

        payload = cast(JsonValue, self.model_dump(mode="json"))
        return sha256_text(dumps_json(payload))


class ValidationIssue(ContractModel):
    """One stable, machine-readable structural validation finding."""

    code: ValidationCode = Field(description="Validation category.")
    severity: ValidationSeverity = Field(description="Error or warning severity.")
    path: NonEmptyStr = Field(description="Stable subject path within the release bundle.")
    message: NonEmptyStr = Field(description="Safe human-readable explanation.")
    reference_ids: tuple[UUID, ...] = Field(
        default_factory=tuple, description="Related immutable domain identifiers."
    )


class ValidationReport(ContractModel):
    """Immutable structural-validation result for one exact release payload."""

    id: UUID = Field(description="Stable validation report identifier.")
    release_id: UUID = Field(description="Validated HVM release.")
    release_content_hash: Sha256Digest = Field(description="Validated release content digest.")
    validator_version: SemanticVersion = Field(description="Exact structural-validator version.")
    issues: tuple[ValidationIssue, ...] = Field(
        default_factory=tuple, description="Ordered structural findings."
    )
    validated_at: UtcDatetime = Field(description="UTC validation completion time.")

    def is_valid(self) -> bool:
        """Return whether no structural error was found."""

        return not any(issue.severity is ValidationSeverity.ERROR for issue in self.issues)


class CompiledProfile(ContractModel):
    """Successful compiler output pairing a sealed release with its exact validation report."""

    release: HVMRelease = Field(description="Structurally valid sealed HVM release.")
    validation_report: ValidationReport = Field(description="Pinned structural validation report.")

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        """Require exact report identity, content hash, and successful validation."""

        if self.validation_report.id != self.release.validation_report_id:
            raise ValueError("compiled release and validation report IDs do not match")
        if self.validation_report.release_id != self.release.id:
            raise ValueError("validation report references a different release")
        if self.validation_report.release_content_hash != self.release.content_hash:
            raise ValueError("validation report content hash does not match the release")
        if not self.validation_report.is_valid():
            raise ValueError("compiled profile requires a structurally valid report")
        return self


class ReleaseEvent(ContractModel):
    """Append-only lifecycle fact for one sealed release."""

    id: UUID = Field(description="Stable lifecycle-event identifier.")
    release_id: UUID = Field(description="Release affected by the event.")
    sequence: int = Field(ge=1, description="Monotonic sequence within the release event stream.")
    event_type: ReleaseEventType = Field(description="Lifecycle fact type.")
    actor_id: UUID = Field(description="Authorized actor or service identity.")
    occurred_at: UtcDatetime = Field(description="UTC event time.")
    validation_report_id: UUID | None = Field(
        default=None, description="Report associated with validation completion."
    )
    related_release_id: UUID | None = Field(
        default=None, description="Predecessor, successor, or rollback target when applicable."
    )

    @model_validator(mode="after")
    def validate_event_links(self) -> Self:
        """Require event-specific references and reject ambiguous extras."""

        validation_events = {
            ReleaseEventType.VALIDATION_PASSED,
            ReleaseEventType.VALIDATION_FAILED,
        }
        related_events = {
            ReleaseEventType.SUPERSEDED,
            ReleaseEventType.ROLLED_BACK_TO,
        }
        if (self.event_type in validation_events) != (self.validation_report_id is not None):
            raise ValueError("validation completion events require exactly one report reference")
        if (self.event_type in related_events) != (self.related_release_id is not None):
            raise ValueError("supersession and rollback events require a related release")
        if self.related_release_id == self.release_id:
            raise ValueError("a release event cannot relate a release to itself")
        return self


_ALLOWED_TRANSITIONS: dict[ReleaseStatus, dict[ReleaseEventType, ReleaseStatus]] = {
    ReleaseStatus.BUILDING: {
        ReleaseEventType.VALIDATION_STARTED: ReleaseStatus.VALIDATING,
        ReleaseEventType.WITHDRAWN: ReleaseStatus.WITHDRAWN,
    },
    ReleaseStatus.VALIDATING: {
        ReleaseEventType.VALIDATION_PASSED: ReleaseStatus.NEEDS_REVIEW,
        ReleaseEventType.VALIDATION_FAILED: ReleaseStatus.REJECTED,
    },
    ReleaseStatus.NEEDS_REVIEW: {
        ReleaseEventType.APPROVED: ReleaseStatus.APPROVED,
        ReleaseEventType.WITHDRAWN: ReleaseStatus.WITHDRAWN,
    },
    ReleaseStatus.APPROVED: {
        ReleaseEventType.ACTIVATED: ReleaseStatus.ACTIVE,
        ReleaseEventType.WITHDRAWN: ReleaseStatus.WITHDRAWN,
    },
    ReleaseStatus.ACTIVE: {
        ReleaseEventType.SUPERSEDED: ReleaseStatus.SUPERSEDED,
        ReleaseEventType.WITHDRAWN: ReleaseStatus.WITHDRAWN,
    },
    ReleaseStatus.SUPERSEDED: {
        ReleaseEventType.ROLLED_BACK_TO: ReleaseStatus.ACTIVE,
    },
    ReleaseStatus.REJECTED: {},
    ReleaseStatus.WITHDRAWN: {},
}


def derive_release_status(
    events: tuple[ReleaseEvent, ...], *, as_of: datetime | None = None
) -> ReleaseStatus | None:
    """Replay lifecycle events and return state at an optional point in time."""

    selected = tuple(event for event in events if as_of is None or event.occurred_at <= as_of)
    if not selected:
        return None
    if selected[0].event_type is not ReleaseEventType.CREATED:
        raise ValueError("release event stream must begin with creation")
    status = ReleaseStatus.BUILDING
    for event in selected[1:]:
        transition = _ALLOWED_TRANSITIONS[status].get(event.event_type)
        if transition is None:
            raise ValueError(f"event {event.event_type} is invalid from release state {status}")
        status = transition
    return status


class ManagedRelease(ContractModel):
    """Sealed HVM payload plus an immutable lifecycle event stream."""

    release: HVMRelease = Field(description="Sealed HVM payload.")
    events: tuple[ReleaseEvent, ...] = Field(min_length=1, description="Ordered lifecycle facts.")
    validation_report: ValidationReport | None = Field(
        default=None, description="Recorded structural report after validation completes."
    )

    @model_validator(mode="after")
    def validate_history(self) -> Self:
        """Require a consistent, replayable, append-only event stream."""

        if any(event.release_id != self.release.id for event in self.events):
            raise ValueError("release events must reference the managed release")
        event_ids = tuple(event.id for event in self.events)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("release event IDs must be unique")
        sequences = tuple(event.sequence for event in self.events)
        if sequences != tuple(range(1, len(self.events) + 1)):
            raise ValueError("release event sequences must be contiguous from one")
        times = tuple(event.occurred_at for event in self.events)
        if times != tuple(sorted(times)):
            raise ValueError("release event times must be nondecreasing")
        derive_release_status(self.events)
        if self.validation_report is not None:
            if self.validation_report.id != self.release.validation_report_id:
                raise ValueError("managed validation report does not match the release")
            if self.validation_report.release_content_hash != self.release.content_hash:
                raise ValueError("managed validation report has a stale release hash")
        completion_events = tuple(
            event
            for event in self.events
            if event.event_type
            in {ReleaseEventType.VALIDATION_PASSED, ReleaseEventType.VALIDATION_FAILED}
        )
        if bool(completion_events) != (self.validation_report is not None):
            raise ValueError("validation completion and report presence must agree")
        return self

    @property
    def revision(self) -> int:
        """Return the optimistic-concurrency revision of the event stream."""

        return len(self.events)

    @property
    def status(self) -> ReleaseStatus:
        """Return current state derived from immutable lifecycle facts."""

        status = derive_release_status(self.events)
        if status is None:  # pragma: no cover - forbidden by model invariants
            raise ValueError("managed release has no lifecycle state")
        return status

    def status_at(self, as_of: datetime) -> ReleaseStatus | None:
        """Return lifecycle state known at a point in time."""

        return derive_release_status(self.events, as_of=normalize_utc_datetime(as_of))


class ReleaseChange(ContractModel):
    """Optimistic, atomically persisted release-stream replacement."""

    record: ManagedRelease = Field(description="New immutable managed-release snapshot.")
    expected_revision: int | None = Field(
        default=None,
        ge=0,
        description="Previous event-stream revision; null means create only.",
    )


class RetrievalProjection(ContractModel):
    """Rebuildable typed query projection derived from one HVM release."""

    id: UUID = Field(description="Stable projection identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Target writing identity.")
    release_id: UUID = Field(description="Source HVM release.")
    release_content_hash: Sha256Digest = Field(description="Source release content digest.")
    projection_type: RetrievalProjectionType = Field(description="Projection query purpose.")
    indexed_features: tuple[FeatureReference, ...] = Field(
        default_factory=tuple, description="Feature definitions indexed by the projection."
    )
    indexed_component_ids: tuple[UUID, ...] = Field(
        default_factory=tuple, description="Release components indexed by the projection."
    )
    projection_version: SemanticVersion = Field(description="Projection contract version.")
    projection_hash: Sha256Digest = Field(description="Materialized projection content digest.")
    materialized_at: UtcDatetime = Field(description="UTC materialization time.")

    @model_validator(mode="after")
    def validate_indexes(self) -> Self:
        """Reject ambiguous duplicate index references."""

        if len(self.indexed_features) != len(set(self.indexed_features)):
            raise ValueError("projection feature references must be unique")
        if len(self.indexed_component_ids) != len(set(self.indexed_component_ids)):
            raise ValueError("projection component IDs must be unique")
        return self
