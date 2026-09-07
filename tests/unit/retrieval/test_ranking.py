"""Controlled relevance experiments and embedding-boundary regression tests.

The tiny vectors below are explicit test fixtures, not empirical semantic-model results.
"""

import asyncio
import math
from uuid import UUID

import pytest

from ceo_voice.core.exceptions import RetrievalValidationError
from ceo_voice.retrieval import (
    DenseEmbeddingSnapshot,
    DenseEvidenceEmbedding,
    DenseQueryEmbedding,
    EvidenceMaterial,
    InMemoryEvidenceMaterialReader,
    RetrievalBundle,
    RetrievalIntelligenceEngine,
    RetrievalRankingInput,
    RetrievalRankingMode,
)
from ceo_voice.retrieval.enums import EvidencePurpose, EvidenceSourceKind, KnowledgeKind
from ceo_voice.retrieval.ranking import bm25_scores, reciprocal_rank_fusion, rerank_candidates
from ceo_voice.retrieval.scoring import score_evidence
from ceo_voice.retrieval.selection import EvidenceCandidate
from ceo_voice.utils.hashing import sha256_text
from tests.unit.retrieval.test_engine import _input
from tests.unit.voice.factories import TENANT_ID


def _candidate(index: int, content: str, *, authority: float = 0.7) -> EvidenceCandidate:
    material = EvidenceMaterial(
        evidence_id=UUID(int=index),
        tenant_id=TENANT_ID,
        document_id=UUID(int=100 + index),
        document_version=1,
        content=content,
        content_hash=sha256_text(content),
        source_kind=EvidenceSourceKind.HVM,
        platform=None,
        publication_time=None,
        diversity_cluster_id=f"document:{index}",
    )
    score = score_evidence(
        confidence=authority,
        coverage=authority,
        freshness=authority,
        platform_match=authority,
        feature_importance=authority,
        representativeness=authority,
        profile_authority=authority,
        intent_match=authority,
    )
    return EvidenceCandidate(
        material=material,
        score=score,
        priority=80,
        purposes={EvidencePurpose.VOICE_SUPPORT},
        requirements={"voice:test-feature": KnowledgeKind.VOICE_FEATURE},
        feature_ids={"test-feature"},
    )


def _hybrid(
    materials: tuple[EvidenceMaterial, ...],
    topic: str,
    *,
    vectors: tuple[tuple[float, ...], ...] | None = None,
) -> RetrievalRankingInput:
    vectors = vectors or tuple((1.0, 0.0) for _ in materials)
    return RetrievalRankingInput(
        mode=RetrievalRankingMode.HYBRID,
        dense_snapshot=DenseEmbeddingSnapshot(
            tenant_id=TENANT_ID,
            model="unit-test-vectors",
            revision="fixture-v1",
            dimensions=2,
            evidence=tuple(
                DenseEvidenceEmbedding(
                    evidence_id=item.evidence_id,
                    content_hash=item.content_hash,
                    vector=vector,
                )
                for item, vector in zip(materials, vectors, strict=True)
            ),
        ),
        dense_query=DenseQueryEmbedding(
            tenant_id=TENANT_ID,
            model="unit-test-vectors",
            revision="fixture-v1",
            dimensions=2,
            query_hash=sha256_text(topic),
            vector=(1.0, 0.0),
        ),
    )


def test_bm25_prefers_query_matches_and_normalizes_document_length() -> None:
    scores = bm25_scores(
        "latency",
        ("latency", "latency " + "unrelated " * 100, "ownership and culture"),
    )
    assert scores[0] > scores[1] > scores[2] == 0
    assert bm25_scores("the and", ("the and", "unrelated")) == (0, 0)
    assert bm25_scores("query", ("the and",)) == (0,)
    assert bm25_scores("query", ()) == ()
    assert bm25_scores("科学", ("科学", "other"))[0] > 0


def test_rrf_arithmetic_is_weighted_and_missing_branches_contribute_nothing() -> None:
    assert reciprocal_rank_fusion(1, 2, sparse_weight=0.25, k=60) == pytest.approx(
        0.25 / 61 + 0.75 / 62
    )
    assert reciprocal_rank_fusion(None, 1, sparse_weight=0.25) == pytest.approx(0.75 / 61)
    assert reciprocal_rank_fusion(None, None) == 0


