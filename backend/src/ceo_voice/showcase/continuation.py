"""Encrypted, bounded continuation snapshots for stateless serverless instances.

The browser holds an opaque bearer token, never a serialized Python object. Large immutable
profiles stay on the server and are resolved only by their exact release IDs and content hashes.
This is single-editor continuation, not a shared database or a global latest-revision registry.
"""

import zlib
from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from pydantic import Field, ValidationError

from ceo_voice.core.exceptions import ApplicationError, ConfigurationError
from ceo_voice.evaluation import EvaluationReport
from ceo_voice.integration import IntegrationOutcome
from ceo_voice.models.base import ContractModel
from ceo_voice.revoice import EditedDraft, ReVoicedDraft
from ceo_voice.services.published_profiles import PublishedProfileBundle

from .catalog import ShowcaseProfile
from .service import WorkflowSession

MAX_TOKEN_CHARACTERS = 2_000_000
MAX_SNAPSHOT_BYTES = 8_000_000


class ContinuationError(ApplicationError):
    code = "workflow_continuation_error"


class _Snapshot(ContractModel):
    schema_version: Literal["1"] = "1"
    session_id: UUID
    profile_slug: str
    voice_release_id: UUID
    voice_hash: str
    virality_release_id: UUID
    virality_hash: str
    outcome: IntegrationOutcome
    revision_count: int = Field(ge=0)
    edited: EditedDraft | None
    revoiced: ReVoicedDraft | None
    evaluation: EvaluationReport | None


class WorkflowContinuation:
    """Encode authenticated snapshots with expiry and immutable-artifact checks."""

    def __init__(
        self, key: str, bundles: Sequence[PublishedProfileBundle], *, ttl_seconds: int = 604800
    ) -> None:
        try:
            self._cipher = Fernet(key.encode("ascii"))
        except (ValueError, UnicodeError) as exc:
            raise ConfigurationError(
                "workflow continuation key must be a valid Fernet key"
            ) from exc
        if ttl_seconds <= 0:
            raise ValueError("continuation lifetime must be positive")
        self._ttl = ttl_seconds
        self._bundles = {bundle.slug: bundle for bundle in bundles}

    def seal(self, session: WorkflowSession) -> str:
        bundle = self._bundle(session.profile.slug)
        voice = bundle.voice_profile.managed_release.release
        virality = bundle.virality_profile.publication.release
        artifacts = session.outcome.artifacts
        if (
            artifacts.voice_profile != bundle.voice_profile
            or artifacts.virality_profile != bundle.virality_profile
        ):
            raise ContinuationError("workflow no longer matches its pinned profile")
        compact = session.outcome.model_copy(
            update={
                "artifacts": artifacts.model_copy(
                    update={
                        "voice_profile": None,
                        "virality_profile": None,
                        "rendered_prompt": None,
                        "retrieval_ranking": None,
                    }
                )
            }
        )
        snapshot = _Snapshot(
            session_id=session.id,
            profile_slug=bundle.slug,
            voice_release_id=voice.id,
            voice_hash=voice.content_hash,
            virality_release_id=virality.id,
            virality_hash=virality.content_hash,
            outcome=compact,
            revision_count=session.revision_count,
            edited=session.edited,
            revoiced=session.revoiced,
            evaluation=session.evaluation,
        )
        serialized = snapshot.model_dump_json().encode("utf-8")
        if len(serialized) > MAX_SNAPSHOT_BYTES:
            raise ContinuationError("workflow exceeds the continuation size limit")
        token = self._cipher.encrypt(zlib.compress(serialized)).decode("ascii")
        if len(token) > MAX_TOKEN_CHARACTERS:
            raise ContinuationError("workflow exceeds the continuation token limit")
        return token

    def open(self, token: str, session_id: UUID) -> WorkflowSession:
        return self._open(token, session_id, ttl=self._ttl)

    def open_stored(self, token: str, session_id: UUID) -> WorkflowSession:
        """Trusted database boundary only: retain MAC, size, identity, and artifact checks.

        Browser bearer lifetime is not a retention policy for an authorized persisted revision.
        Never expose this method as a browser-supplied-token endpoint.
        """
        return self._open(token, session_id, ttl=None)

    def _open(self, token: str, session_id: UUID, *, ttl: int | None) -> WorkflowSession:
        if not token or len(token) > MAX_TOKEN_CHARACTERS:
            raise ContinuationError("workflow continuation is invalid or expired")
        try:
            compressed = self._cipher.decrypt(token, ttl=ttl)
            decoder = zlib.decompressobj()
            payload = decoder.decompress(compressed, MAX_SNAPSHOT_BYTES + 1)
            if len(payload) > MAX_SNAPSHOT_BYTES or not decoder.eof or decoder.unused_data:
                raise ValueError("invalid snapshot size or compression")
            snapshot = _Snapshot.model_validate_json(payload)
        except (InvalidToken, ValueError, zlib.error, ValidationError) as exc:
            raise ContinuationError("workflow continuation is invalid or expired") from exc
        if snapshot.session_id != session_id or snapshot.outcome.run_id != session_id:
            raise ContinuationError("workflow continuation belongs to another session")
        bundle = self._bundle(snapshot.profile_slug)
        voice = bundle.voice_profile.managed_release.release
        virality = bundle.virality_profile.publication.release
        if (
            snapshot.voice_release_id,
            snapshot.voice_hash,
            snapshot.virality_release_id,
            snapshot.virality_hash,
        ) != (voice.id, voice.content_hash, virality.id, virality.content_hash):
            raise ContinuationError("workflow profile changed; start a new draft")
        outcome = snapshot.outcome.model_copy(
            update={
                "artifacts": snapshot.outcome.artifacts.model_copy(
                    update={
                        "voice_profile": bundle.voice_profile,
                        "virality_profile": bundle.virality_profile,
                    }
                )
            }
        )
        return WorkflowSession(
            id=session_id,
            profile=ShowcaseProfile(
                bundle.slug, bundle.name, bundle.role, bundle.summary, bundle.artifact_status
            ),
            outcome=outcome,
            revision_count=snapshot.revision_count,
            edited=snapshot.edited,
            revoiced=snapshot.revoiced,
            evaluation=snapshot.evaluation,
        )

    def _bundle(self, slug: str) -> PublishedProfileBundle:
        try:
            return self._bundles[slug]
        except KeyError as exc:
            raise ContinuationError("workflow profile is no longer available") from exc
