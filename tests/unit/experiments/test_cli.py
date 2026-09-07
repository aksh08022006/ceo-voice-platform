"""File-level experiment commands keep blind packets separate and never invent reviews."""

import json
import runpy
import sys
from pathlib import Path

import pytest

from ceo_voice.experiments import ExperimentReport, RatingSubmission
from ceo_voice.experiments.cli import main

from .factories import make_manifest, make_ratings


def test_prepare_score_and_empty_submission_files(tmp_path: Path) -> None:
    manifest = make_manifest()
    manifest_path = tmp_path / "study.json"
    output = tmp_path / "artifacts"
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    arguments = ["--manifest", str(manifest_path), "--output-dir", str(output)]
    assert main(["prepare", *arguments]) == 0
    assert (output / "assignment-key.private.json").stat().st_mode & 0o777 == 0o600
    ballots = json.loads((output / "ballots.json").read_text(encoding="utf-8"))
    assert len(ballots["ballots"]) == 9
    assert all("arm_a" not in ballot for ballot in ballots["ballots"])
    template = output / "ratings-template.json"
    empty = RatingSubmission.model_validate_json(template.read_text(encoding="utf-8"))
    assert empty.ratings == ()
    assert (
        main(["score", *arguments, "--ratings", str(template), "--bootstrap-samples", "100"]) == 0
    )
    report_path = output / "report.json"
    report = ExperimentReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    assert report.status == "awaiting_human_ratings"
    template.write_text(make_ratings(manifest).model_dump_json(), encoding="utf-8")
    assert (
        main(["score", *arguments, "--ratings", str(template), "--bootstrap-samples", "100"]) == 0
    )
    assert "Synthetic fixture" in (output / "report.md").read_text(encoding="utf-8")
    assert "No generation" in (output / "preparation.md").read_text(encoding="utf-8")


def test_cli_expected_errors_do_not_print_candidate_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "manifest.json"
    args = ["--manifest", str(path), "--output-dir", str(tmp_path / "out")]
    assert main(["prepare", *args]) == 2
    assert "could not be read" in capsys.readouterr().err
    path.write_text('{"secret candidate text": "private"}', encoding="utf-8")
    assert main(["prepare", *args]) == 2
    error = capsys.readouterr().err
    assert "validation failed" in error
    assert "private" not in error and "secret candidate text" not in error
    manifest = make_manifest()
    path.write_text(manifest.model_dump_json(), encoding="utf-8")
    ratings = tmp_path / "ratings.json"
    ratings.write_text(make_ratings(manifest).model_dump_json(), encoding="utf-8")
    assert main(["score", *args, "--ratings", str(ratings), "--bootstrap-samples", "1"]) == 2
    assert "bootstrap_samples" in capsys.readouterr().err


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ceo_voice.experiments", "--help"])
    with pytest.raises(SystemExit) as error:
        runpy.run_module("ceo_voice.experiments", run_name="__main__")
    assert error.value.code == 0