def test_bm25_changes_relevance_without_changing_purpose_or_governed_requirements() -> None:
    generic = _candidate(1, "Teams improve ownership and execution.", authority=0.8)
    relevant = _candidate(2, "Database latency and throughput determine response time.")
    candidates = (generic, relevant)
    assert generic.score.base_score > relevant.score.base_score
    before = tuple((set(item.purposes), dict(item.requirements)) for item in candidates)
    report = rerank_candidates(
        candidates,
        topic="database latency",
        tenant_id=TENANT_ID,
        ranking=RetrievalRankingInput(mode=RetrievalRankingMode.BM25),
    )
    assert relevant.score.base_score > generic.score.base_score
    assert report is not None and report.embedding_model is None
    assert report.candidates[1].lexical_rank == 1
    assert before == tuple((item.purposes, item.requirements) for item in candidates)
    assert all(EvidencePurpose.FACTUAL_SUPPORT not in item.purposes for item in candidates)


def test_hybrid_can_recover_a_lexically_disjoint_candidate_with_explicit_dense_evidence() -> None:
    lexical = _candidate(1, "Response time can improve.")
    semantic = _candidate(2, "Lower database latency by batching network requests.")
    irrelevant = _candidate(3, "The annual hiring plan is ready.")
    candidates = (lexical, semantic, irrelevant)
    ranking = _hybrid(
        tuple(item.material for item in candidates),
        "response time",
        vectors=((0.0, 1.0), (1.0, 0.0), (-1.0, 0.0)),
    ).model_copy(update={"sparse_weight": 0.2})
    report = rerank_candidates(
        candidates, topic="response time", tenant_id=TENANT_ID, ranking=ranking
    )
    assert report is not None
    assert semantic.score.base_score > lexical.score.base_score > irrelevant.score.base_score
    recovered = report.candidates[1]
    assert recovered.lexical_rank is None and recovered.dense_rank == 1
    assert recovered.relevance_score == pytest.approx(0.8)
    assert report.candidates[2].dense_score == -1
    assert report.candidates[2].dense_rank is None
    assert report.embedding_model == "unit-test-vectors"


def test_baseline_explicit_or_omitted_preserves_existing_bundle_serialization() -> None:
    value, materials = _input()
    engine = RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(materials))
    original = asyncio.run(engine.retrieve(value))
    explicit = asyncio.run(
        engine.retrieve(value.model_copy(update={"ranking": RetrievalRankingInput()}))
    )
    assert original == explicit
    payload = original.model_dump(mode="json")
    assert "ranking_report" not in payload["metadata"]
    assert RetrievalBundle.model_validate(payload) == original


