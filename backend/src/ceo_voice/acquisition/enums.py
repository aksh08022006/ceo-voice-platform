"""Controlled vocabulary for governed corpus acquisition."""

from enum import StrEnum


class AcquisitionMethod(StrEnum):
    """How source content may lawfully enter the private ingestion workspace."""

    OFFICIAL_API = "official_api"
    AUTHORIZED_EXPORT = "authorized_export"
    PUBLIC_WEB = "public_web"
    PUBLIC_TRANSCRIPT = "public_transcript"
    MANUAL_CAPTURE = "manual_capture"


class SourceReviewStatus(StrEnum):
    """Human review state for one catalog entry."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReusePermissionBasis(StrEnum):
    """Recorded authority for retaining and analyzing source content."""

    UNKNOWN = "unknown"
    ACCOUNT_AUTHORIZATION = "account_authorization"
    PROVIDER_AGREEMENT = "provider_agreement"
    EXPLICIT_LICENSE = "explicit_license"
    WRITTEN_PERMISSION = "written_permission"
    PUBLIC_DOMAIN = "public_domain"
    SYNTHETIC = "synthetic"


class AuthorshipBasis(StrEnum):
    """Evidence supporting attribution of words to the target leader."""

    FIRST_PARTY_ACCOUNT = "first_party_account"
    NAMED_BYLINE = "named_byline"
    VERIFIED_SPEAKER = "verified_speaker"
    ATTRIBUTED_QUOTE = "attributed_quote"
    UNKNOWN = "unknown"


class CorpusContentRole(StrEnum):
    """Permitted analytical use of an acquired source."""

    PRIMARY_VOICE = "primary_voice"
    SUPPLEMENTARY_VOICE = "supplementary_voice"
    FACTUAL_CONTEXT = "factual_context"


class AuditSeverity(StrEnum):
    """Operational impact of a corpus audit finding."""

    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"
