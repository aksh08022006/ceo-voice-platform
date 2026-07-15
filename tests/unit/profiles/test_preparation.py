"""Governed export-to-profile preparation workflow tests."""

import asyncio
import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from ceo_voice.acquisition import load_source_catalog
from ceo_voice.models.enums import DocumentSourceType
from ceo_voice.profiles import (
    CorpusImportSource,
    CorpusPreparationManifest,
    CorpusPreparationService,
    ProfileBuildManifest,
)
from ceo_voice.profiles.cli import main
from ceo_voice.voice import (
    ProfileLineage,
    SemanticVersion,
    SourceModality,
    TargetIdentityType,
    VoiceIdentity,
)

ROOT = Path(__file__).parents[3]
EXAMPLES = ROOT / "data" / "examples"


def preparation_manifest() -> CorpusPreparationManifest:
    catalog = load_source_catalog(EXAMPLES / "source-catalog.json")
    identity = VoiceIdentity(
        id=UUID(int=501),
        tenant_id=catalog.tenant_id,
        leader_id=catalog.leader_id,
        display_name=catalog.leader_name,
        target_type=TargetIdentityType.PERSONAL_AUTHORSHIP,
        policy_version=SemanticVersion.parse("1.0.0"),
        created_at=catalog.created_at,
    )
    return CorpusPreparationManifest(
        catalog=catalog,
        identity=identity,
        lineage=ProfileLineage(
            id=UUID(int=502),
            tenant_id=catalog.tenant_id,
            voice_identity_id=identity.id,
            lineage_policy_version=SemanticVersion.parse("1.0.0"),
            created_at=catalog.created_at,
        ),
        sources=(
            CorpusImportSource(
                source=DocumentSourceType.LINKEDIN,
                export_path=Path("local-export.jsonl"),
                modality=SourceModality.AUTHORED_WRITTEN,
            ),
        ),
        actor_id=UUID(int=503),
        requested_at=catalog.reviewed_at or catalog.created_at,
    )


def test_reviewed_export_becomes_authorized_profile_manifest() -> None:
    result = asyncio.run(CorpusPreparationService(EXAMPLES).prepare(preparation_manifest()))

    assert len(result.profile_manifest.corpus.documents) == 2
    assert result.ingestion_runs[0].stored_count == 2
    assert result.ingestion_runs[0].rejected_count == 0
    for item in result.profile_manifest.corpus.documents:
        receipt = item.document.metadata["authorization_receipt"]
        assert isinstance(receipt, dict)
        assert receipt["reviewer_id"] == "30000000-0000-0000-0000-000000000003"
        assert item.source_modality is SourceModality.AUTHORED_WRITTEN


def test_preparation_manifest_rejects_unsafe_or_ambiguous_sources() -> None:
    source = preparation_manifest().sources[0]
    with pytest.raises(ValidationError, match="confined"):
        CorpusImportSource(
            source=source.source,
            export_path=Path("../private.jsonl"),
            modality=source.modality,
        )
    with pytest.raises(ValidationError, match="one export"):
        CorpusPreparationManifest.model_validate(
            {**preparation_manifest().model_dump(), "sources": (source, source)}
        )


def test_prepare_corpus_cli_writes_build_manifest_and_trace_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    operation = tmp_path / "prepare.json"
    output = tmp_path / "profile-manifest.json"
    operation.write_text(preparation_manifest().model_dump_json(indent=2), encoding="utf-8")

    exit_code = main(
        [
            "prepare-corpus",
            "--manifest",
            str(operation),
            "--export-root",
            str(EXAMPLES),
            "--output",
            str(output),
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert summary["documents"] == 2
    assert summary["rejected"] == 0
    assert ProfileBuildManifest.model_validate_json(output.read_text(encoding="utf-8"))
    assert output.with_suffix(".preparation.json").exists()
