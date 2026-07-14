"""Provider-neutral query and response contracts for future HVM retrieval."""

from datetime import datetime
from typing import Protocol, Self, runtime_checkable
from uuid import UUID

from pydantic import Field, model_validator

from ceo_voice.models.base import ContractModel, UtcDatetime
from ceo_voice.voice.components import ConfidenceVector
from ceo_voice.voice.enums import (
    DecisionState,
    DownstreamPermission,
    ResolutionSource,
    ResolvedComponentKind,
    VoiceDimension,
    VoiceQueryKind,
)
from ceo_voice.voice.primitives import FeatureReference, Sha256Digest, VoiceContext
from ceo_voice.voice.values import VoiceValue


class VoiceProfileQuery(ContractModel):
    """Typed request for context-resolved HVM behavior without exposing storage internals."""

    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Target writing identity.")
    release_id: UUID | None = Field(
        default=None, description="Exact release; omit only for point-in-time resolution."
    )
    as_of: UtcDatetime | None = Field(
        default=None, description="Point-in-time active release lookup."
    )
    kind: VoiceQueryKind = Field(description="Stable retrieval intent.")
    context: VoiceContext = Field(description="Requested language and communication context.")
    dimensions: tuple[VoiceDimension, ...] = Field(
        default_factory=tuple, description="Optional dimension filter."
    )
    features: tuple[FeatureReference, ...] = Field(
        default_factory=tuple, description="Optional exact feature filter."
    )
    downstream_use: DownstreamPermission = Field(description="Intended consumer use.")
    minimum_decision_state: DecisionState = Field(description="Minimum component authority.")
    include_evidence_references: bool = Field(
        default=False, description="Whether response may include evidence-unit identifiers."
    )
    maximum_components: int = Field(ge=1, le=500, description="Bounded response size.")

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        """Require exactly one release-resolution strategy and unique filters."""

        if (self.release_id is None) == (self.as_of is None):
            raise ValueError("query requires exactly one of release_id or as_of")
        if len(self.dimensions) != len(set(self.dimensions)):
            raise ValueError("query dimensions must be unique")
        if len(self.features) != len(set(self.features)):
            raise ValueError("query feature references must be unique")
        return self


class ResolutionStep(ContractModel):
    """Explainable feature-level inheritance or fallback step."""

    order: int = Field(ge=1, description="One-based resolution order.")
    source: ResolutionSource = Field(description="Selected inheritance source.")
    component_id: UUID | None = Field(default=None, description="Source component when one exists.")
    applied: bool = Field(description="Whether the step contributed to the resolved value.")


class ResolvedVoiceComponent(ContractModel):
    """Public, context-resolved feature result independent of HVM storage layout."""

    component_id: UUID = Field(description="Resolved source component identifier.")
    kind: ResolvedComponentKind = Field(description="Public component category.")
    feature: FeatureReference = Field(description="Exact resolved feature definition.")
    value: VoiceValue = Field(description="Typed resolved target or constraint.")
    confidence: ConfidenceVector = Field(description="Complete component uncertainty.")
    decision_state: DecisionState = Field(description="Maximum permitted downstream use.")
    resolution_trace: tuple[ResolutionStep, ...] = Field(
        min_length=1, description="Ordered inheritance and fallback decisions."
    )
    evidence_unit_ids: tuple[UUID, ...] = Field(
        default_factory=tuple, description="Optional governed evidence references."
    )

    @model_validator(mode="after")
    def validate_trace(self) -> Self:
        """Require contiguous trace order and unique evidence references."""

        orders = tuple(step.order for step in self.resolution_trace)
        if orders != tuple(range(1, len(orders) + 1)):
            raise ValueError("resolution trace steps must be contiguous from one")
        if len(self.evidence_unit_ids) != len(set(self.evidence_unit_ids)):
            raise ValueError("resolved evidence-unit references must be unique")
        return self


class VoiceProfileQueryResult(ContractModel):
    """Release-pinned result returned by a future HVM retrieval implementation."""

    query_id: UUID = Field(description="Stable query trace identifier.")
    release_id: UUID = Field(description="Exact HVM release used.")
    release_content_hash: Sha256Digest = Field(description="Source release digest.")
    components: tuple[ResolvedVoiceComponent, ...] = Field(description="Resolved results.")
    resolved_at: UtcDatetime = Field(description="UTC resolution time.")


@runtime_checkable
class VoiceProfileRetriever(Protocol):
    """Port implemented later by profile and evidence retrieval infrastructure."""

    async def query(self, request: VoiceProfileQuery) -> VoiceProfileQueryResult:
        """Resolve typed voice components without exposing storage or ranking details."""

        ...


@runtime_checkable
class PointInTimeReleaseResolver(Protocol):
    """Narrow lookup port used by future retrieval implementations."""

    async def active_at(self, tenant_id: UUID, lineage_id: UUID, *, as_of: datetime) -> UUID | None:
        """Return the active release identifier at a point in time."""

        ...
