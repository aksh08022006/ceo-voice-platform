"""In-memory and atomic local-file workspace adapters for profile builds."""

import asyncio
from pathlib import Path
from uuid import UUID

from pydantic import Field

from ceo_voice.analysis import ObservationSet
from ceo_voice.core.exceptions import StorageError
from ceo_voice.models.base import ContractModel
from ceo_voice.profiles.contracts import (
    BuildCheckpoint,
    ObservationCacheKey,
    PublishedVoiceProfile,
)
from ceo_voice.voice import ManagedRelease, ReleaseChange, ReleaseStatus


class _ReleaseCatalogFile(ContractModel):
    """Single-file release catalog enabling atomic multi-release lifecycle updates."""

    records: tuple[ManagedRelease, ...] = Field(default_factory=tuple)


class InMemoryProfileWorkspace:
    """Concurrency-safe workspace for tests and embedded single-process execution."""

    def __init__(self) -> None:
        self._observations: dict[UUID, ObservationSet] = {}
        self._checkpoints: dict[tuple[UUID, str], BuildCheckpoint] = {}
        self._profiles: dict[tuple[UUID, str], PublishedVoiceProfile] = {}
        self._releases: dict[UUID, ManagedRelease] = {}
        self._lock = asyncio.Lock()

    async def get_observations(self, key: ObservationCacheKey) -> ObservationSet | None:
        async with self._lock:
            return self._observations.get(key.analysis_run_id)

    async def save_observations(
        self, key: ObservationCacheKey, observation_set: ObservationSet
    ) -> None:
        if observation_set.run_id != key.analysis_run_id:
            raise StorageError("observation cache key does not match the analysis run")
        async with self._lock:
            existing = self._observations.get(key.analysis_run_id)
            if existing is not None and existing != observation_set:
                raise StorageError("observation cache identity conflict")
            self._observations[key.analysis_run_id] = observation_set

    async def get_checkpoint(
        self, voice_identity_id: UUID, corpus_hash: str
    ) -> BuildCheckpoint | None:
        async with self._lock:
            return self._checkpoints.get((voice_identity_id, corpus_hash))

    async def save_checkpoint(self, checkpoint: BuildCheckpoint) -> None:
        async with self._lock:
            self._checkpoints[(checkpoint.voice_identity_id, checkpoint.corpus_hash)] = checkpoint

    async def get_published(
        self, voice_identity_id: UUID, corpus_hash: str
    ) -> PublishedVoiceProfile | None:
        async with self._lock:
            return self._profiles.get((voice_identity_id, corpus_hash))

    async def save_published(self, profile: PublishedVoiceProfile) -> None:
        key = (profile.managed_release.release.voice_identity_id, profile.corpus_hash)
        async with self._lock:
            existing = self._profiles.get(key)
            if existing is not None and existing != profile:
                _validate_profile_update(existing, profile)
            self._profiles[key] = profile

    async def get(self, tenant_id: UUID, release_id: UUID) -> ManagedRelease | None:
        async with self._lock:
            record = self._releases.get(release_id)
            if record is None or record.release.tenant_id != tenant_id:
                return None
            return record

    async def list_lineage(self, tenant_id: UUID, lineage_id: UUID) -> tuple[ManagedRelease, ...]:
        async with self._lock:
            return tuple(
                sorted(
                    (
                        item
                        for item in self._releases.values()
                        if item.release.tenant_id == tenant_id
                        and item.release.lineage_id == lineage_id
                    ),
                    key=lambda item: item.release.version,
                )
            )

    async def commit(self, changes: tuple[ReleaseChange, ...]) -> None:
        async with self._lock:
            _validate_release_changes(self._releases, changes)
            for change in changes:
                self._releases[change.record.release.id] = change.record


