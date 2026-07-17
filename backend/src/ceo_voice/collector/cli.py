"""CLI for the offline, approval-gated public content collector."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from ceo_voice.acquisition.dataset import PublicContentRecord, validate_public_dataset
from ceo_voice.collector.connectors import LocalImportConnector
from ceo_voice.collector.contracts import SourcePolicy
from ceo_voice.collector.service import CollectorService, LocalFileStore
from ceo_voice.utils.files import read_text_limited


def build_parser() -> argparse.ArgumentParser:
    """Build the supported fail-closed collector command grammar."""

    parser = argparse.ArgumentParser(prog="ceo-collector")
    commands = parser.add_subparsers(dest="command", required=True)
    schema = commands.add_parser("export-schema")
    schema.add_argument("--output", type=Path, required=True)
    inspect = commands.add_parser("inspect-source")
    inspect.add_argument("--policy", type=Path, required=True)
    collect = commands.add_parser("collect")
    collect.add_argument("--policy", type=Path, required=True)
    collect.add_argument("--input", type=Path, required=True)
    collect.add_argument("--storage-root", type=Path, required=True)
    resume = commands.add_parser("resume")
    resume.add_argument("--policy", type=Path, required=True)
    resume.add_argument("--input", type=Path, required=True)
    resume.add_argument("--storage-root", type=Path, required=True)
    validate = commands.add_parser("validate-dataset")
    validate.add_argument("--input", type=Path, required=True)
    report = commands.add_parser("report")
    report.add_argument("--input", type=Path, required=True)
    commands.add_parser("doctor")
    return parser


def _policy(path: Path) -> SourcePolicy:
    """Load a bounded source policy without processing content."""

    return SourcePolicy.model_validate_json(read_text_limited(path, max_bytes=1_000_000))


def main(argv: Sequence[str] | None = None) -> int:
    """Run one collector operation and return a shell status code."""

    args = build_parser().parse_args(argv)
    if args.command == "export-schema":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(PublicContentRecord.model_json_schema(), indent=2), encoding="utf-8"
        )
        return 0
    if args.command == "inspect-source":
        from ceo_voice.collector.authorization import authorize

        receipt = authorize(_policy(args.policy), LocalImportConnector.capabilities)
        print(receipt.model_dump_json())
        return 0 if receipt.decision.value == "admit" else 3
    if args.command in {"collect", "resume"}:
        report = CollectorService(LocalFileStore(args.storage_root)).collect(
            _policy(args.policy), args.input
        )
        print(report.model_dump_json())
        return 0 if report.blocked == 0 else 3
    if args.command in {"validate-dataset", "report"}:
        result = validate_public_dataset(args.input)
        print(result.model_dump_json())
        return 0 if result.valid else 3
    print(json.dumps({"status": "ok", "network_connectors": "disabled"}))
    return 0
