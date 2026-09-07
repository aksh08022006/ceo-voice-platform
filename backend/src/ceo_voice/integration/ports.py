"""Optional relevance preparation at the application I/O boundary."""

from typing import Protocol

from ceo_voice.retrieval.contracts import EvidenceMaterial, RetrievalInput
from ceo_voice.retrieval.ranking_contracts import RetrievalRankingInput


class RetrievalRankingPreparer(Protocol):
    """Prepare explicit ranking inputs before the pure retrieval operation."""

    async def prepare(
        self, value: RetrievalInput, materials: tuple[EvidenceMaterial, ...]
    ) -> RetrievalRankingInput | None: ...
