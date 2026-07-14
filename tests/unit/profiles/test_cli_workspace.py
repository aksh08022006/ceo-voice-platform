"""Local workspace persistence, CLI, and workflow-contract tests."""

import asyncio
import json
from io import StringIO
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.analysis import ObservationSet
from ceo_voice.core.exceptions import StorageError
from ceo_voice.profiles import (
    CorpusObservationBatch,
    CuratedCorpus,
    InMemoryProfileWorkspace,
    JsonProfileWorkspace,
    ObservationCacheKey,
    ProgressEvent,
    ProgressKind,
    ScalarBaselineSnapshot,
    build_tier1_runtime,
    create_tier1_profile_builder,
)
from ceo_voice.profiles.cli import ConsoleProgressSink, main
from ceo_voice.profiles.enums import BuildStage
from ceo_voice.voice import ReleaseChange
from tests.unit.profiles.factories import IDENTITY_ID, document, identity, lineage, manifest


def test_json_workspace_persists_profiles_observations_and_release_catalog(
    tmp_path: Path,
) -> None:
    workspace = JsonProfileWorkspace(tmp_path / "workspace")
    profile = asyncio.run(create_tier1_profile_builder(workspace=workspace).build(manifest(1, 2)))
    reloaded = JsonProfileWorkspace(tmp_path / "workspace")

    assert asyncio.run(reloaded.get_published(IDENTITY_ID, profile.corpus_hash)) == profile
    assert (
        asyncio.run(
            reloaded.get(
                profile.managed_release.release.tenant_id, profile.managed_release.release.id
            )
        )
        == profile.managed_release
    )
    assert (
        len(
            asyncio.run(
                reloaded.list_lineage(
                    profile.managed_release.release.tenant_id,
                    profile.managed_release.release.lineage_id,
                )
            )
        )
        == 1
    )


def test_workspace_rejects_cache_and_release_transaction_conflicts() -> None:
    workspace = InMemoryProfileWorkspace()
    profile = asyncio.run(create_tier1_profile_builder(workspace=workspace).build(manifest(1)))
    observation_set_run = profile.observations[0].id
    key = ObservationCacheKey(
        analysis_run_id=observation_set_run,
        document_id=document(1).id,
        document_version=1,
        document_fingerprint=document(1).document_fingerprint,
        registry_snapshot_hash="a" * 64,
    )
    cached_set = next(iter(workspace._observations.values()))
    with pytest.raises(StorageError, match="does not match"):
        asyncio.run(workspace.save_observations(key, cached_set))
    with pytest.raises(StorageError, match="at least one"):
        asyncio.run(workspace.commit(()))
    record = profile.managed_release
    duplicate = ReleaseChange(record=record, expected_revision=record.revision)
    with pytest.raises(StorageError, match="duplicate"):
        asyncio.run(workspace.commit((duplicate, duplicate)))


def test_cli_builds_profile_writes_output_and_resumes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path = tmp_path / "manifest.json"
    workspace_path = tmp_path / "workspace"
    output_path = tmp_path / "published.json"
    manifest_path.write_text(manifest(1, 2).model_dump_json(indent=2), encoding="utf-8")
    arguments = [
        "build",
        "--manifest",
        str(manifest_path),
        "--workspace",
        str(workspace_path),
        "--output",
        str(output_path),
        "--pretty",
    ]

    assert main(arguments) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["release_status"] == "active"
    assert first["release_version"] == 1
    assert output_path.exists()
    assert main(arguments) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["release_id"] == first["release_id"]


def test_cli_reports_invalid_manifest_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{}", encoding="utf-8")

    assert main(["build", "--manifest", str(path), "--workspace", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().err)["code"] == "invalid_manifest"


def test_console_progress_sink_emits_machine_readable_event() -> None:
    stream = StringIO()
    event = ProgressEvent(
        build_id=UUID(int=1),
        kind=ProgressKind.BUILD_STARTED,
        stage=BuildStage.ANALYZING,
        completed=0,
        total=2,
        occurred_at=manifest(1).requested_at,
        message="Started.",
    )
    ConsoleProgressSink(stream=stream).report(event)
    assert json.loads(stream.getvalue())["kind"] == "build_started"


def test_corpus_baseline_and_batch_contracts_reject_ambiguous_state() -> None:
    item = manifest(1).corpus.documents[0]
    with pytest.raises(ValidationError, match="one version"):
        CuratedCorpus(
            identity=identity(),
            lineage=lineage(),
            documents=(item, item),
        )
    wrong = item.document.model_copy(update={"ceo_id": UUID(int=999)})
    with pytest.raises(ValidationError, match="identity leader"):
        CuratedCorpus(
            identity=identity(),
            lineage=lineage(),
            documents=(item.model_copy(update={"document": wrong}),),
        )

    runtime = build_tier1_runtime()
    baseline = runtime.baselines.baselines[0]
    with pytest.raises(ValidationError, match="unique"):
        ScalarBaselineSnapshot(baselines=(baseline, baseline))
    with pytest.raises(KeyError):
        runtime.baselines.get(
            runtime.registry.definitions[-1].reference.model_copy(
                update={"feature_id": "missing.feature"}
            )
        )

    observation_set = next(iter(asyncio.run(_observation_sets())))
    with pytest.raises(ValidationError, match="counts"):
        CorpusObservationBatch(
            observation_sets=(observation_set,),
            failures=(),
            analyzed_documents=0,
            reused_documents=0,
        )


async def _observation_sets() -> tuple[ObservationSet, ...]:
    workspace = InMemoryProfileWorkspace()
    await create_tier1_profile_builder(workspace=workspace).build(manifest(1))
    return tuple(workspace._observations.values())
