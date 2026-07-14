"""Deterministic policy audit for governed source catalogs."""

from collections import Counter, defaultdict
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from ceo_voice.acquisition.contracts import (
    CorpusAcquisitionPolicy,
    CorpusAcquisitionReport,
    CorpusAuditFinding,
    SourceCatalogEntry,
    SourceCatalogManifest,
)
from ceo_voice.acquisition.enums import (
    AuditSeverity,
    AuthorshipBasis,
    CorpusContentRole,
    SourceReviewStatus,
)
from ceo_voice.models.enums import Platform


def _canonical_key(entry: SourceCatalogEntry) -> str:
    """Normalize non-semantic URL variation for duplicate detection."""

    parts = urlsplit(str(entry.canonical_url))
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, "")
    )


def _finding(
    code: str,
    severity: AuditSeverity,
    message: str,
    entries: tuple[SourceCatalogEntry, ...] = (),
) -> CorpusAuditFinding:
    return CorpusAuditFinding(
        code=code,
        severity=severity,
        message=message,
        source_ids=tuple(sorted(entry.source_id for entry in entries)),
    )


class CorpusAcquisitionAuditor:
    """Evaluate whether cataloged evidence may proceed to private ingestion."""

    def __init__(self, policy: CorpusAcquisitionPolicy | None = None) -> None:
        self._policy = policy or CorpusAcquisitionPolicy()

    def audit(
        self,
        manifest: SourceCatalogManifest,
        *,
        audited_at: datetime | None = None,
    ) -> CorpusAcquisitionReport:
        """Return a complete readiness decision without fetching source content."""

        now = audited_at or datetime.now(UTC)
        findings: list[CorpusAuditFinding] = []
        findings.extend(self._entry_findings(manifest.entries))
        findings.extend(self._duplicate_findings(manifest.entries))

        eligible = tuple(entry for entry in manifest.entries if self._is_eligible(entry))
        primary = tuple(
            entry for entry in eligible if entry.content_role is CorpusContentRole.PRIMARY_VOICE
        )
        supplementary = tuple(
            entry
            for entry in eligible
            if entry.content_role is CorpusContentRole.SUPPLEMENTARY_VOICE
        )
        factual = tuple(
            entry
            for entry in manifest.entries
            if entry.content_role is CorpusContentRole.FACTUAL_CONTEXT
            and entry.review_status is SourceReviewStatus.APPROVED
            and not entry.requires_authentication
            and not entry.requires_payment
        )
        findings.extend(self._coverage_findings(manifest, eligible, primary, supplementary))

        publication_dates = tuple(
            entry.publication_date for entry in eligible if entry.publication_date is not None
        )
        blocking = any(item.severity is AuditSeverity.BLOCKING for item in findings)
        return CorpusAcquisitionReport(
            tenant_id=manifest.tenant_id,
            leader_id=manifest.leader_id,
            leader_name=manifest.leader_name,
            audited_at=now,
            total_entries=len(manifest.entries),
            approved_entries=sum(
                entry.review_status is SourceReviewStatus.APPROVED for entry in manifest.entries
            ),
            eligible_entries=len(eligible),
            primary_entries=len(primary),
            supplementary_entries=len(supplementary),
            factual_context_entries=len(factual),
            platforms=tuple(sorted({entry.platform for entry in eligible}, key=str)),
            sources=tuple(sorted({entry.source for entry in eligible}, key=str)),
            earliest_publication=min(publication_dates, default=None),
            latest_publication=max(publication_dates, default=None),
            acquisition_ready=not blocking,
            findings=tuple(sorted(findings, key=lambda item: (item.severity, item.code))),
        )

    def _is_eligible(self, entry: SourceCatalogEntry) -> bool:
        reviewed = (
            entry.review_status is SourceReviewStatus.APPROVED
            if self._policy.require_human_review
            else entry.review_status is not SourceReviewStatus.REJECTED
        )
        return (
            reviewed
            and entry.eligible_for_voice_analysis
            and not entry.requires_authentication
            and not entry.requires_payment
            and entry.authorship_basis is not AuthorshipBasis.UNKNOWN
            and entry.content_role is not CorpusContentRole.FACTUAL_CONTEXT
            and (entry.publication_date is not None or not self._policy.require_publication_dates)
        )

    def _entry_findings(self, entries: tuple[SourceCatalogEntry, ...]) -> list[CorpusAuditFinding]:
        findings: list[CorpusAuditFinding] = []
        for entry in entries:
            if (
                entry.eligible_for_voice_analysis
                and entry.review_status is not SourceReviewStatus.APPROVED
            ):
                severity = (
                    AuditSeverity.BLOCKING
                    if self._policy.require_human_review
                    else AuditSeverity.WARNING
                )
                findings.append(
                    _finding(
                        "source_not_approved",
                        severity,
                        "Voice evidence requires approval.",
                        (entry,),
                    )
                )
            if (
                entry.eligible_for_voice_analysis
                and entry.authorship_basis is AuthorshipBasis.UNKNOWN
            ):
                findings.append(
                    _finding(
                        "unknown_authorship",
                        AuditSeverity.BLOCKING,
                        "Voice evidence requires attributable authorship or speech.",
                        (entry,),
                    )
                )
            if entry.eligible_for_voice_analysis and entry.requires_authentication:
                findings.append(
                    _finding(
                        "authentication_required",
                        AuditSeverity.BLOCKING,
                        "Acquisition must not bypass an authentication boundary.",
                        (entry,),
                    )
                )
            if entry.eligible_for_voice_analysis and entry.requires_payment:
                findings.append(
                    _finding(
                        "payment_required",
                        AuditSeverity.BLOCKING,
                        "Acquisition must not bypass a payment boundary.",
                        (entry,),
                    )
                )
            if (
                entry.eligible_for_voice_analysis
                and entry.content_role is CorpusContentRole.FACTUAL_CONTEXT
            ):
                findings.append(
                    _finding(
                        "context_marked_as_voice",
                        AuditSeverity.BLOCKING,
                        "Factual context cannot be analyzed as the leader's voice.",
                        (entry,),
                    )
                )
            if (
                self._policy.require_publication_dates
                and entry.eligible_for_voice_analysis
                and entry.publication_date is None
            ):
                findings.append(
                    _finding(
                        "missing_publication_date",
                        AuditSeverity.BLOCKING,
                        "Voice evidence needs a publication date for recency and drift analysis.",
                        (entry,),
                    )
                )
        return findings

    def _duplicate_findings(
        self, entries: tuple[SourceCatalogEntry, ...]
    ) -> list[CorpusAuditFinding]:
        by_id: dict[str, list[SourceCatalogEntry]] = defaultdict(list)
        by_url: dict[str, list[SourceCatalogEntry]] = defaultdict(list)
        for entry in entries:
            by_id[entry.source_id].append(entry)
            by_url[_canonical_key(entry)].append(entry)
        findings: list[CorpusAuditFinding] = []
        for code, groups, message in (
            ("duplicate_source_id", by_id, "Catalog source identifiers must be unique."),
            ("duplicate_canonical_url", by_url, "Canonical source URLs must be unique."),
        ):
            for duplicates in groups.values():
                if len(duplicates) > 1:
                    findings.append(
                        _finding(code, AuditSeverity.BLOCKING, message, tuple(duplicates))
                    )
        return findings

    def _coverage_findings(
        self,
        manifest: SourceCatalogManifest,
        eligible: tuple[SourceCatalogEntry, ...],
        primary: tuple[SourceCatalogEntry, ...],
        supplementary: tuple[SourceCatalogEntry, ...],
    ) -> list[CorpusAuditFinding]:
        findings: list[CorpusAuditFinding] = []
        if len(eligible) < self._policy.minimum_eligible_documents:
            findings.append(
                _finding(
                    "insufficient_eligible_documents",
                    AuditSeverity.BLOCKING,
                    f"Need at least {self._policy.minimum_eligible_documents} eligible documents; found {len(eligible)}.",
                )
            )
        if len(primary) < self._policy.minimum_primary_documents:
            findings.append(
                _finding(
                    "insufficient_primary_documents",
                    AuditSeverity.BLOCKING,
                    f"Need at least {self._policy.minimum_primary_documents} primary voice documents; found {len(primary)}.",
                )
            )
        platform_counts = Counter(entry.platform for entry in primary)
        qualified_platforms = {
            platform
            for platform, count in platform_counts.items()
            if count >= self._policy.minimum_documents_per_primary_platform
        }
        if len(qualified_platforms) < self._policy.minimum_primary_platforms:
            findings.append(
                _finding(
                    "insufficient_primary_platform_coverage",
                    AuditSeverity.BLOCKING,
                    "Primary voice evidence does not meet the per-platform coverage threshold.",
                )
            )
        for expected in (Platform.X, Platform.LINKEDIN):
            if platform_counts[expected] < self._policy.minimum_documents_per_primary_platform:
                findings.append(
                    _finding(
                        f"insufficient_{expected.value}_coverage",
                        AuditSeverity.WARNING,
                        f"{expected.value} needs {self._policy.minimum_documents_per_primary_platform} primary documents; found {platform_counts[expected]}.",
                    )
                )
        voice_total = len(primary) + len(supplementary)
        supplementary_fraction = len(supplementary) / voice_total if voice_total else 0.0
        if supplementary_fraction > self._policy.maximum_supplementary_fraction:
            findings.append(
                _finding(
                    "supplementary_evidence_dominates",
                    AuditSeverity.BLOCKING,
                    "Supplementary evidence exceeds the configured corpus fraction.",
                )
            )
        if self._policy.require_human_review and (
            manifest.reviewed_at is None or manifest.reviewer_id is None
        ):
            findings.append(
                _finding(
                    "manifest_review_missing",
                    AuditSeverity.BLOCKING,
                    "A reviewed timestamp and reviewer identity are required.",
                )
            )
        return findings
