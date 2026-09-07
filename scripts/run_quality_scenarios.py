"""Bounded real-provider checks beyond the PDF. Retain outputs; no HTTP retries."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

CASES = (
    (
        "historical-disclosure",
        {
            "profile_slug": "ali-ghodsi",
            "platform": "linkedin",
            "minimum_words": 150,
            "maximum_words": 200,
            "idea": "Reflect on the historical February 9, 2026 Databricks disclosure: the company reported surpassing a $5.4 billion revenue run-rate. This is not recognized annual revenue and is not today's result. The angle is that durable engineering value matters behind a business milestone. No evidence of what caused the result is supplied. Do not invent causal explanations, customer benefits, product metrics or personal memories.",
            "expression": {"emotion": "reflective", "emoji_policy": "none"},
        },
    ),
    (
        "attributed-uncertainty",
        {
            "profile_slug": "matei-zaharia",
            "platform": "x",
            "idea": "The research team suggests compound systems may improve one particular benchmark. We have not measured our own system. Attribute the suggestion to the research team and retain may. Do not claim universal gains or imply we ran their experiment.",
            "expression": {"emotion": "curious", "emoji_policy": "none"},
        },
    ),
    (
        "team-credit",
        {
            "profile_slug": "ali-ghodsi",
            "platform": "linkedin",
            "minimum_words": 100,
            "maximum_words": 150,
            "idea": "Our 12-person engineering team completed the documentation for an open-source parser. Community reviewers reported unclear examples; the team rewrote those examples and added a getting-started guide. The release is planned for next week. Thank the engineers and community reviewers. We have no performance measurements or adoption figures. Do not invent names or say the release already happened.",
            "expression": {"emotion": "grateful", "warmth": "warm", "emoji_policy": "one"},
        },
    ),
    (
        "reply-disagreement",
        {
            "profile_slug": "matei-zaharia",
            "platform": "x",
            "content_kind": "comment",
            "idea": "Respectfully disagree with the universal claim. A larger model may help some tasks; the choice should depend on evaluation of the actual task. We have not run a comparison. Do not claim a smaller or compound system is always better.",
            "parent_post": "Bigger models are always better. There is no reason to evaluate smaller systems.",
            "reply_intent": "respectfully_disagree",
            "expression": {"emotion": "neutral", "emoji_policy": "none"},
        },
    ),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    root = args.output.resolve()
    if root.exists() and any(root.iterdir()):
        parser.error("Choose a fresh output directory to preserve prior runs.")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, body in CASES:
        request = root / f"{name}.request.json"
        response = root / f"{name}.response.json"
        request.write_text(json.dumps(body))
        started = time.monotonic()
        result = subprocess.run(
            [
                "npx",
                "--yes",
                "vercel@59.11.7",
                "curl",
                "--scope",
                "aksh08022006s-projects",
                "/api/v1/workflows/generate",
                "--deployment",
                args.deployment,
                "--",
                "--silent",
                "--show-error",
                "--max-time",
                "180",
                "--request",
                "POST",
                "--header",
                "Content-Type: application/json",
                "--data-binary",
                f"@{request}",
                "--output",
                str(response),
                "--write-out",
                "%{http_code}",
            ],
            capture_output=True,
            text=True,
        )
        (root / f"{name}.stderr.log").write_text(result.stderr)
        try:
            data = json.loads(response.read_text())
        except (FileNotFoundError, ValueError):
            data = {}
        summary = {
            "name": name,
            "deployment": args.deployment,
            "request": body,
            "http_status": result.stdout.strip(),
            "returncode": result.returncode,
            "elapsed_s": round(time.monotonic() - started, 2),
            "completed": result.returncode == 0 and result.stdout.strip() == "200" and bool(data.get("content", "").strip()),
            "content": data.get("content"),
            "thread": data.get("thread"),
            "report": data.get("report"),
            "generation_call_count": data.get("generation_call_count"),
            "fidelity_call_count": data.get("fidelity_call_count"),
            "initial_brief_review_status": data.get("initial_brief_review_status"),
            "initial_brief_review_error": data.get("initial_brief_review_error"),
            "initial_brief_review_findings": data.get("initial_brief_review_findings"),
            "error": {key: data[key] for key in ("code", "message", "details") if key in data},
        }
        (root / f"{name}.result.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        print(
            json.dumps(
                {
                    key: value
                    for key, value in summary.items()
                    if key not in {"request", "content", "thread", "report"}
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
