"""Tests for the deliberately offline public-content collector."""

import csv
import json
from pathlib import Path

import pytest

from ceo_voice.acquisition.enums import AcquisitionMethod
from ceo_voice.collector.authorization import authorize
from ceo_voice.collector.cli import main
from ceo_voice.collector.connectors import LocalImportConnector, _decode_csv_value
from ceo_voice.collector.contracts import ConnectorCapabilities, SourcePolicy
from ceo_voice.collector.service import CollectorService, LocalFileStore

ROOT = Path(__file__).parents[3]
EXAMPLE = ROOT / "data" / "examples" / "public-content-dataset.jsonl"


def _policy(tmp_path: Path, **overrides: object) -> Path:
    """Write an approved synthetic source policy."""

    data: dict[str, object] = {
        "source_id": "synthetic-local",
        "connector_name": "local_import",
        "acquisition_method": "authorized_export",
        "reuse_permission_basis": "synthetic",
        "review_status": "approved",
    }
    data.update(overrides)
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_authorization_fails_closed_for_unknown_or_authenticated_sources(tmp_path: Path) -> None:
    blocked = _policy(tmp_path, reuse_permission_basis="unknown", requires_authentication=True)
    assert main(["inspect-source", "--policy", str(blocked)]) == 3


def test_collect_is_idempotent_and_writes_ignored_canonical_jsonl(tmp_path: Path) -> None:
    policy = SourcePolicy.model_validate_json(_policy(tmp_path).read_text(encoding="utf-8"))
    service = CollectorService(LocalFileStore(tmp_path / "collector"))
    first = service.collect(policy, EXAMPLE)
    second = service.collect(policy, EXAMPLE)
    assert first.admitted == 2
    assert first.output_path is not None
    assert second.admitted == 0
    assert second.unchanged == 2


def test_csv_and_edit_versioning_are_supported(tmp_path: Path) -> None:
    row = json.loads(EXAMPLE.read_text(encoding="utf-8").splitlines()[0])
    csv_path = tmp_path / "input.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(
            {
                key: (
                    json.dumps(value) if isinstance(value, (dict, bool)) or value is None else value
                )
                for key, value in row.items()
            }
        )
    policy = SourcePolicy.model_validate_json(_policy(tmp_path).read_text(encoding="utf-8"))
    service = CollectorService(LocalFileStore(tmp_path / "collector"))
    assert service.collect(policy, csv_path).admitted == 1

    edited = dict(row)
    edited["content"] += " edited"
    import hashlib

    edited["content_sha256"] = hashlib.sha256(edited["content"].encode()).hexdigest()
    edited_path = tmp_path / "edited.jsonl"
    edited_path.write_text(json.dumps(edited), encoding="utf-8")
    result = service.collect(policy, edited_path)
    assert result.edited_versions == 1


def test_authorization_reports_every_unsupported_capability(tmp_path: Path) -> None:
    """A connector may not silently exceed the reviewed source policy."""

    policy = SourcePolicy.model_validate_json(
        _policy(
            tmp_path,
            connector_name="reviewed-connector",
            acquisition_method="manual_capture",
            reuse_permission_basis="public_domain",
            review_status="pending",
            requires_payment=True,
        ).read_text(encoding="utf-8")
    )
    capabilities = ConnectorCapabilities(
        connector_name="different-connector",
        supported_methods=(AcquisitionMethod.AUTHORIZED_EXPORT,),
        requires_network=True,
        requires_authentication=True,
        requires_payment=True,
    )
    receipt = authorize(policy, capabilities)
    assert receipt.decision.value == "block"
    assert len(receipt.reasons) == 7
    assert "terms or explicit permission reference is missing" in receipt.reasons


def test_local_connector_supports_json_shapes_and_rejects_bad_inputs(tmp_path: Path) -> None:
    """Local imports accept only explicit object collections in known formats."""

    connector = LocalImportConnector()
    object_file = tmp_path / "object.json"
    object_file.write_text('{"records": [{"id": 1}]}', encoding="utf-8")
    assert list(connector.read(object_file)) == [{"id": 1}]

    list_file = tmp_path / "list.json"
    list_file.write_text('[{"id": 2}]', encoding="utf-8")
    assert list(connector.read(list_file)) == [{"id": 2}]

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text('{"records": [1]}', encoding="utf-8")
    with pytest.raises(ValueError, match="object list"):
        list(connector.read(invalid_json))

    invalid_jsonl = tmp_path / "invalid.jsonl"
    invalid_jsonl.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="rows must be objects"):
        list(connector.read(invalid_jsonl))

    unsupported = tmp_path / "input.txt"
    unsupported.write_text("content", encoding="utf-8")
    with pytest.raises(ValueError, match="supported input formats"):
        list(connector.read(unsupported))

    assert _decode_csv_value(None) is None
    assert _decode_csv_value("true") is True
    assert _decode_csv_value('["one"]') == ["one"]


def test_collector_reports_invalid_and_duplicate_rows(tmp_path: Path) -> None:
    """One malformed record cannot abort a valid authorized local batch."""

    policy = SourcePolicy.model_validate_json(_policy(tmp_path).read_text(encoding="utf-8"))
    valid = EXAMPLE.read_text(encoding="utf-8").splitlines()[0]
    input_path = tmp_path / "mixed.jsonl"
    input_path.write_text(f"{{}}\n{valid}\n{valid}\n", encoding="utf-8")
    report = CollectorService(LocalFileStore(tmp_path / "collector")).collect(policy, input_path)
    assert report.fetched == 3
    assert report.admitted == 1
    assert report.blocked == 1
    assert report.duplicates == 1


def test_collector_cli_supports_schema_validation_reporting_and_resume(
    tmp_path: Path,
) -> None:
    """Every documented offline command has a directly executable route."""

    schema = tmp_path / "schema.json"
    assert main(["export-schema", "--output", str(schema)]) == 0
    assert "record_id" in schema.read_text(encoding="utf-8")
    assert main(["validate-dataset", "--input", str(EXAMPLE)]) == 0
    assert main(["report", "--input", str(EXAMPLE)]) == 0
    assert main(["doctor"]) == 0

    policy = _policy(tmp_path)
    storage = tmp_path / "collector"
    assert (
        main(
            [
                "resume",
                "--policy",
                str(policy),
                "--input",
                str(EXAMPLE),
                "--storage-root",
                str(storage),
            ]
        )
        == 0
    )
