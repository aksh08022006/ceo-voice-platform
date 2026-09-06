"""Explicit, reproducible inputs and diagnostics for optional relevance ranking."""

import math
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, model_validator

from ceo_voice.models.base import ContractModel, NonEmptyStr

ContentDigest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class RetrievalRankingMode(StrEnum):
    """Baseline authority scoring, lexical retrieval, or real-vector hybrid retrieval."""

    BASELINE = "baseline"
    BM25 = "bm25"
    HYBRID = "hybrid"


class DenseEvidenceEmbedding(ContractModel):
    """Embedding of one exact content-addressed, governed evidence span."""

    evidence_id: UUID
    content_hash: ContentDigest
    vector: tuple[float, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_vector(self) -> Self:
        _validate_vector(self.vector)
        return self


class DenseEmbeddingSnapshot(ContractModel):
    """Caller-supplied embeddings; the engine never fabricates missing vectors."""

    tenant_id: UUID
    model: NonEmptyStr
    revision: NonEmptyStr
    dimensions: int = Field(ge=1, le=65_536)
    evidence: tuple[DenseEvidenceEmbedding, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        ids = tuple(item.evidence_id for item in self.evidence)
        if len(ids) != len(set(ids)):
            raise ValueError("dense snapshot evidence identifiers must be unique")
        if any(len(item.vector) != self.dimensions for item in self.evidence):
            raise ValueError("dense snapshot vector dimensions do not match its declaration")
        return self


class DenseQueryEmbedding(ContractModel):
    """Embedding of the exact request topic, in the snapshot's embedding space."""

    tenant_id: UUID
    model: NonEmptyStr
    revision: NonEmptyStr
    dimensions: int = Field(ge=1, le=65_536)
    query_hash: ContentDigest
    vector: tuple[float, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_vector(self) -> Self:
        _validate_vector(self.vector)
        if len(self.vector) != self.dimensions:
            raise ValueError("query vector dimensions do not match its declaration")
        return self


class RetrievalRankingInput(ContractModel):
    """Optional candidate reranking; authority and mandatory coverage remain in force."""

    mode: RetrievalRankingMode = RetrievalRankingMode.BASELINE
    relevance_weight: float = Field(default=0.35, gt=0, le=0.5, allow_inf_nan=False)
    sparse_weight: float = Field(default=0.5, gt=0, lt=1, allow_inf_nan=False)
    rrf_k: int = Field(default=60, ge=1, le=1_000)
    dense_snapshot: DenseEmbeddingSnapshot | None = None
    dense_query: DenseQueryEmbedding | None = None

    @model_validator(mode="after")
    def validate_dense_inputs(self) -> Self:
        if self.mode is RetrievalRankingMode.HYBRID:
            if self.dense_snapshot is None or self.dense_query is None:
                raise ValueError(
                    "hybrid ranking requires both a dense snapshot and query embedding"
                )
        elif self.dense_snapshot is not None or self.dense_query is not None:
            raise ValueError("dense embeddings may only be supplied for hybrid ranking")
        return self


class CandidateRanking(ContractModel):
    """Raw branch scores, ranks and the exact authority/relevance blend per candidate."""

    evidence_id: UUID
    lexical_score: float = Field(ge=0, allow_inf_nan=False)
    lexical_rank: int | None = Field(default=None, ge=1)
    dense_score: float | None = Field(default=None, ge=-1, le=1, allow_inf_nan=False)
    dense_rank: int | None = Field(default=None, ge=1)
    fusion_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    relevance_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    authority_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    blended_score: float = Field(ge=0, le=1, allow_inf_nan=False)


class RetrievalRankingReport(ContractModel):
    """Audit record of reranking; synthetic embeddings are never an engine fallback."""

    algorithm_version: str = "governed-relevance/1.0.0"
    mode: RetrievalRankingMode
    query_hash: ContentDigest
    relevance_weight: float = Field(gt=0, le=0.5)
    sparse_weight: float = Field(gt=0, lt=1)
    rrf_k: int = Field(ge=1)
    embedding_model: str | None = None
    embedding_revision: str | None = None
    embedding_dimensions: int | None = None
    dense_snapshot_hash: ContentDigest | None = None
    dense_query_hash: ContentDigest | None = None
    candidates: tuple[CandidateRanking, ...]


def _validate_vector(vector: tuple[float, ...]) -> None:
    if any(not math.isfinite(item) for item in vector):
        raise ValueError("dense vectors must contain only finite values")
    norm = math.hypot(*vector)
    if norm == 0 or not math.isfinite(norm):
        raise ValueError("dense vectors must have a finite, nonzero norm")
