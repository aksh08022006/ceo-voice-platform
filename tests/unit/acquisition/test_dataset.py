"""Public collector handoff contract and content-free validation tests."""

import json
from pathlib import Path

from ceo_voice.acquisition import validate_public_dataset
from ceo_voice.profiles.cli import main

ROOT = Path(__file__).parents[3]
EXAMPLE = ROOT / "data" / "examples" / "public-content-dataset.jsonl"


def test_example_public_dataset_is_valid_and_partitioned() -> None:
    report = validate_public_dataset(EXAMPLE)

    assert report.valid is True
    assert report.record_count == 2
    assert report.leader_count == 2
    assert report.records_with_performance == 2
    assert report.reusable_records == 2
    assert not report.errors


def test_dataset_rejects_hash_mismatch_duplicates_and_empty_files(tmp_path: Path) -> None:
    first = json.loads(EXAMPLE.read_text(encoding="utf-8").splitlines()[0])
    first["content_sha256"] = "0" * 64
    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text(json.dumps(first), encoding="utf-8")
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")

    assert validate_public_dataset(invalid).errors == ("line 1: invalid record (1 error(s))",)
    assert validate_public_dataset(empty).errors == ("dataset: no records",)

    valid_line = EXAMPLE.read_text(encoding="utf-8").splitlines()[0]
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text(f"{valid_line}\n{valid_line}\n", encoding="utf-8")
    report = validate_public_dataset(duplicate)
    assert report.valid is False
    assert "duplicate" in report.errors[0]


def test_validate_dataset_cli_writes_content_free_report(tmp_path: Path) -> None:
    output = tmp_path / "report.json"

    exit_code = main(["validate-dataset", "--input", str(EXAMPLE), "--output", str(output)])

    assert exit_code == 0
    assert output.exists()
    assert '"record_count": 2' in output.read_text(encoding="utf-8")


def test_dataset_schema_cli_exports_the_runtime_contract(tmp_path: Path) -> None:
    output = tmp_path / "public-content.schema.json"

    exit_code = main(["dataset-schema", "--output", str(output)])

    schema = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert schema["title"] == "PublicContentRecord"
    assert "content_sha256" in schema["required"]
