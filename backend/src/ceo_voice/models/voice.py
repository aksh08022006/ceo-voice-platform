"""Versioned voice-profile contracts without extraction behavior."""

from typing import Self
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import (
    FeatureScope,
    Platform,
    VoiceFeatureLayer,
    VoiceProfileStatus,
)


class VoiceFeature(ContractModel):
    """One evidence-backed micro-pattern in a leader's writing behavior.

    Attributes:
        name: Stable, machine-readable feature identifier.
        layer: Linguistic layer to which the feature belongs.
        scope: Whether the feature is globally stable or platform-conditioned.
        platform: Required conceptual target for platform-scoped features.
        value: Typed JSON-compatible feature representation.
        confidence: Calibrated confidence between zero and one.
        evidence_count: Number of independent observations supporting the feature.
        evidence_document_ids: Documents from which supporting evidence was derived.
    """

    name: NonEmptyStr = Field(description="Stable feature identifier.")
    layer: VoiceFeatureLayer = Field(description="Linguistic layer represented by the feature.")
    scope: FeatureScope = Field(description="Global or platform-conditioned feature scope.")
    platform: Platform | None = Field(
        default=None,
        description="Associated platform for a platform-scoped feature.",
    )
    value: JsonValue = Field(description="JSON-compatible feature value.")
    confidence: float = Field(ge=0, le=1, description="Calibrated feature confidence.")
    evidence_count: int = Field(ge=0, description="Number of observations supporting the feature.")
    evidence_document_ids: tuple[UUID, ...] = Field(
        default_factory=tuple,
        description="Source documents that support the feature.",
    )

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        """Keep global and platform-conditioned evidence unambiguous."""

        if self.scope is FeatureScope.PLATFORM and self.platform is None:
            raise ValueError("platform-scoped features require a platform")
        if self.scope is FeatureScope.GLOBAL and self.platform is not None:
            raise ValueError("global features must not specify a platform")
        return self


class VoiceProfile(ContractModel):
    """Auditable, versioned representation of a leader's writing micro-patterns.

    This contract deliberately stores atomic features and provenance rather than only a prose
    summary. Post structure remains outside the profile so future generation can combine voice,
    platform structure, and factual evidence independently.

    Attributes:
        id: Stable identifier for this profile lineage.
        tenant_id: Tenant ownership boundary.
        ceo_id: Leader represented by the profile.
        version: Monotonically increasing profile version.
        status: Review and activation lifecycle state.
        features: Atomic, evidence-backed behavioral features.
        source_snapshot_hash: Digest identifying the complete source evidence snapshot.
        created_at: UTC creation timestamp.
    """

    id: UUID = Field(description="Stable voice-profile lineage identifier.")
    tenant_id: UUID = Field(description="Tenant that owns the profile.")
    ceo_id: UUID = Field(description="Leader represented by the profile.")
    version: int = Field(ge=1, description="Monotonic profile version.")
    status: VoiceProfileStatus = Field(description="Review and activation lifecycle state.")
    features: tuple[VoiceFeature, ...] = Field(
        default_factory=tuple,
        description="Atomic, evidence-backed voice features.",
    )
    source_snapshot_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
        description="SHA-256 digest of the profile's evidence snapshot.",
    )
    created_at: UtcDatetime = Field(description="UTC profile creation timestamp.")
