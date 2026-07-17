"""Fail-closed authorization evaluation with no provider-specific behavior."""

from datetime import UTC, datetime

from ceo_voice.acquisition.enums import ReusePermissionBasis, SourceReviewStatus
from ceo_voice.collector.contracts import (
    AcquisitionDecision,
    AuthorizationReceipt,
    ConnectorCapabilities,
    SourcePolicy,
)


def authorize(policy: SourcePolicy, capabilities: ConnectorCapabilities) -> AuthorizationReceipt:
    """Admit only reviewed, local, explicitly authorized source routes."""

    reasons: list[str] = []
    if policy.connector_name != capabilities.connector_name:
        reasons.append("connector identity does not match source policy")
    if policy.acquisition_method not in capabilities.supported_methods:
        reasons.append("acquisition method is not supported by connector")
    if capabilities.requires_network:
        reasons.append("network connectors require separate policy approval")
    if policy.requires_authentication or capabilities.requires_authentication:
        reasons.append("authenticated collection is not supported")
    if policy.requires_payment or capabilities.requires_payment:
        reasons.append("paid collection is not supported")
    if policy.review_status is not SourceReviewStatus.APPROVED:
        reasons.append("source has not passed human review")
    if policy.reuse_permission_basis is ReusePermissionBasis.UNKNOWN:
        reasons.append("reuse permission basis is unknown")
    if policy.terms_url is None and policy.reuse_permission_basis not in {
        ReusePermissionBasis.SYNTHETIC,
        ReusePermissionBasis.WRITTEN_PERMISSION,
    }:
        reasons.append("terms or explicit permission reference is missing")
    return AuthorizationReceipt(
        source_id=policy.source_id,
        connector_name=policy.connector_name,
        decision=AcquisitionDecision.BLOCK if reasons else AcquisitionDecision.ADMIT,
        reasons=tuple(reasons),
        decided_at=datetime.now(UTC),
    )
