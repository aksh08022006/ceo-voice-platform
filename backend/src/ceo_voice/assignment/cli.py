"""Run with python -m ceo_voice.assignment; all scores come from supplied real evidence."""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ValidationError

from ceo_voice.config import load_settings
from ceo_voice.core.exceptions import ApplicationError
from ceo_voice.generation.transport import HttpxJsonTransport
from ceo_voice.services.model_provider import create_model_provider
from ceo_voice.utils.files import read_text_limited

from .contracts import AssignmentManifest, CaseJudgment, JudgeBatch
from .evaluation import (
    AssignmentJudge,
    evaluate_assignment,
    evidence_sha256,
    prepare_assignment,
    select_references,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Engineering assignment evaluation evidence.")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Create thirty pending briefs, without scores.")
    prepare.add_argument("--third-profile", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    schema = commands.add_parser("schema", help="Write the manifest JSON Schema.")
    schema.add_argument("--output", type=Path, required=True)
    for name in ("report", "judge"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        if name == "report":
            command.add_argument("--judgments", type=Path)
        else:
            command.add_argument(
                "--limit",
                type=int,
                choices=range(1, 31),
                default=30,
                help="Maximum cases considered, at most one model call each.",
            )
            command.add_argument(
                "--model", help="Override the configured generation model for judging."
            )
    return parser


async def run_judge(manifest: AssignmentManifest, *, limit: int, model: str | None) -> JudgeBatch:
    settings = load_settings().model
    if not settings.enabled:
        return JudgeBatch(
            judgments=tuple(
                CaseJudgment(
                    case_id=case.case_id,
                    status="pending",
                    reason="model access is disabled",
                    evidence_sha256=evidence_sha256(case, select_references(manifest, case)[0]),
                )
                for case in manifest.cases[:limit]
            )
        )
    transport = HttpxJsonTransport(timeout_seconds=settings.request_timeout_seconds)
    try:
        provider = create_model_provider(settings, transport)
        judge = AssignmentJudge(
            provider,
            model=model or settings.generation_model or "",
            maximum_output_tokens=min(600, settings.maximum_output_tokens),
            # UTF-8 bytes conservatively upper-bound model input tokens; no post truncation.
            maximum_prompt_bytes=min(
                80_000, settings.context_window_tokens - settings.maximum_output_tokens
            ),
        )
        judgments = []
        for case in manifest.cases[:limit]:
            judgments.append(await judge.judge(manifest, case))
        return JudgeBatch(judgments=tuple(judgments))
    finally:
        await transport.aclose()


def _write(path: Path, value: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.model_dump_json(indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            _write(args.output, prepare_assignment(args.third_profile))
        elif args.command == "schema":
            import json

            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(AssignmentManifest.model_json_schema(), indent=2) + "\n",
                encoding="utf-8",
            )
        else:
            manifest = AssignmentManifest.model_validate_json(
                read_text_limited(args.manifest, max_bytes=20_000_000)
            )
            if args.command == "judge":
                _write(
                    args.output,
                    asyncio.run(run_judge(manifest, limit=args.limit, model=args.model)),
                )
            else:
                batch = (
                    JudgeBatch.model_validate_json(
                        read_text_limited(args.judgments, max_bytes=5_000_000)
                    )
                    if args.judgments
                    else None
                )
                _write(args.output, evaluate_assignment(manifest, batch))
        return 0
    except (ApplicationError, OSError, ValueError, ValidationError):
        print(
            "Assignment evaluation failed: invalid input, unavailable file, or configuration error. No score was fabricated.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
