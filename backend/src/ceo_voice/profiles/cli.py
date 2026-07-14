"""Command-line entry point for local corpus-to-profile builds."""

import argparse
import asyncio
import json
import platform
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError

from ceo_voice.config import load_settings
from ceo_voice.core.exceptions import ApplicationError
from ceo_voice.profiles.composition import create_tier1_profile_builder
from ceo_voice.profiles.contracts import ProfileBuildManifest, ProgressEvent
from ceo_voice.profiles.onboarding import (
    CEOOnboardingService,
    OnboardingManifest,
    write_onboarding_report,
)
from ceo_voice.profiles.workspace import JsonProfileWorkspace
from ceo_voice.utils.files import read_text_limited
from ceo_voice.virality import JsonViralityWorkspace, create_virality_builder

_MAX_MANIFEST_BYTES = 50 * 1024 * 1024


class ConsoleProgressSink:
    """Emit one JSON progress record per line for humans and automation."""

    def __init__(self, *, stream: TextIO = sys.stderr) -> None:
        self._stream = stream

    def report(self, event: ProgressEvent) -> None:
        """Write a compact, content-free progress record."""

        print(event.model_dump_json(), file=self._stream, flush=True)


def build_parser() -> argparse.ArgumentParser:
    """Create the stable CLI grammar."""

    parser = argparse.ArgumentParser(
        prog="ceo-voice",
        description="Operate the governed CEO voice profile and release workflows.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Build or resume one corpus profile.")
    build.add_argument("--manifest", type=Path, required=True, help="ProfileBuildManifest JSON.")
    build.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="Local durable workspace for observations, releases, checkpoints, and profiles.",
    )
    build.add_argument(
        "--output",
        type=Path,
        help="Optional path receiving the complete published profile JSON.",
    )
    build.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the final machine-readable profile JSON.",
    )
    onboard = commands.add_parser(
        "onboard", help="Build HVM and VKR releases from one reviewed onboarding manifest."
    )
    onboard.add_argument("--manifest", type=Path, required=True, help="OnboardingManifest JSON.")
    onboard.add_argument(
        "--workspace", type=Path, required=True, help="Durable local release workspace."
    )
    commands.add_parser("doctor", help="Validate runtime configuration and package installation.")
    return parser


async def _run_build(args: argparse.Namespace) -> int:
    manifest_text = read_text_limited(args.manifest, max_bytes=_MAX_MANIFEST_BYTES)
    manifest = ProfileBuildManifest.model_validate_json(manifest_text)
    workspace = JsonProfileWorkspace(args.workspace)
    builder = create_tier1_profile_builder(
        workspace=workspace,
        progress=ConsoleProgressSink(),
    )
    profile = await builder.build(manifest)
    serialized = profile.model_dump_json(indent=2 if args.pretty else None)
    if args.output is not None:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
    summary = {
        "build_id": str(profile.build_id),
        "release_id": str(profile.managed_release.release.id),
        "release_version": profile.managed_release.release.version,
        "release_status": profile.managed_release.status.value,
        "corpus_hash": profile.corpus_hash,
        "corpus_health": profile.corpus_health.status.value,
        "authority": profile.inspection.authority.value,
        "profile_path": str(args.output.expanduser().resolve()) if args.output else None,
    }
    print(json.dumps(summary, separators=(",", ":")))
    return 0


async def _run_onboard(args: argparse.Namespace) -> int:
    """Build the two existing knowledge releases and persist a readiness decision."""

    text = read_text_limited(args.manifest, max_bytes=_MAX_MANIFEST_BYTES)
    manifest = OnboardingManifest.model_validate_json(text)
    workspace_path = args.workspace.expanduser().resolve()
    service = CEOOnboardingService(
        profile_builder=create_tier1_profile_builder(
            workspace=JsonProfileWorkspace(workspace_path),
            progress=ConsoleProgressSink(),
        ),
        virality_builder=create_virality_builder(workspace=JsonViralityWorkspace(workspace_path)),
    )
    report = await service.onboard(manifest)
    report_path = write_onboarding_report(report, workspace_path)
    print(
        json.dumps(
            {**report.model_dump(mode="json"), "report_path": str(report_path)},
            separators=(",", ":"),
        )
    )
    return 0 if report.generation_ready else 3


def _run_doctor() -> int:
    """Check configuration and emit a container-compatible health result."""

    settings = load_settings()
    try:
        package_version = version("ceo-voice-platform")
    except PackageNotFoundError:
        package_version = "source"
    print(
        json.dumps(
            {
                "status": "ok",
                "package": "ceo-voice-platform",
                "version": package_version,
                "python": platform.python_version(),
                "environment": settings.application.environment.value,
                "model_enabled": settings.model.enabled,
            },
            separators=(",", ":"),
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested command and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            return asyncio.run(_run_build(args))
        if args.command == "onboard":
            return asyncio.run(_run_onboard(args))
        if args.command == "doctor":
            return _run_doctor()
    except ValidationError as exc:
        print(
            json.dumps({"code": "invalid_manifest", "error_count": exc.error_count()}),
            file=sys.stderr,
        )
        return 2
    except ApplicationError as exc:
        print(json.dumps(exc.to_dict(), default=str), file=sys.stderr)
        return 1
    parser.error("unsupported command")


if __name__ == "__main__":  # pragma: no cover - exercised through the console entry point
    raise SystemExit(main())
