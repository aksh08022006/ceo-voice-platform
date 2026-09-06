"""Cold-instance continuation and authenticated-snapshot rejection tests."""

import asyncio
import base64
import json
import time
import zlib
from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from tests.integration.test_full_workflow import (
    ApprovedFixtureBuilder,
    NeverCalledProvider,
    SequenceProvider,
    integration_input,
)

from ceo_voice.api import create_app
from ceo_voice.config import ApiSettings, ModelSettings, Settings
from ceo_voice.context import create_context_compiler
from ceo_voice.core.exceptions import ConfigurationError
from ceo_voice.generation import (
    GenerationEngine,
    GenerationPolicy,
    OutputValidator,
    PromptBuilder,
    PromptRenderer,
    TokenBudgetManager,
)
from ceo_voice.generation.enums import ProviderName
from ceo_voice.integration import IntegrationRunner
from ceo_voice.models.enums import ContentType, Platform
from ceo_voice.profiles import (
    InMemoryProfileWorkspace,
    build_tier1_runtime,
    create_tier1_profile_builder,
)
from ceo_voice.profiles.builder import VoiceProfileBuilder
from ceo_voice.services import PublishedProfileBundle
from ceo_voice.showcase import ShowcaseWorkflowService, continuation
from ceo_voice.showcase.continuation import ContinuationError, WorkflowContinuation
from ceo_voice.showcase.service import WorkflowSession
from ceo_voice.virality import InMemoryViralityWorkspace, create_virality_builder
from ceo_voice.voice import DownstreamPermission, FeatureRegistry

_DRAFT = "Clear ownership improves execution by making decisions explicit."
_EDITED = "Clear ownership improves reliable execution by making decisions explicit."


@pytest.fixture(scope="module")
def deployment(tmp_path_factory: pytest.TempPathFactory) -> PublishedProfileBundle:
    """Build genuine immutable artifact contracts from the existing synthetic test corpus."""
    directory = tmp_path_factory.mktemp("continuation-profile")
    runtime = build_tier1_runtime()
    registry = FeatureRegistry.build(
        registry_id=runtime.registry.id,
        version=runtime.registry.version,
        definitions=tuple(
            item.model_copy(
                update={
                    "downstream_permissions": (
                        *item.downstream_permissions,
                        DownstreamPermission.GENERATE,
                    )
                }
            )
            for item in runtime.registry.definitions
        ),
        created_at=runtime.registry.created_at,
    )
    workspace = InMemoryViralityWorkspace()
    provider = NeverCalledProvider()
    policy = GenerationPolicy(
        provider=ProviderName.OPENAI, model="fixture", model_context_tokens=30_000
    )
    budget = TokenBudgetManager(policy)
    prompts, renderer = PromptBuilder(budget), PromptRenderer(budget)
    runner = IntegrationRunner(
        profile_builder=cast(
            VoiceProfileBuilder,
            ApprovedFixtureBuilder(
                create_tier1_profile_builder(workspace=InMemoryProfileWorkspace(), runtime=runtime),
                registry,
            ),
        ),
        virality_builder=create_virality_builder(workspace=workspace),
        virality_workspace=workspace,
        feature_registry=registry,
        context_compiler=create_context_compiler(),
        prompt_builder=prompts,
        prompt_renderer=renderer,
        generation_engine=GenerationEngine(
            provider, prompts, renderer, OutputValidator(), policy=policy
        ),
    )
    command = integration_input(directory)
    built = asyncio.run(runner.run(command))
    assert (
        built.artifacts.voice_profile is not None and built.artifacts.virality_profile is not None
    )
    analysis = asyncio.run(
        workspace.get_analysis(
            built.artifacts.virality_profile.publication.release.analysis_snapshot
        )
    )
    assert analysis is not None
    return PublishedProfileBundle(
        slug="integration-leader",
        name="Fixture Leader",
        role="Fixture",
        summary="Synthetic test bundle.",
        voice_profile=built.artifacts.voice_profile,
        voice_corpus=command.profile_manifest.corpus,
        virality_profile=built.artifacts.virality_profile,
        virality_analysis=analysis,
        virality_corpus=command.virality_corpus,
        feature_registry=registry,
    )


def _service(directory: Path, deployment: PublishedProfileBundle) -> ShowcaseWorkflowService:
    return ShowcaseWorkflowService(
        output_directory=directory,
        provider=NeverCalledProvider(),
        model="fixture",
        published_bundles=(deployment,),
    )


def _session(service: ShowcaseWorkflowService) -> WorkflowSession:
    return asyncio.run(
        service.generate(
            profile_slug="integration-leader",
            platform=Platform.LINKEDIN,
            content_type=ContentType.POST,
            idea="Explain clear ownership.",
            constraints=(),
        )
    )


