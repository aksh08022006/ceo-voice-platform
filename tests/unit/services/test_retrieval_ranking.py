"""Embedding preparation isolation, cost bounds, response contracts and runtime wiring."""

import asyncio
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import JsonValue, SecretStr, ValidationError

from ceo_voice.api import create_app
from ceo_voice.config import ModelSettings, RetrievalSettings, Settings
from ceo_voice.core.exceptions import ConfigurationError, ProviderError, RetrievalValidationError
from ceo_voice.retrieval import InMemoryEvidenceMaterialReader, RetrievalIntelligenceEngine
from ceo_voice.services.retrieval_ranking import ConfiguredRetrievalRanking
from ceo_voice.showcase import ShowcaseWorkflowService
from tests.unit.retrieval.test_engine import _input


def model_settings() -> ModelSettings:
    return ModelSettings(
        enabled=True,
        provider="openai",
        generation_model="test-generation",
        embedding_model="test-embedding",
        api_key=SecretStr("test-only-credential"),
    )


def ranking_settings(**overrides: object) -> RetrievalSettings:
    return RetrievalSettings.model_validate(
        {
            "mode": "hybrid",
            "embedding_revision": "test-v1",
            "embedding_dimensions": 2,
            "embedding_batch_size": 2,
            **overrides,
        }
    )


class RecordingEmbeddings:
    """Contract fixture returns vectors in reverse order to verify response-index use."""

    def __init__(self, malformed: dict[str, JsonValue] | None = None) -> None:
        self.requests: list[dict[str, JsonValue]] = []
        self.malformed = malformed

    async def post(
        self, *, url: str, headers: dict[str, str], payload: dict[str, JsonValue]
    ) -> tuple[dict[str, JsonValue], int]:
        assert url == "https://api.openai.com/v1/embeddings"
        assert headers["Authorization"] == "Bearer test-only-credential"
        assert payload["encoding_format"] == "float"
        assert payload["dimensions"] == 2
        self.requests.append(payload)
        if self.malformed is not None:
            return self.malformed, 1
        texts = payload["input"]
        assert isinstance(texts, list)
        rows: list[JsonValue] = [
            {"index": index, "embedding": [float(len(str(text))), 1.0]}
            for index, text in reversed(tuple(enumerate(texts)))
        ]
        return {"model": "test-embedding", "data": rows}, 1


def test_baseline_and_bm25_never_need_a_model() -> None:
    value, materials = _input()
    for mode in ("baseline", "bm25"):
        preparer = ConfiguredRetrievalRanking(
            RetrievalSettings.model_validate({"mode": mode}), ModelSettings()
        )
        ranking = asyncio.run(preparer.prepare(value, materials))
        if mode == "baseline":
            assert ranking is None
        else:
            assert ranking is not None and ranking.mode == "bm25"


def test_hybrid_uses_real_adapter_vectors_and_reuses_only_same_scope() -> None:
    value, materials = _input()
    transport = RecordingEmbeddings()
    preparer = ConfiguredRetrievalRanking(ranking_settings(), model_settings(), transport)
    first = asyncio.run(preparer.prepare(value, materials))
    assert first is not None and first.dense_snapshot is not None
    assert first.dense_query is not None
    assert first.dense_query.vector == (float(len(value.request.topic)), 1.0)
    assert first.dense_snapshot.evidence[0].vector == (float(len(materials[0].content)), 1.0)
    count = len(transport.requests)
    assert all(len(request["input"]) <= 2 for request in transport.requests)  # type: ignore[arg-type]
    assert asyncio.run(preparer.prepare(value, materials)) == first
    assert len(transport.requests) == count
    other_leader = value.model_copy(
        update={"request": value.request.model_copy(update={"ceo_id": UUID(int=88991)})}
    )
    asyncio.run(preparer.prepare(other_leader, materials))
    assert len(transport.requests) > count
    changed = materials[0].model_copy(update={"tenant_id": UUID(int=88992)})
    with pytest.raises(RetrievalValidationError, match="another tenant"):
        asyncio.run(preparer.prepare(value, (changed,)))


def test_hybrid_preparation_flows_through_sealed_retrieval() -> None:
    value, materials = _input(with_supplied_evidence=True)
    engine = RetrievalIntelligenceEngine(InMemoryEvidenceMaterialReader(materials))
    eligible = asyncio.run(engine.candidate_materials(value))
    preparer = ConfiguredRetrievalRanking(
        ranking_settings(), model_settings(), RecordingEmbeddings()
    )
    ranking = asyncio.run(preparer.prepare(value, eligible))
    bundle = asyncio.run(engine.retrieve(value.model_copy(update={"ranking": ranking})))
    assert bundle.metadata.semantic_ranking_used
    assert bundle.metadata.ranking_report is not None
    assert bundle.metadata.ranking_report.embedding_model == "test-embedding"
    assert len(bundle.report.coverage) >= 2


