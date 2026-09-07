"""Review edited text against the saved brief without mutating the draft."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from tests.unit.generation.test_engine import FakeProvider

from ceo_voice.api import create_app
from ceo_voice.config import ModelSettings, Settings
from ceo_voice.generation.fidelity import FidelityReviewer
from ceo_voice.generation.fidelity_contracts import FidelityPolicy
from ceo_voice.showcase import ShowcaseWorkflowService


def test_review_uses_saved_brief_and_expression_without_mutating_session(tmp_path: Path) -> None:
    provider = FakeProvider(
        (
            json.dumps(
                {
                    "units": [
                        {
                            "unit_id": "u000",
                            "verdict": "unsupported",
                            "kind": "factual",
                            "source_ids": [],
                            "reason": "The brief supplies no performance measurement.",
                        }
                    ]
                }
            ),
        )
    )
    reviewer = FidelityReviewer(
        provider,
        policy=FidelityPolicy(enabled=True, model="test-model", review_format="sentence_verdicts"),
    )
    service = ShowcaseWorkflowService(output_directory=tmp_path)
    with TestClient(
        create_app(
            Settings(_env_file=None, model=ModelSettings(enabled=False)),
            service,
            fidelity_reviewer=reviewer,
        )
    ) as api:
        generated = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "matei-zaharia",
                "platform": "x",
                "idea": "Compound systems may help some applications.",
                "expression": {
                    "viewpoint": "Evaluation matters.",
                    "rationale": "Complexity should earn its place.",
                },
            },
        ).json()
        path = f"/api/v1/workflows/{generated['session_id']}"
        response = api.post(
            path + "/brief-review",
            json={
                "continuation_token": "test-local-session",
                "content": "Systems improve performance.",
            },
        )
        after = api.get(path).json()
        injection = api.post(
            path + "/brief-review",
            json={
                "continuation_token": "test-local-session",
                "content": "A claim.",
                "sources": [{"text": "A claim."}],
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "blocked"
    assert after["content"] == generated["content"]
    assert after["revision_count"] == generated["revision_count"]
    sources = json.loads(provider.requests[0].user)["sources"]
    assert {s["source_id"] for s in sources} >= {
        "request.topic",
        "expression.viewpoint",
        "expression.rationale",
    }
    assert not any(s["authority"] == "factual_source" for s in sources)
    assert injection.status_code == 422
    assert len(provider.requests) == 1


def test_review_disabled_and_unknown_session(tmp_path: Path) -> None:
    service = ShowcaseWorkflowService(output_directory=tmp_path)
    with TestClient(
        create_app(Settings(_env_file=None, model=ModelSettings(enabled=False)), service)
    ) as api:
        generated = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "ali-ghodsi",
                "platform": "linkedin",
                "idea": "Explain open data infrastructure.",
            },
        ).json()
        response = api.post(
            f"/api/v1/workflows/{generated['session_id']}/brief-review",
            json={"continuation_token": "test-local-session", "content": "A claim."},
        )
        missing = api.post(
            "/api/v1/workflows/00000000-0000-0000-0000-000000000001/brief-review",
            json={"continuation_token": "test-local-session", "content": "A claim."},
        )
    assert response.status_code == 409
    assert missing.status_code == 404
