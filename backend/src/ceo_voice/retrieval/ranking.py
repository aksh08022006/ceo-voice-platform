"""Deterministic BM25 and supplied-vector cosine ranking over governed candidates."""

import math
import re
from collections import Counter
from uuid import UUID

from ceo_voice.core.exceptions import RetrievalValidationError
from ceo_voice.retrieval.ranking_contracts import (
    CandidateRanking,
    RetrievalRankingInput,
    RetrievalRankingMode,
    RetrievalRankingReport,
)
from ceo_voice.retrieval.selection import EvidenceCandidate
from ceo_voice.utils.hashing import sha256_text

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "with",
    ]
)


def bm25_scores(query: str, documents: tuple[str, ...]) -> tuple[float, ...]:
    """Compute Okapi BM25 (k1=1.2, b=.75) using Unicode words and positive IDF."""

    terms = set(_tokens(query))
    counters = tuple(Counter(_tokens(document)) for document in documents)
    if not counters or not terms:
        return tuple(0.0 for _ in counters)
    lengths = tuple(sum(counter.values()) for counter in counters)
    average = sum(lengths) / len(lengths)
    if average == 0:
        return tuple(0.0 for _ in counters)
    idf = {
        term: math.log1p(
            (len(counters) - (frequency := sum(term in item for item in counters)) + 0.5)
            / (frequency + 0.5)
        )
        for term in sorted(terms)
    }
    return tuple(
        math.fsum(
            idf[term] * (frequency * 2.2) / (frequency + 1.2 * (0.25 + 0.75 * length / average))
            for term in sorted(terms)
            if (frequency := counter[term]) > 0
        )
        for counter, length in zip(counters, lengths, strict=True)
    )


def reciprocal_rank_fusion(
    sparse_rank: int | None,
    dense_rank: int | None,
    *,
    sparse_weight: float = 0.5,
    k: int = 60,
) -> float:
    """Weighted RRF; absent/nonpositive branch matches contribute no evidence."""

    return (sparse_weight / (k + sparse_rank) if sparse_rank is not None else 0.0) + (
        (1 - sparse_weight) / (k + dense_rank) if dense_rank is not None else 0.0
    )


def rerank_candidates(
    candidates: tuple[EvidenceCandidate, ...],
    *,
    topic: str,
    tenant_id: UUID,
    ranking: RetrievalRankingInput | None,
) -> RetrievalRankingReport | None:
    """Adjust candidate scores without broadening their ownership, purpose or requirements."""

    if ranking is None or ranking.mode is RetrievalRankingMode.BASELINE:
        return None
    ordered = tuple(sorted(candidates, key=lambda item: item.material.evidence_id.int))
    if any(item.material.tenant_id != tenant_id for item in ordered):
        _invalid("tenant_mismatch")
    lexical = dict(
        zip(
            (item.material.evidence_id for item in ordered),
            bm25_scores(topic, tuple(item.material.content for item in ordered)),
            strict=True,
        )
    )
    lexical_ranks = _ranks(lexical)
    dense: dict[UUID, float] = {}
    if ranking.mode is RetrievalRankingMode.HYBRID:
        dense = _dense_scores(ordered, topic=topic, tenant_id=tenant_id, ranking=ranking)
    dense_ranks = _ranks(dense)
    lexical_maximum = max(lexical.values(), default=0.0)
    diagnostics: list[CandidateRanking] = []
    for item in ordered:
        evidence_id = item.material.evidence_id
        fusion = (
            reciprocal_rank_fusion(
                lexical_ranks.get(evidence_id),
                dense_ranks.get(evidence_id),
                sparse_weight=ranking.sparse_weight,
                k=ranking.rrf_k,
            )
            if ranking.mode is RetrievalRankingMode.HYBRID
            else 0.0
        )
        relevance = (
            fusion * (ranking.rrf_k + 1)
            if ranking.mode is RetrievalRankingMode.HYBRID
            else lexical[evidence_id] / lexical_maximum if lexical_maximum > 0 else 0.0
        )
        relevance = min(1.0, max(0.0, relevance))
        authority = item.score.base_score
        blended = round(
            (1 - ranking.relevance_weight) * authority + ranking.relevance_weight * relevance, 6
        )
        item.score = item.score.model_copy(update={"base_score": blended, "final_score": blended})
        item.reasons.add(f"{ranking.mode.value} topic relevance {relevance:.6f}")
        diagnostics.append(
            CandidateRanking(
                evidence_id=evidence_id,
                lexical_score=lexical[evidence_id],
                lexical_rank=lexical_ranks.get(evidence_id),
                dense_score=dense.get(evidence_id),
                dense_rank=dense_ranks.get(evidence_id),
                fusion_score=fusion,
                relevance_score=relevance,
                authority_score=authority,
                blended_score=blended,
            )
        )
    snapshot = ranking.dense_snapshot
    return RetrievalRankingReport(
        mode=ranking.mode,
        query_hash=sha256_text(topic),
        relevance_weight=ranking.relevance_weight,
        sparse_weight=ranking.sparse_weight,
        rrf_k=ranking.rrf_k,
        embedding_model=snapshot.model if snapshot else None,
        embedding_revision=snapshot.revision if snapshot else None,
        embedding_dimensions=snapshot.dimensions if snapshot else None,
        dense_snapshot_hash=sha256_text(snapshot.model_dump_json()) if snapshot else None,
        dense_query_hash=(
            sha256_text(ranking.dense_query.model_dump_json()) if ranking.dense_query else None
        ),
        candidates=tuple(diagnostics),
    )


def _dense_scores(
    candidates: tuple[EvidenceCandidate, ...],
    *,
    topic: str,
    tenant_id: UUID,
    ranking: RetrievalRankingInput,
) -> dict[UUID, float]:
    snapshot, query = ranking.dense_snapshot, ranking.dense_query
    if snapshot is None or query is None:
        _invalid("missing_dense_embeddings")
    assert snapshot is not None and query is not None
    if snapshot.tenant_id != tenant_id or query.tenant_id != tenant_id:
        _invalid("dense_tenant_mismatch")
    if (snapshot.model, snapshot.revision, snapshot.dimensions) != (
        query.model,
        query.revision,
        query.dimensions,
    ):
        _invalid("embedding_space_mismatch")
    if query.query_hash != sha256_text(topic):
        _invalid("stale_query_embedding")
    vectors = {item.evidence_id: item for item in snapshot.evidence}
    if set(vectors) != {item.material.evidence_id for item in candidates}:
        _invalid("dense_candidate_membership_mismatch")
    query_norm = math.hypot(*query.vector)
    result = {}
    for item in candidates:
        embedded = vectors[item.material.evidence_id]
        if embedded.content_hash != item.material.content_hash:
            _invalid("stale_evidence_embedding")
        norm = math.hypot(*embedded.vector)
        # Normalize before multiplying to avoid overflow for finite large vector elements.
        cosine = math.fsum(
            (left / norm) * (right / query_norm)
            for left, right in zip(embedded.vector, query.vector, strict=True)
        )
        result[item.material.evidence_id] = min(1.0, max(-1.0, cosine))
    return result


def _ranks(scores: dict[UUID, float]) -> dict[UUID, int]:
    ranked = sorted(scores, key=lambda key: (-scores[key], key.int))
    return {key: index for index, key in enumerate(ranked, start=1) if scores[key] > 0}


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(word for word in _TOKEN.findall(text.casefold()) if word not in _STOPWORDS)


def _invalid(reason: str) -> None:
    raise RetrievalValidationError(
        "relevance ranking inputs are incompatible", details={"reason": reason}
    )