def test_cache_eviction_and_disabled_cache_do_not_lose_batch_vectors() -> None:
    value, materials = _input()
    for capacity in (0, 1):
        transport = RecordingEmbeddings()
        preparer = ConfiguredRetrievalRanking(
            ranking_settings(embedding_cache_items=capacity), model_settings(), transport
        )
        first = asyncio.run(preparer.prepare(value, materials))
        count = len(transport.requests)
        assert first == asyncio.run(preparer.prepare(value, materials))
        assert len(transport.requests) > count


def test_hybrid_configuration_fails_closed() -> None:
    with pytest.raises(ConfigurationError, match="complete embedding provider"):
        ConfiguredRetrievalRanking(ranking_settings(), ModelSettings())
    with pytest.raises(ValidationError, match="hybrid retrieval requires"):
        Settings(_env_file=None, retrieval=ranking_settings())
    valid = Settings(_env_file=None, retrieval=ranking_settings(), model=model_settings())
    assert valid.retrieval.mode == "hybrid"
    with pytest.raises(ValidationError, match="hybrid retrieval requires"):
        Settings(
            _env_file=None,
            retrieval=ranking_settings(embedding_revision=None),
            model=model_settings(),
        )


def test_preparation_rejects_excessive_inputs_before_network_access() -> None:
    value, materials = _input()
    transport = RecordingEmbeddings()
    for options, candidates in (
        ({"maximum_embedding_items": 1}, materials),
        ({"maximum_embedding_input_bytes": 1}, materials),
        ({}, (materials[0], materials[0])),
        ({}, ()),
    ):
        preparer = ConfiguredRetrievalRanking(
            ranking_settings(**options), model_settings(), transport
        )
        with pytest.raises(RetrievalValidationError):
            asyncio.run(preparer.prepare(value, candidates))
    assert not transport.requests


@pytest.mark.parametrize(
    "response",
    [
        {"model": "wrong", "data": []},
        {"model": "test-embedding", "data": [{"index": 0, "embedding": [10**1000, 1]}] * 2},
        {"model": "test-embedding", "data": None},
        {"model": "test-embedding", "data": []},
        {"model": "test-embedding", "data": [None, None]},
        {"model": "test-embedding", "data": [{"index": 0, "embedding": [1, 0]}] * 2},
        {"model": "test-embedding", "data": [{"index": True, "embedding": [1, 0]}] * 2},
        {"model": "test-embedding", "data": [{"index": 3, "embedding": [1, 0]}] * 2},
        {"model": "test-embedding", "data": [{"index": 0, "embedding": [1]}] * 2},
        {"model": "test-embedding", "data": [{"index": 0, "embedding": [True, 1]}] * 2},
        {"model": "test-embedding", "data": [{"index": 0, "embedding": [float("nan"), 1]}] * 2},
        {"model": "test-embedding", "data": [{"index": 0, "embedding": [0, 0]}] * 2},
    ],
)
def test_provider_contract_failures_never_fallback_or_leak_payload(
    response: dict[str, JsonValue],
) -> None:
    value, materials = _input()
    transport = RecordingEmbeddings(response)
    preparer = ConfiguredRetrievalRanking(ranking_settings(), model_settings(), transport)
    with pytest.raises(ProviderError) as raised:
        asyncio.run(preparer.prepare(value, materials))
    assert "test-only-credential" not in str(raised.value)
    assert materials[0].content not in str(raised.value)


def test_browser_workflow_can_use_bm25_without_extra_product_inputs(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, retrieval=RetrievalSettings(mode="bm25"))
    service = ShowcaseWorkflowService(
        output_directory=tmp_path,
        retrieval_ranking=ConfiguredRetrievalRanking(settings.retrieval, settings.model),
    )
    with TestClient(create_app(settings, service)) as api:
        generated = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "ali-ghodsi",
                "platform": "linkedin",
                "idea": "Open AI infrastructure",
            },
        )
        assert generated.status_code == 200, generated.text
        session = service.get(UUID(generated.json()["session_id"]))
        bundle = session.outcome.artifacts.retrieval
        assert bundle is not None and bundle.metadata.ranking_report is not None
        assert bundle.metadata.ranking_report.mode == "bm25"
        assert not bundle.metadata.semantic_ranking_used
        ranking_path = session.outcome.artifact_directory / "retrieval-ranking.json"
        assert ranking_path.is_file()
        assert '"mode": "bm25"' in ranking_path.read_text()
        assert "retrieval_ranking" not in session.outcome.artifacts.model_dump()


def test_preparer_snapshots_configuration_before_caching_vectors() -> None:
    value, materials = _input()
    settings = ranking_settings()
    preparer = ConfiguredRetrievalRanking(settings, model_settings(), RecordingEmbeddings())
    settings.embedding_dimensions = 3
    settings.embedding_batch_size = 1
    result = asyncio.run(preparer.prepare(value, materials))
    assert result is not None and result.dense_snapshot is not None
    assert result.dense_snapshot.dimensions == 2
