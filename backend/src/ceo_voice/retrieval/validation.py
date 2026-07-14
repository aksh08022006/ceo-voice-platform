"""Cross-artifact invariants enforced before retrieval candidate construction."""

from ceo_voice.core.exceptions import RetrievalValidationError
from ceo_voice.retrieval.contracts import RetrievalInput
from ceo_voice.virality import PublicationStatus
from ceo_voice.voice import ReleaseStatus


def validate_retrieval_input(value: RetrievalInput) -> None:
    """Reject unpinned, cross-tenant, cross-platform, or inactive knowledge."""

    request, context = value.request, value.context
    voice_release = value.voice_profile.managed_release.release
    structural_release = value.virality_profile.publication.release
    checks = (
        (request.request_id == context.intent.request_id, "request_context_mismatch"),
        (
            request.tenant_id == context.intent.tenant_id == voice_release.tenant_id,
            "tenant_mismatch",
        ),
        (request.ceo_id == context.intent.leader_id, "leader_mismatch"),
        (
            request.platform == context.intent.platform == context.platform.platform,
            "platform_mismatch",
        ),
        (context.voice.release_id == voice_release.id, "voice_release_mismatch"),
        (context.voice.release_content_hash == voice_release.content_hash, "voice_hash_mismatch"),
        (context.voice.release_version == voice_release.version, "voice_version_mismatch"),
        (context.virality.release_id == structural_release.id, "virality_release_mismatch"),
        (
            context.virality.release_content_hash == structural_release.content_hash,
            "virality_hash_mismatch",
        ),
        (context.virality.platform == request.platform, "virality_platform_mismatch"),
        (structural_release.tenant_id == request.tenant_id, "virality_tenant_mismatch"),
        (
            value.voice_profile.managed_release.status is ReleaseStatus.ACTIVE,
            "voice_release_inactive",
        ),
        (
            value.virality_profile.publication.status is PublicationStatus.ACTIVE,
            "virality_release_inactive",
        ),
    )
    for valid, reason in checks:
        if not valid:
            raise RetrievalValidationError(
                "retrieval input artifacts are incompatible",
                details={"reason": reason},
            )
