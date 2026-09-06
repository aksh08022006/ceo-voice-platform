"""Prepare real embeddings outside the deterministic retrieval engine.

Only explicit hybrid configuration sends eligible evidence and the topic to the configured
OpenAI-compatible endpoint. Baseline and BM25 require no model or network access.
"""

import math
from collections import OrderedDict
from typing import cast
from uuid import UUID

from pydantic import JsonValue, SecretStr

from ceo_voice.config import ModelSettings, RetrievalSettings
from ceo_voice.core.exceptions import ConfigurationError, ProviderError, RetrievalValidationError
from ceo_voice.generation.ports import JsonTransport
from ceo_voice.retrieval.contracts import EvidenceMaterial, RetrievalInput
from ceo_voice.retrieval.ranking_contracts import (
    DenseEmbeddingSnapshot,
    DenseEvidenceEmbedding,
    DenseQueryEmbedding,
    RetrievalRankingInput,
    RetrievalRankingMode,
)
from ceo_voice.utils.hashing import sha256_text


class ConfiguredRetrievalRanking:
    """Bound preparation cost and bind vectors to exact tenant-owned content.

    The process-local LRU stores only vectors keyed by tenant, leader and content hash. It is
    scoped to one immutable provider/model/revision configuration. There is no silent fallback
    if the provider fails or returns an inconsistent embedding space.
    """

    def __init__(
        self,
        settings: RetrievalSettings,
        model: ModelSettings,
        transport: JsonTransport | None = None,
    ) -> None:
        self._settings = settings.model_copy(deep=True)
        self._mode = RetrievalRankingMode(settings.mode)
        self._transport = transport
        self._model = model.embedding_model
        self._revision = settings.embedding_revision
        self._key: SecretStr | None = model.api_key
        self._url = (model.base_url or "https://api.openai.com/v1").rstrip("/") + "/embeddings"
        self._cache: OrderedDict[tuple[UUID, UUID, str], tuple[float, ...]] = OrderedDict()
        if self._mode is RetrievalRankingMode.HYBRID and (
            not model.enabled
            or (model.provider or "").lower() != "openai"
            or self._model is None
            or self._revision is None
            or self._key is None
            or transport is None
        ):
            raise ConfigurationError("hybrid retrieval requires a complete embedding provider")

    async def prepare(
        self, value: RetrievalInput, materials: tuple[EvidenceMaterial, ...]
    ) -> RetrievalRankingInput | None:
        """Prepare immutable inputs; material selection and authority belong to retrieval."""

        if self._mode is RetrievalRankingMode.BASELINE:
            return None
        options = {
            "mode": self._mode,
            "relevance_weight": self._settings.relevance_weight,
            "sparse_weight": self._settings.sparse_weight,
            "rrf_k": self._settings.rrf_k,
        }
        if self._mode is RetrievalRankingMode.BM25:
            return RetrievalRankingInput.model_validate(options)
        self._validate_materials(value, materials)
        texts = (*tuple(item.content for item in materials), value.request.topic)
        vectors = await self._vectors(value, texts)
        assert self._model is not None and self._revision is not None
        snapshot = DenseEmbeddingSnapshot(
            tenant_id=value.request.tenant_id,
            model=self._model,
            revision=self._revision,
            dimensions=self._settings.embedding_dimensions,
            evidence=tuple(
                DenseEvidenceEmbedding(
                    evidence_id=item.evidence_id,
                    content_hash=item.content_hash,
                    vector=vector,
                )
                for item, vector in zip(materials, vectors[:-1], strict=True)
            ),
        )
        query = DenseQueryEmbedding(
            tenant_id=value.request.tenant_id,
            model=self._model,
            revision=self._revision,
            dimensions=self._settings.embedding_dimensions,
            query_hash=sha256_text(value.request.topic),
            vector=vectors[-1],
        )
        return RetrievalRankingInput.model_validate(
            {**options, "dense_snapshot": snapshot, "dense_query": query}
        )

    def _validate_materials(
        self, value: RetrievalInput, materials: tuple[EvidenceMaterial, ...]
    ) -> None:
        if not materials or len(materials) + 1 > self._settings.maximum_embedding_items:
            raise RetrievalValidationError("embedding candidate count exceeds preparation bounds")
        if len({item.evidence_id for item in materials}) != len(materials):
            raise RetrievalValidationError("embedding candidates contain duplicate identifiers")
        if any(item.tenant_id != value.request.tenant_id for item in materials):
            raise RetrievalValidationError("embedding candidate belongs to another tenant")
        # UTF-8 byte count is a conservative upper bound for byte-level tokenizer tokens.
        # Reject oversize spans rather than silently truncating content behind its hash.
        if any(
            len(text.encode("utf-8")) > self._settings.maximum_embedding_input_bytes
            for text in (*tuple(item.content for item in materials), value.request.topic)
        ):
            raise RetrievalValidationError("embedding input exceeds the configured byte bound")

    async def _vectors(
        self, value: RetrievalInput, texts: tuple[str, ...]
    ) -> tuple[tuple[float, ...], ...]:
        keys = tuple(
            (value.request.tenant_id, value.request.ceo_id, sha256_text(text)) for text in texts
        )
        resolved: dict[tuple[UUID, UUID, str], tuple[float, ...]] = {}
        missing: dict[tuple[UUID, UUID, str], str] = {}
        for key, text in zip(keys, texts, strict=True):
            if key in self._cache:
                resolved[key] = self._cache[key]
                self._cache.move_to_end(key)
            else:
                missing[key] = text
        items = tuple(missing.items())
        for start in range(0, len(items), self._settings.embedding_batch_size):
            batch = items[start : start + self._settings.embedding_batch_size]
            vectors = await self._embed(tuple(text for _, text in batch))
            for (key, _), vector in zip(batch, vectors, strict=True):
                resolved[key] = vector
                self._cache[key] = vector
                while len(self._cache) > self._settings.embedding_cache_items:
                    self._cache.popitem(last=False)
        return tuple(resolved[key] for key in keys)

    async def _embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        assert self._transport is not None and self._key is not None and self._model is not None
        payload: dict[str, JsonValue] = {
            "input": list(texts),
            "model": self._model,
            "encoding_format": "float",
            "dimensions": self._settings.embedding_dimensions,
        }
        response, _ = await self._transport.post(
            url=self._url,
            headers={
                "Authorization": f"Bearer {self._key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            payload=payload,
        )
        if response.get("model") != self._model:
            raise ProviderError("embedding provider returned a different model")
        rows = response.get("data")
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise ProviderError("embedding provider returned an inconsistent item count")
        indexed: dict[int, tuple[float, ...]] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ProviderError("embedding provider returned a malformed item")
            index, vector = row.get("index"), row.get("embedding")
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or not 0 <= index < len(texts)
                or index in indexed
                or not isinstance(vector, list)
                or len(vector) != self._settings.embedding_dimensions
            ):
                raise ProviderError("embedding provider returned invalid indices or dimensions")
            if any(not isinstance(item, int | float) or isinstance(item, bool) for item in vector):
                raise ProviderError("embedding provider returned invalid vector values")
            try:
                numbers = tuple(float(item) for item in cast(list[int | float], vector))
            except OverflowError as error:
                raise ProviderError(
                    "embedding provider returned unbounded vector values"
                ) from error
            if any(not math.isfinite(item) for item in numbers):
                raise ProviderError("embedding provider returned invalid vector values")
            norm = math.hypot(*numbers)
            if norm == 0 or not math.isfinite(norm):
                raise ProviderError("embedding provider returned a zero or unbounded vector")
            indexed[index] = numbers
        return tuple(indexed[index] for index in range(len(texts)))
