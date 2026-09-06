"""HTTP serving remains usable when serverless artifact volumes are full or read-only."""

import asyncio
import errno
from importlib import import_module
from pathlib import Path
from typing import Literal
from unittest.mock import Mock
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from tests.api.test_continuation import deployment as deployment
from tests.integration.test_full_workflow import NeverCalledProvider, SequenceProvider

from ceo_voice.api import create_app
from ceo_voice.config import ApiSettings, ModelSettings, Settings
from ceo_voice.integration.artifacts import ArtifactWriter
from ceo_voice.models.enums import Platform
from ceo_voice.services import PublishedProfileBundle
from ceo_voice.showcase import ShowcaseWorkflowService

api_module = import_module("ceo_voice.api.app")
service_module = import_module("ceo_voice.showcase.service")
EDITED = "Clear ownership improves reliable execution by making decisions explicit."


@pytest.mark.parametrize("failure", [errno.ENOSPC, errno.EROFS])
def test_published_api_and_cold_continuation_do_not_write_artifacts(
    failure: int,
    deployment: PublishedProfileBundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full volume cannot turn a successful provider result into HTTP 500."""

    settings = Settings(
        _env_file=None,
        api=ApiSettings(
            artifact_storage="memory",
            published_profile_catalog=Path("already-loaded/catalog.json"),
            continuation_key=SecretStr(Fernet.generate_key().decode()),
        ),
        model=ModelSettings(
            enabled=True,
            provider="openai",
            generation_model="fixture",
            api_key=SecretStr("synthetic-test-key"),
        ),
    )
    monkeypatch.setattr(api_module, "load_published_profile_catalog", lambda path: (deployment,))
    monkeypatch.setattr(api_module, "create_model_provider", lambda *args: NeverCalledProvider())
    monkeypatch.setattr(service_module, "SESSION_CACHE_LIMIT", 2)
    write = Mock(side_effect=OSError(failure, "artifact volume unavailable"))
    mkdir = Mock(side_effect=OSError(failure, "artifact volume unavailable"))
    temporary = Mock(side_effect=OSError(failure, "temporary volume unavailable"))

    with monkeypatch.context() as storage:
        storage.setattr(Path, "write_text", write)
        storage.setattr(Path, "mkdir", mkdir)
        storage.setattr(service_module, "gettempdir", temporary)
        original_app = create_app(settings)
        with TestClient(original_app) as first:
            snapshots = []
            for _ in range(3):
                generated = first.post(
                    "/api/v1/workflows/generate",
                    json={
                        "profile_slug": deployment.slug,
                        "platform": "linkedin",
                        "idea": "Explain clear ownership.",
                    },
                )
                assert generated.status_code == 200, generated.text
                snapshots.append(generated.json())
        initial = snapshots[0]
        identifier = UUID(initial["session_id"])
        with pytest.raises(KeyError):
            original_app.state.workflows.get(identifier)
        # Eviction and a separate process preserve the complete editing/evaluation state.
        monkeypatch.setattr(
            api_module, "create_model_provider", lambda *args: SequenceProvider((EDITED,))
        )
        cold_app = create_app(settings)
        with TestClient(cold_app) as second:
            resumed = second.post(
                f"/api/v1/workflows/{identifier}/resume",
                json={"continuation_token": initial["continuation_token"]},
            )
            assert resumed.status_code == 200, resumed.text
            assert resumed.json()["content"] == initial["content"]
            session = cold_app.state.workflows.get(identifier)
            artifacts = session.outcome.artifacts
            assert artifacts.voice_profile is deployment.voice_profile
            assert artifacts.virality_profile is deployment.virality_profile
            assert artifacts.context is not None and artifacts.retrieval is not None
            revised = second.post(
                f"/api/v1/workflows/{identifier}/revoice",
                json={
                    "continuation_token": resumed.json()["continuation_token"],
                    "content": EDITED,
                    "expected_revision": 0,
                },
            )
            assert revised.status_code == 200, revised.text
            assert revised.json()["revoiced_content"] == EDITED
        with TestClient(create_app(settings)) as third:
            evaluated = third.post(
                f"/api/v1/workflows/{identifier}/evaluate",
                json={"continuation_token": revised.json()["continuation_token"]},
            )
            assert evaluated.status_code == 200, evaluated.text
            assert evaluated.json()["dimensions"]
            assert evaluated.json()["revision_count"] == 1
    write.assert_not_called()
    mkdir.assert_not_called()
    temporary.assert_not_called()


def test_default_showcase_api_does_not_write_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    writes = Mock(side_effect=OSError(errno.ENOSPC, "full artifact volume"))
    monkeypatch.setattr(Path, "write_text", writes)
    monkeypatch.setattr(Path, "mkdir", writes)
    monkeypatch.setattr(service_module, "gettempdir", writes)
    with TestClient(
        create_app(Settings(_env_file=None, model=ModelSettings(enabled=False)))
    ) as api:
        generated = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "ali-ghodsi",
                "platform": "linkedin",
                "idea": "Explain clear ownership.",
            },
        )
        assert generated.status_code == 200, generated.text
    writes.assert_not_called()


def test_direct_offline_service_keeps_artifact_files_by_default(
    tmp_path: Path, deployment: PublishedProfileBundle
) -> None:
    service = ShowcaseWorkflowService(
        output_directory=tmp_path,
        provider=NeverCalledProvider(),
        model="fixture",
        published_bundles=(deployment,),
    )
    session = asyncio.run(
        service.generate(
            profile_slug=deployment.slug,
            platform=Platform.LINKEDIN,
            content_type="post",
            idea="Explain clear ownership.",
            constraints=(),
        )
    )
    directory = session.outcome.artifact_directory
    assert (directory / "integration-outcome.json").is_file()
    assert (directory / "voice-profile.json").is_file()
    assert (directory / "retrieval-bundle.json").is_file()
    assert (directory / "generated-draft.json").is_file()


def test_memory_writer_does_not_serialize_and_filesystem_failure_is_not_suppressed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = Mock()
    model.model_dump_json.side_effect = AssertionError("memory artifacts must not be serialized")
    ArtifactWriter(storage="memory").write_model(tmp_path, "record", model)
    model.model_dump_json.assert_not_called()
    monkeypatch.setattr(Path, "mkdir", Mock(side_effect=OSError(errno.ENOSPC, "full volume")))
    with pytest.raises(OSError):
        ArtifactWriter().write_model(tmp_path, "record", model)


@pytest.mark.parametrize("storage", ["memory", "filesystem"])
def test_injected_service_preserves_its_explicit_artifact_storage(
    storage: Literal["memory", "filesystem"],
    tmp_path: Path,
    deployment: PublishedProfileBundle,
) -> None:
    service = ShowcaseWorkflowService(
        output_directory=tmp_path / "artifacts",
        provider=NeverCalledProvider(),
        model="fixture",
        published_bundles=(deployment,),
        artifact_storage=storage,
    )
    settings = Settings(
        _env_file=None,
        model=ModelSettings(enabled=False),
        api=ApiSettings(artifact_storage="filesystem" if storage == "memory" else "memory"),
    )
    with TestClient(create_app(settings, service)) as api:
        generated = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": deployment.slug,
                "platform": "linkedin",
                "idea": "Explain clear ownership.",
            },
        )
        assert generated.status_code == 200, generated.text
    artifact = tmp_path / "artifacts" / generated.json()["session_id"] / "integration-outcome.json"
    assert artifact.is_file() is (storage == "filesystem")


def test_http_filesystem_artifact_storage_is_explicitly_configurable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CEO_VOICE_API__ARTIFACT_STORAGE", "filesystem")
    settings = Settings(_env_file=None, model=ModelSettings(enabled=False))
    assert settings.api.artifact_storage == "filesystem"
    monkeypatch.setattr(service_module, "gettempdir", lambda: str(tmp_path))
    with TestClient(create_app(settings)) as api:
        generated = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "ali-ghodsi",
                "platform": "linkedin",
                "idea": "Explain clear ownership.",
            },
        )
        assert generated.status_code == 200, generated.text
    assert (
        tmp_path
        / "ceo-voice-showcase"
        / generated.json()["session_id"]
        / "integration-outcome.json"
    ).is_file()
