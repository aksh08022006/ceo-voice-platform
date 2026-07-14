"""Persistence boundary for immutable virality releases and active publication state."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from ceo_voice.virality.contracts import AnalysisSnapshot, CorpusAnalysis, ViralityProfile


@runtime_checkable
class ViralityWorkspace(Protocol):
    """Minimal atomic catalog needed by the Virality Library Builder."""

    async def get_analysis(self, snapshot: AnalysisSnapshot) -> CorpusAnalysis | None:
        """Return the full observation dataset matching a content-addressed snapshot."""

        ...

    async def save_analysis(self, snapshot: AnalysisSnapshot, analysis: CorpusAnalysis) -> None:
        """Persist one immutable analysis snapshot idempotently."""

        ...

    async def get_by_fingerprint(
        self, tenant_id: UUID, library_id: UUID, fingerprint: str
    ) -> ViralityProfile | None:
        """Return an idempotently completed build."""

        ...

    async def list_releases(self, tenant_id: UUID, library_id: UUID) -> tuple[ViralityProfile, ...]:
        """Return release snapshots in ascending version order."""

        ...

    async def publish(self, profile: ViralityProfile) -> None:
        """Atomically activate the profile and supersede the previous active release."""

        ...