def test_engine_ranking_is_deterministic_sealed_and_uses_topic_query_only() -> None:
    value, materials = _input(with_supplied_evidence=True)
    engine = RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(materials))
    eligible = asyncio.run(engine.candidate_materials(value))
    assert len(eligible) == len(materials) + 1
    assert any(item.source_kind is EvidenceSourceKind.REQUEST for item in eligible)
    for ranking in (
        RetrievalRankingInput(mode=RetrievalRankingMode.BM25),
        _hybrid(eligible, value.request.topic),
    ):
        ranked_input = value.model_copy(update={"ranking": ranking})
        first = asyncio.run(engine.retrieve(ranked_input))
        second = asyncio.run(engine.retrieve(ranked_input))
        assert first == second
        report = first.metadata.ranking_report
        assert report is not None and report.query_hash == sha256_text(value.request.topic)
        assert first.metadata.semantic_ranking_used == (ranking.mode is RetrievalRankingMode.HYBRID)
        assert RetrievalBundle.model_validate_json(first.model_dump_json()) == first
        assert {item.requirement for item in first.report.coverage} >= {
            *(f"voice:{item.feature_id}" for item in first.voice_features),
            *(f"structure:{item.pattern_id}" for item in first.structural_guidance),
        }


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("snapshot_tenant", "dense_tenant_mismatch"),
        ("query_tenant", "dense_tenant_mismatch"),
        ("model", "embedding_space_mismatch"),
        ("revision", "embedding_space_mismatch"),
        ("dimensions", "embedding_space_mismatch"),
        ("query_hash", "stale_query_embedding"),
        ("content_hash", "stale_evidence_embedding"),
        ("candidate_id", "dense_candidate_membership_mismatch"),
    ),
)
def test_hybrid_rejects_mismatched_and_stale_embeddings(mutation: str, reason: str) -> None:
    candidate = _candidate(1, "latency")
    ranking = _hybrid((candidate.material,), "latency")
    assert ranking.dense_snapshot is not None and ranking.dense_query is not None
    snapshot, query = ranking.dense_snapshot, ranking.dense_query
    if mutation == "snapshot_tenant":
        snapshot = snapshot.model_copy(update={"tenant_id": UUID(int=987)})
    elif mutation == "query_tenant":
        query = query.model_copy(update={"tenant_id": UUID(int=987)})
    elif mutation in {"model", "revision"}:
        query = query.model_copy(update={mutation: "different"})
    elif mutation == "dimensions":
        query = query.model_copy(update={"dimensions": 3, "vector": (1.0, 0.0, 0.0)})
    elif mutation == "query_hash":
        query = query.model_copy(update={"query_hash": sha256_text("stale topic")})
    else:
        embedded = snapshot.evidence[0].model_copy(
            update=(
                {"content_hash": sha256_text("stale text")}
                if mutation == "content_hash"
                else {"evidence_id": UUID(int=987)}
            )
        )
        snapshot = snapshot.model_copy(update={"evidence": (embedded,)})
    ranking = ranking.model_copy(update={"dense_snapshot": snapshot, "dense_query": query})
    with pytest.raises(RetrievalValidationError) as caught:
        rerank_candidates((candidate,), topic="latency", tenant_id=TENANT_ID, ranking=ranking)
    assert caught.value.details["reason"] == reason


@pytest.mark.parametrize("vector", ((0.0, 0.0), (math.nan, 1.0), (math.inf, 0.0)))
def test_dense_vectors_reject_nonfinite_and_zero_vectors(vector: tuple[float, ...]) -> None:
    with pytest.raises(ValueError, match="vectors"):
        DenseEvidenceEmbedding(
            evidence_id=UUID(int=1), content_hash=sha256_text("a"), vector=vector
        )


def test_dense_contracts_reject_ambiguous_or_incomplete_spaces() -> None:
    material = _candidate(1, "latency").material
    ranking = _hybrid((material,), "latency")
    assert ranking.dense_snapshot is not None and ranking.dense_query is not None
    snapshot, query = ranking.dense_snapshot, ranking.dense_query
    with pytest.raises(ValueError, match="both"):
        RetrievalRankingInput(mode=RetrievalRankingMode.HYBRID)
    with pytest.raises(ValueError, match="only"):
        RetrievalRankingInput(mode=RetrievalRankingMode.BM25, dense_snapshot=snapshot)
    with pytest.raises(ValueError, match="unique"):
        DenseEmbeddingSnapshot(**{**snapshot.model_dump(), "evidence": snapshot.evidence * 2})
    with pytest.raises(ValueError, match="dimensions"):
        DenseEmbeddingSnapshot(**{**snapshot.model_dump(), "dimensions": 3})
    with pytest.raises(ValueError, match="dimensions"):
        DenseQueryEmbedding(**{**query.model_dump(), "dimensions": 3})


def test_ranking_ties_are_independent_of_reader_order() -> None:
    def ranked(reverse: bool) -> tuple[UUID, ...]:
        candidates = tuple(_candidate(index, "latency") for index in (1, 2, 3))
        report = rerank_candidates(
            tuple(reversed(candidates)) if reverse else candidates,
            topic="latency",
            tenant_id=TENANT_ID,
            ranking=RetrievalRankingInput(mode=RetrievalRankingMode.BM25),
        )
        assert report is not None
        return tuple(item.evidence_id for item in report.candidates)

    assert ranked(False) == ranked(True) == tuple(UUID(int=index) for index in (1, 2, 3))
