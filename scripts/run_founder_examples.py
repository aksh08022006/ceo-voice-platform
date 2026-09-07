"""Bounded real-model acceptance run; preserve raw results privately and never retry silently."""

import json, os, subprocess, sys, time
from pathlib import Path
from datetime import datetime, timezone
import argparse

parser = argparse.ArgumentParser(
    description="Run six real-provider founder examples; no automatic HTTP retries. Requires the existing Vercel CLI login."
)
parser.add_argument("--deployment", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
ROOT = args.output.resolve()
# Set privacy before any continuation-bearing file is created; never overwrite a run.
os.umask(0o077)
if ROOT.exists() and any(ROOT.iterdir()):
    parser.error("Output directory must be empty; choose a new directory to retain previous runs.")
ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
ROOT.chmod(0o700)
DEPLOY = args.deployment
ALI = "Databricks just acquired Tabular, the company behind Apache Iceberg. The angle is that this validates the open-source approach to data infrastructure. The best technology wins when it is open, and this acquisition brings together the teams behind Spark and Iceberg under one roof."
MATEI = "The AI industry is converging on compound AI systems rather than monolithic models. The angle is that the next wave of AI progress will come from how you orchestrate multiple models, retrieval, and tools together, not from making a single model bigger. This is what Databricks has been building toward with Mosaic and their ML platform."


def call(name, path, body):
    req = ROOT / f"{name}.request.json"
    out = ROOT / f"{name}.response.json"
    req.write_text(json.dumps(body))
    req.chmod(0o600)
    started = time.monotonic()
    with (ROOT / f"{name}.stderr.log").open("w") as err:
        p = subprocess.run(
            [
                "npx",
                "--yes",
                "vercel@59.11.7",
                "curl",
                path,
                "--deployment",
                DEPLOY,
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
                f"@{req}",
                "--output",
                str(out),
                "--write-out",
                "%{http_code}",
            ],
            capture_output=False,
            stdout=subprocess.PIPE,
            stderr=err,
            text=True,
        )
    if out.exists():
        out.chmod(0o600)
    meta = {
        "name": name,
        "deployment": DEPLOY,
        "http_status": p.stdout.strip(),
        "returncode": p.returncode,
        "elapsed_s": round(time.monotonic() - started, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        data = json.loads(out.read_text())
    except (ValueError, FileNotFoundError):
        data = {}
    if "content" in data:
        text = data.get("revoiced_content") or data["content"]
        meta.update(
            content=text,
            word_count=len(text.split()),
            posts=[len(x) for x in data.get("thread", [])],
            revision=data.get("revision_count"),
            revoice_applied=data.get("revoice_applied"),
            fallback=data.get("revoice_fallback_used"),
            expression=data.get("expression"),
            expression_profile=data.get("expression_profile"),
            report=data.get("report"),
        )
    else:
        meta["error"] = data
    (ROOT / f"{name}.result.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(
        json.dumps(
            {k: v for k, v in meta.items() if k not in ("expression_profile", "content", "report")},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return data


ali = call(
    "01-pdf-ali",
    "/api/v1/workflows/generate",
    {
        "profile_slug": "ali-ghodsi",
        "platform": "linkedin",
        "idea": ALI,
        "minimum_words": 150,
        "maximum_words": 300,
    },
)
matei = call(
    "02-pdf-matei",
    "/api/v1/workflows/generate",
    {
        "profile_slug": "matei-zaharia",
        "platform": "x",
        "idea": MATEI,
        "content_type": "thread",
        "thread_post_count": 3,
    },
)
if "content" in ali:
    parts = ali["content"].split("\n\n")
    # Explicit synthetic editor-supplied story for the workflow test, not a verified biographical fact.
    hook = "When I met the Tabular founders, we talked about keeping data infrastructure open. That conversation is the starting point I want to share."
    # With only three paragraphs there is one middle paragraph, so reversing it is
    # a no-op. Move the two body paragraphs instead and record whether a move occurred.
    body = parts[1:]
    reordered = [*reversed(body[:-1]), body[-1]] if len(body) > 2 else list(reversed(body))
    moved = len(body) > 1 and reordered != body
    edited = "\n\n".join([hook, *reordered]) if body else hook + "\n\n" + ali["content"]
    (ROOT / "03-structural-edit.json").write_text(
        json.dumps({"original_paragraphs": len(parts), "body_order_changed": moved})
    )
    revised = call(
        "03-pdf-editor-loop",
        f"/api/v1/workflows/{ali['session_id']}/revoice",
        {
            "content": edited,
            "expected_revision": 0,
            "continuation_token": ali.get("continuation_token"),
            "editor_note": "Re-voice this. Keep my structural changes, refine for Ali\u2019s voice.",
        },
    )
    if "content" in revised:
        accepted = revised.get("revoiced_content") or edited
        second = accepted.replace(hook, hook + " I want to keep that focus.").rstrip() + " 🙏"
        call(
            "04-second-editor-loop",
            f"/api/v1/workflows/{ali['session_id']}/revoice",
            {
                "content": second,
                "expected_revision": 1,
                "continuation_token": revised.get("continuation_token"),
                "editor_note": "Keep the revised opening, paragraph order, cautious meaning and my final emoji. Only refine permitted wording.",
            },
        )
brief = "Discuss compound AI systems. Combining models, retrieval and tools may help some applications; this is not a universal improvement. No measurements, customer claims or personal experiences are supplied."
for name, emotion in [("05-emotion-curious", "curious"), ("06-emotion-concerned", "concerned")]:
    call(
        name,
        "/api/v1/workflows/generate",
        {
            "profile_slug": "matei-zaharia",
            "platform": "x",
            "idea": brief,
            "expression": {
                "emotion": emotion,
                "intensity": "restrained",
                "emoji_policy": "none",
                "viewpoint": "Compound systems may help some applications, not all.",
                "rationale": "System complexity should earn its place through evaluation.",
            },
        },
    )
