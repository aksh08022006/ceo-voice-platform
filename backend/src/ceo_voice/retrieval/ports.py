"""Minimal evidence-material boundary required by generation retrieval."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from ceo_voice.retrieval.contracts import EvidenceMaterial


@runtime_checkable
class EvidenceMaterialReader(Protocol):
    """Resolve immutable evidence spans without exposing raw documents."""

    async def get_many(
        self, tenant_id: UUID, evidence_ids: tuple[UUID, ...]
    ) -> tuple[EvidenceMaterial, ...]:
        """Return available material for the requested evidence IDs only."""

        ...
