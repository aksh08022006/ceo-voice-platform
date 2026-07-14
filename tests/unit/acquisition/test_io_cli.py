"""Bounded source-catalog file and CLI tests."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from ceo_voice.acquisition import (
    AcquisitionMethod,
    AuthorshipBasis,
    CorpusContentRole,
    SourceCatalogEntry,
    SourceCatalogManifest,
    SourceReviewStatus,
    load_source_catalog,
)
from ceo_voice.models.enums import DocumentSourceType, DocumentType, Platform
from ceo_voice.profiles.cli import main


def _manifest() -> SourceCatalogManifest:
    now = datetime(2026, 7, 14, tzinfo=UTC)
    entry = SourceCatalogEntry(
        source_id="official-page",
        source=DocumentSourceType.OTHER,
        platform=Platform.GENERIC,
        document_type=DocumentType.OTHER,
        canonical_url="https://example.com/leader",
        title="Official leader page",
        publisher="Example",
        publication_date=None,
        acquisition_method=AcquisitionMethod.PUBLIC_WEB,
        review_status=SourceReviewStatus.PENDING,
        authorship_basis=AuthorshipBasis.UNKNOWN,
        content_role=CorpusContentRole.FACTUAL_CONTEXT,
        access_notes="Public identity anchor; not voice evidence.",
    )
    return SourceCatalogManifest(
        tenant_id=UUID(int=1),
        leader_id=UUID(int=2),
        leader_name="Example Leader",
        entries=(entry,),
        created_at=now,
    )


def test_load_catalog_and_cli_write_honest_not_ready_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "catalog.json"
    output = tmp_path / "reports" / "audit.json"
    path.write_text(_manifest().model_dump_json(indent=2), encoding="utf-8")

    assert load_source_catalog(path) == _manifest()
    assert (
        main(
            [
                "audit-corpus",
                "--manifest",
                str(path),
                "--output",
                str(output),
                "--pretty",
            ]
        )
        == 3
    )
    result = json.loads(capsys.readouterr().out)
    assert result["acquisition_ready"] is False
    assert json.loads(output.read_text(encoding="utf-8")) == result


def test_cli_accepts_explicit_discovery_policy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "catalog.json"
    policy = tmp_path / "policy.json"
    path.write_text(_manifest().model_dump_json(), encoding="utf-8")
    policy.write_text(
        json.dumps(
            {
                "minimum_eligible_documents": 1,
                "minimum_primary_documents": 1,
                "minimum_primary_platforms": 1,
                "minimum_documents_per_primary_platform": 1,
                "maximum_supplementary_fraction": 1,
                "require_publication_dates": False,
                "require_human_review": False,
            }
        ),
        encoding="utf-8",
    )

    assert main(["audit-corpus", "--manifest", str(path), "--policy", str(policy)]) == 3
    assert json.loads(capsys.readouterr().out)["total_entries"] == 1


@pytest.mark.parametrize(
    ("filename", "leader_name"),
    (
        ("ali-ghodsi.discovery.json", "Ali Ghodsi"),
        ("matei-zaharia.discovery.json", "Matei Zaharia"),
    ),
)
def test_committed_discovery_catalogs_remain_valid_and_honestly_unready(
    filename: str,
    leader_name: str,
) -> None:
    manifest = load_source_catalog(Path("configs/source-catalogs") / filename)

    assert manifest.leader_name == leader_name
    assert all(not entry.eligible_for_voice_analysis for entry in manifest.entries)
