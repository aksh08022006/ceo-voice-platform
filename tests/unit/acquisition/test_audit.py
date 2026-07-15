"""Governed source-catalog audit tests."""

from datetime import UTC, datetime
from uuid import UUID

from ceo_voice.acquisition import (
    AcquisitionMethod,
    AuthorshipBasis,
    CorpusAcquisitionAuditor,
    CorpusAcquisitionPolicy,
    CorpusContentRole,
    ReusePermissionBasis,
    SourceCatalogEntry,
    SourceCatalogManifest,
    SourceReviewStatus,
)
from ceo_voice.models.enums import DocumentSourceType, DocumentType, Platform

NOW = datetime(2026, 7, 14, tzinfo=UTC)


def _entry(
    index: int,
    platform: Platform,
    **updates: object,
) -> SourceCatalogEntry:
    values: dict[str, object] = {
        "source_id": f"source-{index}",
        "source": DocumentSourceType.X if platform is Platform.X else DocumentSourceType.LINKEDIN,
        "platform": platform,
        "document_type": DocumentType.SOCIAL_POST,
        "canonical_url": f"https://example.com/{platform.value}/{index}",
        "title": f"Catalog item {index}",
        "publisher": "Example",
        "publication_date": NOW,
        "acquisition_method": AcquisitionMethod.AUTHORIZED_EXPORT,
        "review_status": SourceReviewStatus.APPROVED,
        "authorship_basis": AuthorshipBasis.FIRST_PARTY_ACCOUNT,
        "content_role": CorpusContentRole.PRIMARY_VOICE,
        "eligible_for_voice_analysis": True,
        "reuse_permission_basis": ReusePermissionBasis.ACCOUNT_AUTHORIZATION,
        "access_notes": "Authorized account export supplied by the operator.",
    }
    values.update(updates)
    return SourceCatalogEntry.model_validate(values)


def _manifest(*entries: SourceCatalogEntry, reviewed: bool = True) -> SourceCatalogManifest:
    return SourceCatalogManifest(
        tenant_id=UUID(int=1),
        leader_id=UUID(int=2),
        leader_name="Example Leader",
        entries=entries,
        created_at=NOW,
        reviewed_at=NOW if reviewed else None,
        reviewer_id=UUID(int=3) if reviewed else None,
    )


def test_balanced_reviewed_catalog_is_acquisition_ready() -> None:
    entries = tuple(_entry(index, Platform.X) for index in range(10)) + tuple(
        _entry(index + 10, Platform.LINKEDIN) for index in range(10)
    )

    report = CorpusAcquisitionAuditor().audit(_manifest(*entries), audited_at=NOW)

    assert report.acquisition_ready is True
    assert report.eligible_entries == 20
    assert report.primary_entries == 20
    assert report.platforms == (Platform.LINKEDIN, Platform.X)
    assert report.earliest_publication == NOW
    assert report.latest_publication == NOW
    assert report.findings == ()


def test_audit_exposes_access_attribution_duplicate_and_coverage_failures() -> None:
    pending = _entry(1, Platform.X, review_status=SourceReviewStatus.PENDING)
    unknown = _entry(2, Platform.X, authorship_basis=AuthorshipBasis.UNKNOWN)
    unlicensed = _entry(7, Platform.X, reuse_permission_basis=ReusePermissionBasis.UNKNOWN)
    authenticated = _entry(3, Platform.X, requires_authentication=True)
    paid = _entry(4, Platform.X, requires_payment=True)
    context = _entry(5, Platform.X, content_role=CorpusContentRole.FACTUAL_CONTEXT)
    undated = _entry(6, Platform.X, publication_date=None)
    duplicate = _entry(
        1,
        Platform.X,
        canonical_url="https://example.com/x/1/",
        content_role=CorpusContentRole.SUPPLEMENTARY_VOICE,
    )

    report = CorpusAcquisitionAuditor().audit(
        _manifest(
            pending,
            unknown,
            unlicensed,
            authenticated,
            paid,
            context,
            undated,
            duplicate,
            reviewed=False,
        ),
        audited_at=NOW,
    )

    codes = {finding.code for finding in report.findings}
    assert report.acquisition_ready is False
    assert report.eligible_entries == 1
    assert report.supplementary_entries == 1
    assert report.factual_context_entries == 1
    assert {
        "source_not_approved",
        "unknown_authorship",
        "reuse_permission_missing",
        "authentication_required",
        "payment_required",
        "context_marked_as_voice",
        "missing_publication_date",
        "duplicate_source_id",
        "duplicate_canonical_url",
        "insufficient_eligible_documents",
        "insufficient_primary_documents",
        "insufficient_primary_platform_coverage",
        "insufficient_x_coverage",
        "insufficient_linkedin_coverage",
        "supplementary_evidence_dominates",
        "manifest_review_missing",
    } <= codes


def test_policy_can_support_a_non_production_discovery_audit() -> None:
    policy = CorpusAcquisitionPolicy(
        minimum_eligible_documents=1,
        minimum_primary_documents=1,
        minimum_primary_platforms=1,
        minimum_documents_per_primary_platform=1,
        maximum_supplementary_fraction=1,
        require_publication_dates=False,
        require_human_review=False,
    )
    entry = _entry(
        1,
        Platform.X,
        review_status=SourceReviewStatus.PENDING,
        publication_date=None,
    )

    report = CorpusAcquisitionAuditor(policy).audit(
        _manifest(entry, reviewed=False), audited_at=NOW
    )

    assert report.acquisition_ready is True
    assert report.approved_entries == 0
    assert report.eligible_entries == 1
    assert report.earliest_publication is None
    assert {finding.code for finding in report.findings} == {
        "insufficient_linkedin_coverage",
        "source_not_approved",
    }
