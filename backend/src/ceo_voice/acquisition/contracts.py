"""Immutable contracts for source discovery, review, and corpus readiness."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, HttpUrl

from ceo_voice.acquisition.enums import (
    AcquisitionMethod,
    AuditSeverity,
    AuthorshipBasis,
    CorpusContentRole,
    SourceReviewStatus,
)
from ceo_voice.models.base import ContractModel, NonEmptyStr, UtcDatetime
from ceo_voice.models.enums import DocumentSourceType, DocumentType, Platform


class SourceCatalogEntry(ContractModel):
    """Provenance and governance record for one discoverable source item.

    The contract deliberately stores no source text. Content is acquired into an ignored,
    access-controlled workspace only after this record passes review.
    """

    source_id: NonEmptyStr = Field(description="Stable catalog identifier, not a provider secret.")
    source: DocumentSourceType
    platform: Platform
    document_type: DocumentType
    canonical_url: HttpUrl
    title: NonEmptyStr
    publisher: NonEmptyStr
    publication_date: UtcDatetime | None = None
    acquisition_method: AcquisitionMethod
    review_status: SourceReviewStatus = SourceReviewStatus.PENDING
    authorship_basis: AuthorshipBasis = AuthorshipBasis.UNKNOWN
    content_role: CorpusContentRole
    requires_authentication: bool = False
    requires_payment: bool = False
    eligible_for_voice_analysis: bool = False
    attribution_notes: NonEmptyStr | None = None
    access_notes: NonEmptyStr
    content_fingerprint: NonEmptyStr | None = Field(
        default=None,
        description="Hash of privately acquired content for incremental processing; never content.",
    )
    captured_at: UtcDatetime | None = None


class SourceCatalogManifest(ContractModel):
    """Versioned discovery catalog for one leader and tenant."""

    schema_version: Literal["1.0"] = "1.0"
    tenant_id: UUID
    leader_id: UUID
    leader_name: NonEmptyStr
    entries: tuple[SourceCatalogEntry, ...] = Field(min_length=1)
    created_at: UtcDatetime
    reviewed_at: UtcDatetime | None = None
    reviewer_id: UUID | None = None


class CorpusAcquisitionPolicy(ContractModel):
    """Explicit evidence thresholds required before profile construction."""

    minimum_eligible_documents: int = Field(default=20, ge=1)
    minimum_primary_documents: int = Field(default=10, ge=1)
    minimum_primary_platforms: int = Field(default=2, ge=1)
    minimum_documents_per_primary_platform: int = Field(default=5, ge=1)
    maximum_supplementary_fraction: float = Field(default=0.5, ge=0, le=1)
    require_publication_dates: bool = True
    require_human_review: bool = True


class CorpusAuditFinding(ContractModel):
    """One traceable corpus governance or coverage finding."""

    code: NonEmptyStr
    severity: AuditSeverity
    message: NonEmptyStr
    source_ids: tuple[NonEmptyStr, ...] = ()


class CorpusAcquisitionReport(ContractModel):
    """Deterministic decision over a source catalog and acquisition policy."""

    tenant_id: UUID
    leader_id: UUID
    leader_name: NonEmptyStr
    audited_at: UtcDatetime
    total_entries: int = Field(ge=1)
    approved_entries: int = Field(ge=0)
    eligible_entries: int = Field(ge=0)
    primary_entries: int = Field(ge=0)
    supplementary_entries: int = Field(ge=0)
    factual_context_entries: int = Field(ge=0)
    platforms: tuple[Platform, ...]
    sources: tuple[DocumentSourceType, ...]
    earliest_publication: datetime | None
    latest_publication: datetime | None
    acquisition_ready: bool
    findings: tuple[CorpusAuditFinding, ...]
