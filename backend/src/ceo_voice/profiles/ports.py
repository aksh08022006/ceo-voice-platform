"""Persistence and progress ports owned by the profile-builder workflow."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from ceo_voice.analysis import ObservationSet
from ceo_voice.profiles.contracts import (
    BuildCheckpoint,
    ObservationCacheKey,
    ProgressEvent,
    PublishedVoiceProfile,
)
from ceo_voice.voice import ManagedRelease, ReleaseChange


@runtime_checkable
class ProfileWorkspace(Protocol):
    """Atomic workflow state required for incremental and restartable profile builds."""

    async def get_observations(self, key: ObservationCacheKey) -> ObservationSet | None:
        """Return an exactly compatible cached document analysis."""

        ...

    async def save_observations(
        self, key: ObservationCacheKey, observation_set: ObservationSet
    ) -> None:
        """Persist one immutable document analysis idempotently."""

        ...

    async def get_checkpoint(
        self, voice_identity_id: UUID, corpus_hash: str
    ) -> BuildCheckpoint | None:
        """Return a prior build attempt for the same corpus."""

        ...

    async def save_checkpoint(self, checkpoint: BuildCheckpoint) -> None:
        """Create or advance a restart checkpoint."""

        ...

    async def get_published(
        self, voice_identity_id: UUID, corpus_hash: str
    ) -> PublishedVoiceProfile | None:
        """Return a completed artifact for an identical corpus."""

        ...

    async def save_published(self, profile: PublishedVoiceProfile) -> None:
        """Persist a complete published artifact idempotently."""

        ...

    async def get(self, tenant_id: UUID, release_id: UUID) -> ManagedRelease | None:
        """Return one managed release for lifecycle orchestration."""

        ...

    async def list_lineage(self, tenant_id: UUID, lineage_id: UUID) -> tuple[ManagedRelease, ...]:
        """Return releases in monotonically increasing version order."""

        ...

    async def commit(self, changes: tuple[ReleaseChange, ...]) -> None:
        """Atomically apply release lifecycle changes."""

        ...


@runtime_checkable
class ProgressSink(Protocol):
    """Receive progress without influencing workflow correctness."""

    def report(self, event: ProgressEvent) -> None:
        """Handle one immutable progress event."""

        ...


class NullProgressSink:
    """Default progress adapter for embedded builds."""

    def report(self, event: ProgressEvent) -> None:
        """Intentionally ignore progress."""

        del event
