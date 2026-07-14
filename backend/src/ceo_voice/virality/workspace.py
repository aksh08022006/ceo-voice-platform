"""In-memory and atomic local JSON adapters for Virality Knowledge Releases."""

import asyncio
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

from pydantic import Field

from ceo_voice.core.exceptions import StorageError
from ceo_voice.models.base import ContractModel
from ceo_voice.virality.contracts import AnalysisSnapshot, CorpusAnalysis, ViralityProfile
from ceo_voice.virality.enums import PublicationStatus
from ceo_voice.virality.releases import build_analysis_snapshot


class _Catalog(ContractModel):
    profiles: tuple[ViralityProfile, ...] = Field(default_factory=tuple)


class InMemoryViralityWorkspace:
    """Concurrency-safe catalog for tests and embedded single-process use."""

    def __init__(self) -> None:
        self._profiles: dict[UUID, ViralityProfile] = {}
        self._analyses: dict[UUID, CorpusAnalysis] = {}
        self._lock = asyncio.Lock()

    async def get_analysis(self, snapshot: AnalysisSnapshot) -> CorpusAnalysis | None:
        async with self._lock:
            return self._analyses.get(snapshot.id)

    async def save_analysis(self, snapshot: AnalysisSnapshot, analysis: CorpusAnalysis) -> None:
        _validate_analysis(snapshot, analysis)
        async with self._lock:
            existing = self._analyses.get(snapshot.id)
            if existing is not None and existing != analysis:
                raise StorageError("virality analysis snapshot identity conflict")
            self._analyses[snapshot.id] = analysis

    async def get_by_fingerprint(
        self, tenant_id: UUID, library_id: UUID, fingerprint: str
    ) -> ViralityProfile | None:
        async with self._lock:
            return next(
                (
                    item
                    for item in self._profiles.values()
                    if item.publication.release.tenant_id == tenant_id
                    and item.publication.release.library_id == library_id
                    and item.build_fingerprint == fingerprint
                ),
                None,
            )

    async def list_releases(self, tenant_id: UUID, library_id: UUID) -> tuple[ViralityProfile, ...]:
        async with self._lock:
            return _matching(self._profiles.values(), tenant_id, library_id)

    async def publish(self, profile: ViralityProfile) -> None:
        async with self._lock:
            self._profiles = _published(self._profiles, profile)


class JsonViralityWorkspace:
    """Atomic local catalog; distributed deployments replace this adapter transactionally."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve() / "virality"
        self._path = self._root / "catalog.json"
        self._lock = asyncio.Lock()

    async def get_analysis(self, snapshot: AnalysisSnapshot) -> CorpusAnalysis | None:
        async with self._lock:
            path = self._analysis_path(snapshot.id)
            if not path.exists():
                return None
            analysis = CorpusAnalysis.model_validate_json(path.read_text(encoding="utf-8"))
            _validate_analysis(snapshot, analysis)
            return analysis

    async def save_analysis(self, snapshot: AnalysisSnapshot, analysis: CorpusAnalysis) -> None:
        _validate_analysis(snapshot, analysis)
        async with self._lock:
            path = self._analysis_path(snapshot.id)
            if path.exists():
                existing = CorpusAnalysis.model_validate_json(path.read_text(encoding="utf-8"))
                if existing != analysis:
                    raise StorageError("virality analysis snapshot identity conflict")
                return
            self._write_model(path, analysis)

    async def get_by_fingerprint(
        self, tenant_id: UUID, library_id: UUID, fingerprint: str
    ) -> ViralityProfile | None:
        async with self._lock:
            return next(
                (
                    item
                    for item in self._read().profiles
                    if item.publication.release.tenant_id == tenant_id
                    and item.publication.release.library_id == library_id
                    and item.build_fingerprint == fingerprint
                ),
                None,
            )

    async def list_releases(self, tenant_id: UUID, library_id: UUID) -> tuple[ViralityProfile, ...]:
        async with self._lock:
            return _matching(self._read().profiles, tenant_id, library_id)

    async def publish(self, profile: ViralityProfile) -> None:
        async with self._lock:
            records = {item.publication.release.id: item for item in self._read().profiles}
            updated = _published(records, profile)
            self._write(
                _Catalog(
                    profiles=tuple(
                        sorted(updated.values(), key=lambda item: item.publication.release.id.int)
                    )
                )
            )

    def _read(self) -> _Catalog:
        if not self._path.exists():
            return _Catalog()
        return _Catalog.model_validate_json(self._path.read_text(encoding="utf-8"))

    def _write(self, catalog: _Catalog) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".json.tmp")
        temporary.write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(self._path)

    def _analysis_path(self, snapshot_id: UUID) -> Path:
        return self._root / "analyses" / f"{snapshot_id}.json"

    @staticmethod
    def _write_model(path: Path, model: ContractModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(model.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)


def _matching(
    profiles: Iterable[ViralityProfile], tenant_id: UUID, library_id: UUID
) -> tuple[ViralityProfile, ...]:
    return tuple(
        sorted(
            (
                item
                for item in profiles
                if item.publication.release.tenant_id == tenant_id
                and item.publication.release.library_id == library_id
            ),
            key=lambda item: item.publication.release.version,
        )
    )


def _validate_analysis(snapshot: AnalysisSnapshot, analysis: CorpusAnalysis) -> None:
    rebuilt = build_analysis_snapshot(
        snapshot_id=snapshot.id,
        analysis=analysis,
        corpus_id=snapshot.corpus_id,
    )
    if rebuilt != snapshot:
        raise StorageError("virality analysis does not match its snapshot")


def _published(
    records: dict[UUID, ViralityProfile], profile: ViralityProfile
) -> dict[UUID, ViralityProfile]:
    release = profile.publication.release
    if profile.publication.status is not PublicationStatus.ACTIVE:
        raise StorageError("only an active virality profile may be published")
    existing = records.get(release.id)
    if existing is not None:
        if existing != profile:
            raise StorageError("virality release identity conflict")
        return records
    if any(
        item.build_fingerprint == profile.build_fingerprint
        and item.publication.release.tenant_id == release.tenant_id
        and item.publication.release.library_id == release.library_id
        for item in records.values()
    ):
        raise StorageError("virality build fingerprint conflict")
    updated = dict(records)
    lineage = tuple(
        item
        for item in records.values()
        if item.publication.release.tenant_id == release.tenant_id
        and item.publication.release.library_id == release.library_id
    )
    expected_version = max((item.publication.release.version for item in lineage), default=0) + 1
    active = next(
        (item for item in lineage if item.publication.status is PublicationStatus.ACTIVE),
        None,
    )
    if release.version != expected_version:
        raise StorageError("virality release version is not the next lineage version")
    if release.previous_release_id != (
        active.publication.release.id if active is not None else None
    ):
        raise StorageError("virality release does not reference the active predecessor")
    for release_id, item in tuple(updated.items()):
        candidate = item.publication.release
        if (
            candidate.tenant_id == release.tenant_id
            and candidate.library_id == release.library_id
            and item.publication.status is PublicationStatus.ACTIVE
        ):
            updated[release_id] = item.model_copy(
                update={
                    "publication": item.publication.model_copy(
                        update={"status": PublicationStatus.SUPERSEDED}
                    )
                }
            )
    updated[release.id] = profile
    return updated
