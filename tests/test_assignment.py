"""Assignment-scale tests use synthetic fixtures only, never real quality evidence."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import AnyHttpUrl, SecretStr, ValidationError

from ceo_voice.assignment import cli
from ceo_voice.assignment.contracts import (
    AssignmentManifest,
    CaseJudgment,
    GenerationSource,
    HumanReview,
    JudgeBatch,
    JudgePayload,
    ReferencePost,
)
from ceo_voice.assignment.evaluation import (
    AssignmentJudge,
    candidate_sha256,
    evaluate_assignment,
    evidence_sha256,
    prepare_assignment,
    select_references,
    text_sha256,
)
from ceo_voice.config import ModelSettings, Settings
from ceo_voice.core.exceptions import ProviderError
from ceo_voice.generation.contracts import ProviderRequest, ProviderResult, TokenUsage
from ceo_voice.generation.enums import ProviderName

_NOW = datetime(2026, 9, 7, tzinfo=UTC)


class FixtureProvider:
    name = ProviderName.OPENAI

    def __init__(self, mode: str = "valid") -> None:
        self.mode = mode
        self.requests: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        if self.mode == "error":
            raise ProviderError("fixture failure")
        source = json.loads(request.user)["references"][0]["source_id"]
        text = json.dumps(
            {
                "voice_score": 8,
                "reasoning": "Synthetic test rationale.",
                "reference_ids": ["unknown" if self.mode == "citation" else source],
                "limitations": ["Synthetic fixture, not actual evaluation."],
            }
        )
        return ProviderResult(
            text="invalid JSON" if self.mode == "invalid" else text,
            provider=self.name,
            model="fixture-model",
            usage=TokenUsage(input_tokens=40, output_tokens=20),
            latency_ms=1,
        )


def _ready() -> AssignmentManifest:
    initial = prepare_assignment("third-leader")
    references = tuple(
        ReferencePost(
            source_id=f"{profile}-{platform}-{index}",
            profile_id=profile,
            platform=platform,
            independence_group=f"{profile}-{platform}-{index}",
            source_url=AnyHttpUrl(f"https://example.com/{profile}/{platform}/{index}"),
            published_at=_NOW,
            text=f"Synthetic independent fixture post {index} by {profile} on {platform}.",
            complete_original=True,
            provenance_verified=True,
        )
        for profile in initial.profiles
        for platform in ("x", "linkedin")
        for index in range(20)
    )
    cases = tuple(
        case.model_copy(
            update={
                "draft": f"Synthetic candidate for {case.case_id}.",
                "human_review": HumanReview(
                    reviewer="Fixture reviewer",
                    reviewed_at=_NOW,
                    candidate_sha256=candidate_sha256(f"Synthetic candidate for {case.case_id}."),
                    voice_accuracy=4,
                    post_quality=4,
                    naturalness=4,
                    notes="Fixture only.",
                ),
            }
        )
        for case in initial.cases
    )
    return initial.model_copy(
        update={"references": references, "cases": cases, "generation_sources_complete": True}
    )


def _batch(manifest: AssignmentManifest) -> JudgeBatch:
    provider = FixtureProvider()
    judge = AssignmentJudge(provider, model="fixture-model")

    async def run() -> JudgeBatch:
        return JudgeBatch(
            judgments=tuple([await judge.judge(manifest, case) for case in manifest.cases])
        )

    return asyncio.run(run())


def test_prepare_pending_and_exact_categories() -> None:
    manifest = prepare_assignment("third-leader")
    report = evaluate_assignment(manifest)
    assert len(manifest.cases) == 30
    assert all(
        len([case for case in manifest.cases if case.profile_id == profile]) == 10
        for profile in manifest.profiles
    )
    assert report.status == report.manual_gate == "pending"
    assert report.automated_scored_cases == 0
    assert all(not profile.means for profile in report.profiles)
    provider = FixtureProvider()
    result = asyncio.run(
        AssignmentJudge(provider, model="fixture").judge(manifest, manifest.cases[0])
    )
    assert result.status == "pending" and result.payload is None
    assert not provider.requests


def test_valid_manual_gate_and_independent_automated_evidence() -> None:
    manifest = _ready()
    assert evaluate_assignment(manifest).manual_gate == "passed"
    assert evaluate_assignment(manifest).status == "pending"
    batch = _batch(manifest)
    report = evaluate_assignment(manifest, batch)
    assert report.status == "passed"
    assert report.automated_scored_cases == 30
    assert all(
        profile.means == {"voice_accuracy": 4.0, "post_quality": 4.0, "naturalness": 4.0}
        for profile in report.profiles
    )


def test_failing_dimension_cannot_be_hidden_by_other_scores_or_other_profiles() -> None:
    manifest = _ready()
    cases = tuple(
        (
            case.model_copy(
                update={
                    "human_review": case.human_review.model_copy(
                        update={"voice_accuracy": 3, "post_quality": 5, "naturalness": 5}
                    )
                }
            )
            if case.profile_id == "ali-ghodsi" and case.human_review
            else case
        )
        for case in manifest.cases
    )
    report = evaluate_assignment(manifest.model_copy(update={"cases": cases}))
    assert report.manual_gate == report.status == "failed"
    assert report.profiles[0].means["voice_accuracy"] == 3


def test_missing_case_missing_review_and_stale_review_remain_pending() -> None:
    manifest = _ready()
    missing = manifest.model_copy(update={"cases": manifest.cases[:-1]})
    assert evaluate_assignment(missing).manual_gate == "pending"
    changed = manifest.cases[0].model_copy(update={"draft": "Changed content."})
    changed_manifest = manifest.model_copy(update={"cases": (changed, *manifest.cases[1:])})
    assert "different draft" in " ".join(evaluate_assignment(changed_manifest).profiles[0].blockers)
    unreviewed = manifest.cases[0].model_copy(update={"human_review": None})
    assert (
        evaluate_assignment(
            manifest.model_copy(update={"cases": (unreviewed, *manifest.cases[1:])})
        ).manual_gate
        == "pending"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("voice_accuracy", 0),
        ("post_quality", 6),
        ("naturalness", 4.5),
        ("naturalness", "4"),
        ("voice_accuracy", True),
    ],
)
def test_manual_scores_require_exact_integer_scale(field: str, value: object) -> None:
    review = _ready().cases[0].human_review
    assert review is not None
    data = review.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        HumanReview.model_validate(data)


@pytest.mark.parametrize("change", ["source_id", "text", "group"])
def test_generation_reference_leakage_is_blocking(change: str) -> None:
    manifest = _ready()
    reference = manifest.references[0]
    source = GenerationSource(
        source_id=reference.source_id if change == "source_id" else "training-source",
        independence_group=reference.independence_group if change == "group" else "training-group",
        text=(
            "  " + reference.text.upper() + "\n"
            if change == "text"
            else "Different training material."
        ),
    )
    manifest = manifest.model_copy(update={"generation_sources": (source,)})
    assert any(
        "holdout leakage" in item for item in select_references(manifest, manifest.cases[0])[1]
    )


@pytest.mark.parametrize("change", ["text", "independence_group", "source_url"])
def test_duplicate_reference_independence_is_checked(change: str) -> None:
    manifest = _ready()
    duplicate = manifest.references[1].model_copy(
        update={change: getattr(manifest.references[0], change)}
    )
    manifest = manifest.model_copy(
        update={"references": (manifest.references[0], duplicate, *manifest.references[2:])}
    )
    assert any(
        "dependent reference" in item for item in select_references(manifest, manifest.cases[0])[1]
    )


def test_real_complete_platform_references_and_candidate_copying() -> None:
    manifest = _ready()
    reference = manifest.references[0].model_copy(update={"provenance_verified": False})
    sparse = manifest.model_copy(update={"references": (reference, *manifest.references[1:])})
    assert "found 19" in " ".join(select_references(sparse, sparse.cases[0])[1])
    reference = reference.model_copy(
        update={"provenance_verified": True, "complete_original": False}
    )
    sparse = manifest.model_copy(update={"references": (reference, *manifest.references[1:])})
    assert "found 19" in " ".join(select_references(sparse, sparse.cases[0])[1])
    copied = manifest.cases[0].model_copy(update={"draft": manifest.references[0].text})
    assert "duplicates reference" in " ".join(select_references(manifest, copied)[1])
    selected, problems = select_references(manifest, manifest.cases[0])
    assert len(selected) == 20 and not problems
    assert all(item.platform == "x" and item.profile_id == "ali-ghodsi" for item in selected)


@pytest.mark.parametrize("mode", ["error", "invalid", "citation"])
def test_provider_errors_invalid_json_and_fabricated_citations_never_score(mode: str) -> None:
    manifest = _ready()
    provider = FixtureProvider(mode)
    judgment = asyncio.run(
        AssignmentJudge(provider, model="fixture").judge(manifest, manifest.cases[0])
    )
    assert judgment.status == "error" and judgment.payload is None
    assert len(provider.requests) == 1


def test_budget_preserves_whole_posts_and_performs_no_call() -> None:
    manifest = _ready()
    provider = FixtureProvider()
    judgment = asyncio.run(
        AssignmentJudge(provider, model="fixture", maximum_prompt_bytes=1024).judge(
            manifest, manifest.cases[0]
        )
    )
    assert judgment.status == "pending" and "no posts were truncated" in judgment.reason
    assert not provider.requests
    with pytest.raises(ValueError, match="budgets"):
        AssignmentJudge(provider, model="fixture", maximum_output_tokens=1)


def test_model_judgment_binding_and_imported_citation_validation() -> None:
    manifest = _ready()
    batch = _batch(manifest)
    case = manifest.cases[0].model_copy(update={"idea": "New angle."})
    stale_manifest = manifest.model_copy(update={"cases": (case, *manifest.cases[1:])})
    assert "different evidence" in " ".join(evaluate_assignment(stale_manifest, batch).blockers)
    payload = JudgePayload(
        voice_score=8, reasoning="Fixture", reference_ids=("outside",), limitations=()
    )
    invalid = batch.judgments[0].model_copy(update={"payload": payload})
    invalid_batch = batch.model_copy(update={"judgments": (invalid, *batch.judgments[1:])})
    assert "citations are invalid" in " ".join(
        evaluate_assignment(manifest, invalid_batch).blockers
    )
    pending = CaseJudgment(
        case_id=manifest.cases[0].case_id,
        status="pending",
        reason="awaiting model",
        evidence_sha256="hash",
    )
    assert (
        evaluate_assignment(manifest, JudgeBatch(judgments=(pending,))).automated_scored_cases == 0
    )


def test_contract_identity_and_judgment_invariants() -> None:
    manifest = _ready()
    with pytest.raises(ValidationError, match="distinct"):
        prepare_assignment("ali-ghodsi")
    with pytest.raises(ValidationError, match="requires"):
        AssignmentManifest(profiles=("a", "b", "c"))
    data = manifest.model_dump()
    for field in ("cases", "references"):
        modified = dict(data)
        modified[field] = [data[field][0], data[field][0]]
        with pytest.raises(ValidationError, match="duplicate"):
            AssignmentManifest.model_validate(modified)
    for field in ("cases", "references"):
        modified = dict(data)
        modified[field] = [{**data[field][0], "profile_id": "unknown"}]
        with pytest.raises(ValidationError, match="undeclared"):
            AssignmentManifest.model_validate(modified)
    payload = JudgePayload(voice_score=1, reasoning="Fixture", reference_ids=("a",), limitations=())
    with pytest.raises(ValidationError, match="only a scored"):
        CaseJudgment(
            case_id="case",
            status="pending",
            reason="fixture",
            evidence_sha256="hash",
            payload=payload,
        )
    with pytest.raises(ValidationError, match="provenance"):
        CaseJudgment(
            case_id="case",
            status="scored",
            reason="fixture",
            evidence_sha256="hash",
            payload=payload,
        )
    pending = CaseJudgment(
        case_id="case", status="pending", reason="fixture", evidence_sha256="hash"
    )
    with pytest.raises(ValidationError, match="duplicate"):
        JudgeBatch(judgments=(pending, pending))


def test_hashing_distinguishes_exact_review_from_normalized_duplicate() -> None:
    assert text_sha256("\uff21  Word\n") == text_sha256("a word")
    assert candidate_sha256("A word") != candidate_sha256("A  word")
    manifest = _ready()
    references, _ = select_references(manifest, manifest.cases[0])
    assert evidence_sha256(manifest.cases[0], references) != evidence_sha256(
        manifest.cases[0], references[:-1]
    )


def test_cli_prepare_schema_report_and_errors(tmp_path: Path) -> None:
    manifest_path, schema_path, report_path = [
        tmp_path / name for name in ("manifest.json", "schema.json", "report.json")
    ]
    assert (
        cli.main(["prepare", "--third-profile", "third-leader", "--output", str(manifest_path)])
        == 0
    )
    assert cli.main(["schema", "--output", str(schema_path)]) == 0
    assert "HumanReview" in schema_path.read_text()
    assert cli.main(["report", "--manifest", str(manifest_path), "--output", str(report_path)]) == 0
    assert json.loads(report_path.read_text())["status"] == "pending"
    assert (
        cli.main(["report", "--manifest", str(tmp_path / "absent"), "--output", str(report_path)])
        == 2
    )
    manifest = _ready()
    manifest_path.write_text(manifest.model_dump_json())
    batch_path = tmp_path / "judgments.json"
    batch_path.write_text(_batch(manifest).model_dump_json())
    assert (
        cli.main(
            [
                "report",
                "--manifest",
                str(manifest_path),
                "--judgments",
                str(batch_path),
                "--output",
                str(report_path),
            ]
        )
        == 0
    )
    assert json.loads(report_path.read_text())["status"] == "passed"


def test_cli_disabled_model_stays_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(model=ModelSettings()))
    manifest_path, output_path = tmp_path / "manifest.json", tmp_path / "judgments.json"
    manifest_path.write_text(_ready().model_dump_json())
    assert (
        cli.main(
            [
                "judge",
                "--manifest",
                str(manifest_path),
                "--limit",
                "1",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    batch = JudgeBatch.model_validate_json(output_path.read_text())
    assert len(batch.judgments) == 1 and batch.judgments[0].status == "pending"


def test_cli_enabled_provider_is_bounded_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = FixtureProvider()
    settings = Settings(
        model=ModelSettings(
            enabled=True,
            provider="openai",
            generation_model="fixture-model",
            api_key=SecretStr("not-a-key"),
        )
    )
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "create_model_provider", lambda settings, transport: provider)
    result = asyncio.run(cli.run_judge(_ready(), limit=1, model="override-model"))
    assert len(result.judgments) == 1
    assert len(provider.requests) == 1 and provider.requests[0].model == "override-model"