class JsonProfileWorkspace:
    """Atomic JSON workspace used by the local build CLI.

    A complete release catalog is replaced as one file, so activation and supersession cannot be
    partially persisted. The adapter is safe for concurrent coroutines in one process. A future
    multi-process or distributed deployment should implement the same port with transactional
    storage and optimistic concurrency.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()
        self._lock = asyncio.Lock()

    async def get_observations(self, key: ObservationCacheKey) -> ObservationSet | None:
        async with self._lock:
            return self._read_model(self._observation_path(key.analysis_run_id), ObservationSet)

    async def save_observations(
        self, key: ObservationCacheKey, observation_set: ObservationSet
    ) -> None:
        if observation_set.run_id != key.analysis_run_id:
            raise StorageError("observation cache key does not match the analysis run")
        async with self._lock:
            path = self._observation_path(key.analysis_run_id)
            existing = self._read_model(path, ObservationSet)
            if existing is not None and existing != observation_set:
                raise StorageError("observation cache identity conflict")
            self._write_model(path, observation_set)

    async def get_checkpoint(
        self, voice_identity_id: UUID, corpus_hash: str
    ) -> BuildCheckpoint | None:
        async with self._lock:
            return self._read_model(
                self._checkpoint_path(voice_identity_id, corpus_hash), BuildCheckpoint
            )

    async def save_checkpoint(self, checkpoint: BuildCheckpoint) -> None:
        async with self._lock:
            self._write_model(
                self._checkpoint_path(checkpoint.voice_identity_id, checkpoint.corpus_hash),
                checkpoint,
            )

    async def get_published(
        self, voice_identity_id: UUID, corpus_hash: str
    ) -> PublishedVoiceProfile | None:
        async with self._lock:
            return self._read_model(
                self._profile_path(voice_identity_id, corpus_hash), PublishedVoiceProfile
            )

    async def save_published(self, profile: PublishedVoiceProfile) -> None:
        identity_id = profile.managed_release.release.voice_identity_id
        async with self._lock:
            path = self._profile_path(identity_id, profile.corpus_hash)
            existing = self._read_model(path, PublishedVoiceProfile)
            if existing is not None and existing != profile:
                _validate_profile_update(existing, profile)
            self._write_model(path, profile)

    async def get(self, tenant_id: UUID, release_id: UUID) -> ManagedRelease | None:
        async with self._lock:
            record = self._release_records().get(release_id)
            if record is None or record.release.tenant_id != tenant_id:
                return None
            return record

    async def list_lineage(self, tenant_id: UUID, lineage_id: UUID) -> tuple[ManagedRelease, ...]:
        async with self._lock:
            return tuple(
                sorted(
                    (
                        item
                        for item in self._release_records().values()
                        if item.release.tenant_id == tenant_id
                        and item.release.lineage_id == lineage_id
                    ),
                    key=lambda item: item.release.version,
                )
            )

    async def commit(self, changes: tuple[ReleaseChange, ...]) -> None:
        async with self._lock:
            records = self._release_records()
            _validate_release_changes(records, changes)
            for change in changes:
                records[change.record.release.id] = change.record
            catalog = _ReleaseCatalogFile(
                records=tuple(sorted(records.values(), key=lambda item: item.release.id.int))
            )
            self._write_model(self._root / "releases" / "catalog.json", catalog)

    def _release_records(self) -> dict[UUID, ManagedRelease]:
        catalog = (
            self._read_model(self._root / "releases" / "catalog.json", _ReleaseCatalogFile)
            or _ReleaseCatalogFile()
        )
        return {item.release.id: item for item in catalog.records}

    def _observation_path(self, run_id: UUID) -> Path:
        return self._root / "observations" / f"{run_id}.json"

    def _checkpoint_path(self, identity_id: UUID, corpus_hash: str) -> Path:
        return self._root / "checkpoints" / str(identity_id) / f"{corpus_hash}.json"

    def _profile_path(self, identity_id: UUID, corpus_hash: str) -> Path:
        return self._root / "profiles" / str(identity_id) / f"{corpus_hash}.json"

    @staticmethod
    def _read_model[T: ContractModel](path: Path, model: type[T]) -> T | None:
        if not path.exists():
            return None
        return model.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_model(path: Path, model: ContractModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(model.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)


def _validate_release_changes(
    records: dict[UUID, ManagedRelease], changes: tuple[ReleaseChange, ...]
) -> None:
    """Validate one optimistic atomic release-catalog transaction."""

    if not changes:
        raise StorageError("release transaction must contain at least one change")
    release_ids = tuple(change.record.release.id for change in changes)
    if len(release_ids) != len(set(release_ids)):
        raise StorageError("release transaction contains duplicate changes")
    for change in changes:
        current = records.get(change.record.release.id)
        if change.expected_revision is None:
            if current is not None:
                raise StorageError("release create conflict")
        elif current is None or current.revision != change.expected_revision:
            raise StorageError("release revision conflict")


def _validate_profile_update(
    existing: PublishedVoiceProfile, replacement: PublishedVoiceProfile
) -> None:
    """Allow only a lifecycle-only advance of the same immutable release artifact."""

    if (
        existing.build_id != replacement.build_id
        or existing.corpus_hash != replacement.corpus_hash
        or existing.managed_release.release != replacement.managed_release.release
        or existing.validation_report != replacement.validation_report
        or existing.observations != replacement.observations
        or existing.evidence_units != replacement.evidence_units
        or existing.retrieval_projection != replacement.retrieval_projection
        or (
            existing.managed_release.status,
            replacement.managed_release.status,
        )
        != (ReleaseStatus.NEEDS_REVIEW, ReleaseStatus.ACTIVE)
        or replacement.managed_release.revision <= existing.managed_release.revision
    ):
        raise StorageError("published profile identity conflict")
