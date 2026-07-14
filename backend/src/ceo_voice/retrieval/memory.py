"""In-memory evidence material adapter for tests and embedded execution."""

from collections.abc import Iterable
from uuid import UUID

from ceo_voice.retrieval.contracts import EvidenceMaterial


class InMemoryEvidenceMaterialReader:
    """Serve an immutable material snapshot behind the production reader port."""

    def __init__(self, materials: Iterable[EvidenceMaterial]) -> None:
        indexed: dict[UUID, EvidenceMaterial] = {}
        for material in materials:
            if material.evidence_id in indexed:
                raise ValueError("evidence material identifiers must be unique")
            indexed[material.evidence_id] = material
        self._materials = indexed

    async def get_many(
        self, tenant_id: UUID, evidence_ids: tuple[UUID, ...]
    ) -> tuple[EvidenceMaterial, ...]:
        """Return matching tenant-owned spans in canonical request order."""

        return tuple(
            material
            for evidence_id in evidence_ids
            if (material := self._materials.get(evidence_id)) is not None
            and material.tenant_id == tenant_id
        )
