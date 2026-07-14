"""Governed identity and profile-lineage contracts for the HVM domain."""

from uuid import UUID

from pydantic import Field

from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime
from ceo_voice.voice.enums import TargetIdentityType
from ceo_voice.voice.primitives import SemanticVersion


class VoiceIdentity(ContractModel):
    """Tenant-scoped declaration of the writing identity being represented.

    The target type is a governance assertion, never a style-derived conclusion. Personal
    authorship and an approved executive brand therefore cannot be silently merged.
    """

    id: UUID = Field(description="Stable target writing-identity identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    leader_id: UUID = Field(description="Leader associated with the governed identity.")
    display_name: NonEmptyStr = Field(description="Operator-facing identity name.")
    target_type: TargetIdentityType = Field(description="Declared authorship semantics.")
    policy_version: SemanticVersion = Field(description="Identity-governance policy version.")
    created_at: UtcDatetime = Field(description="UTC identity creation time.")


class ProfileLineage(ContractModel):
    """Stable lineage under which immutable HVM releases evolve."""

    id: UUID = Field(description="Stable profile-lineage identifier.")
    tenant_id: UUID = Field(description="Tenant ownership boundary.")
    voice_identity_id: UUID = Field(description="Governed target writing identity.")
    lineage_policy_version: SemanticVersion = Field(
        description="Policy that governs versioning, review, and activation."
    )
    created_at: UtcDatetime = Field(description="UTC lineage creation time.")
