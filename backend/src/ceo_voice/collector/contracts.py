"""Immutable contracts used by the lawful local collector."""

from enum import StrEnum

from pydantic import Field, HttpUrl

from ceo_voice.acquisition.enums import AcquisitionMethod, ReusePermissionBasis, SourceReviewStatus
from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime


class AcquisitionDecision(StrEnum):
    """Outcome of evaluating an input source before any content is read."""

    ADMIT = "admit"
    BLOCK = "block"


class ConnectorCapabilities(ContractModel):
    """Source-independent capabilities declared before a connector may run."""

    connector_name: NonEmptyStr
    supported_methods: tuple[AcquisitionMethod, ...]
    supports_cursor: bool = True
    supports_incremental: bool = True
    requires_network: bool = False
    requires_authentication: bool = False
    requires_payment: bool = False


class SourcePolicy(ContractModel):
    """Content-free policy declaration supplied by the operator."""

    source_id: NonEmptyStr
    connector_name: NonEmptyStr
    acquisition_method: AcquisitionMethod
    reuse_permission_basis: ReusePermissionBasis
    terms_url: HttpUrl | None = None
    license_url: HttpUrl | None = None
    requires_authentication: bool = False
    requires_payment: bool = False
    review_status: SourceReviewStatus = SourceReviewStatus.PENDING
    written_permission_reference: str | None = None


class AuthorizationReceipt(ContractModel):
    """Content-free immutable record of a source admission decision."""

    source_id: NonEmptyStr
    connector_name: NonEmptyStr
    decision: AcquisitionDecision
    reasons: tuple[NonEmptyStr, ...] = ()
    decided_at: UtcDatetime


class Checkpoint(ContractModel):
    """Resumable connector state, stored only after a successful output write."""

    source_id: NonEmptyStr
    cursor: str | None = None
    completed_at: UtcDatetime
    records_seen: int = Field(ge=0)
    records_written: int = Field(ge=0)


class CollectedVersion(ContractModel):
    """Fingerprint state for one immutable platform post version."""

    platform: NonEmptyStr
    source_post_id: NonEmptyStr
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    version: int = Field(ge=1)
    observed_at: UtcDatetime


class CollectionReport(ContractModel):
    """Content-free collection summary."""

    source_id: NonEmptyStr
    fetched: int = Field(ge=0)
    admitted: int = Field(ge=0)
    blocked: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    edited_versions: int = Field(ge=0)
    output_path: str | None = None