def _settings(key: str) -> Settings:
    return Settings(
        _env_file=None,
        model=ModelSettings(enabled=False),
        api=ApiSettings(continuation_key=SecretStr(key)),
    )


def test_cold_app_resumes_revoices_and_evaluates_exact_revision(
    tmp_path: Path, deployment: PublishedProfileBundle
) -> None:
    key = Fernet.generate_key().decode()
    original = _service(tmp_path / "original", deployment)
    cold = ShowcaseWorkflowService(
        output_directory=tmp_path / "cold",
        provider=SequenceProvider((_EDITED,)),
        model="fixture",
        published_bundles=(deployment,),
    )
    with TestClient(create_app(_settings(key), original)) as first:
        response = first.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "integration-leader",
                "platform": "linkedin",
                "idea": "Explain clear ownership.",
            },
        )
    assert response.status_code == 200, response.text
    initial = response.json()
    session_id, token = initial["session_id"], initial["continuation_token"]
    with pytest.raises(KeyError):
        cold.get(UUID(session_id))
    with TestClient(create_app(_settings(key), cold)) as second:
        resumed = second.post(
            f"/api/v1/workflows/{session_id}/resume", json={"continuation_token": token}
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["content"] == _DRAFT
        assert resumed.json()["revision_count"] == 0
        assert resumed.headers["Cache-Control"] == "no-store"
        revised = second.post(
            f"/api/v1/workflows/{session_id}/revoice",
            json={"continuation_token": token, "content": _EDITED, "expected_revision": 0},
        )
        assert revised.status_code == 200, revised.text
        revision = revised.json()
        assert revision["revision_count"] == 1
        assert revision["revoiced_content"] == _EDITED
        conflict = second.post(
            f"/api/v1/workflows/{session_id}/revoice",
            json={
                "continuation_token": revision["continuation_token"],
                "content": _EDITED,
                "expected_revision": 0,
            },
        )
        assert conflict.status_code == 409
    # A third isolated process receives the latest bearer snapshot, with no shared memory/files.
    final_service = _service(tmp_path / "third", deployment)
    with TestClient(create_app(_settings(key), final_service)) as third:
        evaluated = third.post(
            f"/api/v1/workflows/{session_id}/evaluate",
            json={"continuation_token": revision["continuation_token"]},
        )
        assert evaluated.status_code == 200, evaluated.text
        result = evaluated.json()
        assert result["revision_count"] == 1 and result["revoiced_content"] == _EDITED
        assert result["dimensions"]
        assert final_service.get(UUID(session_id)).edited is not None
        latest = third.post(
            f"/api/v1/workflows/{session_id}/resume",
            json={"continuation_token": result["continuation_token"]},
        )
        assert latest.json()["evaluation_score"] == result["evaluation_score"]


def test_http_requires_token_even_for_warm_session_and_rejects_forgery(
    tmp_path: Path, deployment: PublishedProfileBundle
) -> None:
    key = Fernet.generate_key().decode()
    service = _service(tmp_path, deployment)
    session = _session(service)
    token = WorkflowContinuation(key, (deployment,)).seal(session)
    with TestClient(create_app(_settings(key), service)) as api:
        assert api.get(f"/api/v1/workflows/{session.id}").status_code == 401
        assert api.post(f"/api/v1/workflows/{session.id}/evaluate").status_code == 401
        assert (
            api.post(
                f"/api/v1/workflows/{session.id}/revoice", json={"content": _EDITED}
            ).status_code
            == 401
        )
        forged = token[:30] + ("A" if token[30] != "A" else "B") + token[31:]
        assert (
            api.post(
                f"/api/v1/workflows/{session.id}/resume", json={"continuation_token": forged}
            ).status_code
            == 410
        )
        assert (
            api.post(
                f"/api/v1/workflows/{uuid4()}/resume", json={"continuation_token": token}
            ).status_code
            == 410
        )
        assert (
            api.post(
                f"/api/v1/workflows/{session.id}/resume",
                json={"continuation_token": "x" * (continuation.MAX_TOKEN_CHARACTERS + 1)},
            ).status_code
            == 422
        )


def test_codec_omits_profiles_and_restores_exact_immutable_artifacts(
    tmp_path: Path, deployment: PublishedProfileBundle
) -> None:
    key = Fernet.generate_key().decode()
    codec = WorkflowContinuation(key, (deployment,))
    session = _session(_service(tmp_path, deployment))
    token = codec.seal(session)
    raw = base64.urlsafe_b64decode(token)
    assert deployment.slug.encode() not in raw and _DRAFT.encode() not in raw
    snapshot = json.loads(zlib.decompress(Fernet(key.encode()).decrypt(token)))
    assert snapshot["outcome"]["artifacts"]["voice_profile"] is None
    assert snapshot["outcome"]["artifacts"]["virality_profile"] is None
    assert snapshot["outcome"]["artifacts"]["rendered_prompt"] is None
    restored = codec.open(token, session.id)
    assert restored.outcome.artifacts.voice_profile is deployment.voice_profile
    assert restored.outcome.artifacts.virality_profile is deployment.virality_profile
    assert restored.outcome.artifacts.draft == session.outcome.artifacts.draft


def test_codec_expiry_wrong_key_id_profile_drift_and_missing_profile(
    tmp_path: Path, deployment: PublishedProfileBundle
) -> None:
    key = Fernet.generate_key().decode()
    cipher, codec = Fernet(key.encode()), WorkflowContinuation(key, (deployment,), ttl_seconds=60)
    session = _session(_service(tmp_path, deployment))
    token = codec.seal(session)
    expired = cipher.encrypt_at_time(
        cipher.decrypt(token), current_time=int(time.time()) - 120
    ).decode()
    for invalid in (expired, "not-a-token", "", "☃"):
        with pytest.raises(ContinuationError):
            codec.open(invalid, session.id)
    with pytest.raises(ContinuationError):
        WorkflowContinuation(Fernet.generate_key().decode(), (deployment,)).open(token, session.id)
    with pytest.raises(ContinuationError, match="another session"):
        codec.open(token, uuid4())
    with pytest.raises(ContinuationError, match="no longer available"):
        WorkflowContinuation(key, ()).open(token, session.id)
    release = deployment.voice_profile.managed_release.release.model_copy(
        update={"validation_report_id": uuid4()}
    )
    voice = deployment.voice_profile.model_copy(
        update={
            "managed_release": deployment.voice_profile.managed_release.model_copy(
                update={"release": release}
            )
        }
    )
    changed = deployment.model_copy(update={"voice_profile": voice})
    with pytest.raises(ContinuationError, match="profile changed"):
        WorkflowContinuation(key, (changed,)).open(token, session.id)
    with pytest.raises(ContinuationError, match="pinned profile"):
        WorkflowContinuation(key, (changed,)).seal(session)


@pytest.mark.parametrize(
    "kind", ["json", "compressed", "truncated", "trailing", "expansion", "wrong_run"]
)
def test_authenticated_malformed_payloads_fail_closed(
    kind: str, tmp_path: Path, deployment: PublishedProfileBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = Fernet.generate_key().decode()
    cipher, codec = Fernet(key.encode()), WorkflowContinuation(key, (deployment,))
    session = _session(_service(tmp_path, deployment))
    compressed = cipher.decrypt(codec.seal(session))
    if kind == "json":
        compressed = zlib.compress(b"{}")
    elif kind == "compressed":
        compressed = b"invalid compressed bytes"
    elif kind == "truncated":
        compressed = compressed[:-1]
    elif kind == "trailing":
        compressed += b"trailing junk"
    elif kind == "expansion":
        monkeypatch.setattr(continuation, "MAX_SNAPSHOT_BYTES", 1000)
        compressed = zlib.compress(b"a" * 1001)
    else:
        snapshot = json.loads(zlib.decompress(compressed))
        snapshot["outcome"]["run_id"] = str(uuid4())
        compressed = zlib.compress(json.dumps(snapshot).encode())
    with pytest.raises(ContinuationError):
        codec.open(cipher.encrypt(compressed).decode(), session.id)


def test_seal_size_limits_config_and_session_memory_bound(
    tmp_path: Path, deployment: PublishedProfileBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = Fernet.generate_key().decode()
    codec = WorkflowContinuation(key, (deployment,))
    service = _service(tmp_path, deployment)
    session = _session(service)
    with pytest.raises(ConfigurationError, match="Fernet"):
        WorkflowContinuation("invalid", (deployment,))
    with pytest.raises(ValueError, match="positive"):
        WorkflowContinuation(key, (deployment,), ttl_seconds=0)
    monkeypatch.setattr(continuation, "MAX_SNAPSHOT_BYTES", 1)
    with pytest.raises(ContinuationError, match="size limit"):
        codec.seal(session)
    monkeypatch.setattr(continuation, "MAX_SNAPSHOT_BYTES", 8_000_000)
    monkeypatch.setattr(continuation, "MAX_TOKEN_CHARACTERS", 1)
    with pytest.raises(ContinuationError, match="token limit"):
        codec.seal(session)
    with pytest.raises(ContinuationError):
        codec.open("ab", session.id)
    unrelated = ShowcaseWorkflowService(output_directory=tmp_path / "unrelated")
    with pytest.raises(KeyError):
        unrelated.resume(session)
    identifiers = []
    for _ in range(35):
        identifier = uuid4()
        identifiers.append(identifier)
        service.resume(replace(session, id=identifier))
    with pytest.raises(KeyError):
        service.get(identifiers[0])
    assert service.get(identifiers[-1]).id == identifiers[-1]
