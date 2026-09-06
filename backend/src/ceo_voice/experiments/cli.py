"""Offline preparation and scoring commands; no model or network dependencies."""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from ceo_voice.core.exceptions import EvaluationError
from ceo_voice.models.base import ContractModel

from .contracts import ExperimentManifest, RatingSubmission
from .preparation import prepare
from .reporting import render_report
from .scoring import score


def _write(path: Path, value: ContractModel) -> None:
    path.write_text(value.model_dump_json(indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Prepare blind ballots or score explicitly submitted human ratings."""

    parser = argparse.ArgumentParser(description="Offline blinded writing experiment harness")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "score"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--output-dir", type=Path, required=True)
        if name == "score":
            command.add_argument("--ratings", type=Path, required=True)
            command.add_argument("--bootstrap-samples", type=int, default=2000)
    args = parser.parse_args(argv)
    try:
        manifest = ExperimentManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
        output_dir: Path = args.output_dir
        if args.command == "prepare":
            ballots, private = prepare(manifest)
            output_dir.mkdir(parents=True, exist_ok=True)
            _write(output_dir / "ballots.json", ballots)
            key_path = output_dir / "assignment-key.private.json"
            # Create the analyst key with restricted permissions before writing sensitive labels.
            key_path.touch(mode=0o600, exist_ok=True)
            key_path.chmod(0o600)
            _write(key_path, private)
            template = RatingSubmission(
                experiment_id=manifest.experiment_id,
                manifest_sha256=manifest.fingerprint(),
                ratings=(),
            )
            _write(output_dir / "ratings-template.json", template)
            (output_dir / "preparation.md").write_text(
                "# Blinded review preparation\n\n"
                f"Prepared {len(ballots.ballots)} baseline-paired ballots. "
                f"Synthetic fixture: {manifest.synthetic}.\n\n"
                "Share ballots.json and independently selected reference writing with reviewers. "
                "Keep the manifest and assignment-key.private.json with the analyst. "
                "Copy ratings-template.json and add real human reviews under ratings: "
                "each entry needs ballot_id, reviewer_id, and choices, a mapping from every "
                "listed dimension to a, b, or tie. Leave unjudgeable ballots unsubmitted. "
                "Do not put arm names or model names in reviewer instructions.\n\n"
                "No generation, judging, or quality measurement has occurred. "
                "Synthetic cases verify plumbing only.\n",
                encoding="utf-8",
            )
        else:
            submission = RatingSubmission.model_validate_json(
                args.ratings.read_text(encoding="utf-8")
            )
            report = score(manifest, submission, bootstrap_samples=args.bootstrap_samples)
            output_dir.mkdir(parents=True, exist_ok=True)
            _write(output_dir / "report.json", report)
            (output_dir / "report.md").write_text(render_report(report), encoding="utf-8")
    except (OSError, UnicodeError):
        print("Experiment files could not be read or written.", file=sys.stderr)
        return 2
    except ValidationError as error:
        # Pydantic's ordinary rendering includes source text; expose only safe validation messages.
        message = error.errors(include_input=False, include_context=False)[0]["msg"]
        print(f"Experiment validation failed: {message}", file=sys.stderr)
        return 2
    except EvaluationError as error:
        print(error.message, file=sys.stderr)
        return 2
    print("Experiment artifacts written.")
    return 0
