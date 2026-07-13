"""Leader identity contracts."""

from uuid import UUID

from pydantic import Field

from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime


class CEOIdentity(ContractModel):
    """Tenant-scoped identity of a leader whose voice is modeled.

    Attributes:
        id: Stable platform identifier for the leader.
        tenant_id: Owner boundary used for authorization and data isolation.
        display_name: Human-readable name shown in operator workflows.
        external_reference: Optional identifier in an upstream identity system.
        created_at: UTC timestamp at which the identity was registered.
    """

    id: UUID = Field(description="Stable platform identifier for the leader.")
    tenant_id: UUID = Field(description="Tenant that owns this leader identity.")
    display_name: NonEmptyStr = Field(description="Human-readable leader name.")
    external_reference: str | None = Field(
        default=None,
        description="Optional identifier supplied by an external identity system.",
    )
    created_at: UtcDatetime = Field(description="UTC registration timestamp.")
