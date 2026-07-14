"""HTTP integration tests over the complete browser workflow."""

from pathlib import Path

from fastapi.testclient import TestClient

from ceo_voice.api import create_app
from ceo_voice.config import Settings
from ceo_voice.showcase import ShowcaseWorkflowService


def client(tmp_path: Path) -> TestClient:
    """Return an isolated browser API with no shared workflow state."""

    return TestClient(
        create_app(
            Settings(),
            ShowcaseWorkflowService(output_directory=tmp_path / "artifacts"),
        )
    )


def test_health_catalog_and_request_trace_are_available(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        health = api.get("/api/v1/health", headers={"X-Request-ID": "browser-test"})
        profiles = api.get("/api/v1/profiles")
        walkthroughs = api.get("/api/v1/walkthroughs")

    assert health.status_code == 200
    assert health.headers["X-Request-ID"] == "browser-test"
    assert health.json()["showcase_enabled"] is True
    assert {item["slug"] for item in profiles.json()} == {
        "ali-ghodsi",
        "matei-zaharia",
        "jensen-huang",
    }
    assert len(walkthroughs.json()) == 3
    assert all("human_edit" in item for item in walkthroughs.json())


def test_browser_can_generate_edit_revoice_evaluate_and_inspect(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        generated = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "ali-ghodsi",
                "platform": "linkedin",
                "content_type": "announcement",
                "idea": "Launch a governed AI feature for production data teams.",
                "constraints": "Avoid hype.",
            },
        )
        assert generated.status_code == 200, generated.text
        first = generated.json()
        session_id = first["session_id"]
        edited_content = first["content"].replace("connect", "carefully connect")

        revoiced = api.post(
            f"/api/v1/workflows/{session_id}/revoice",
            json={"content": edited_content},
        )
        evaluated = api.post(f"/api/v1/workflows/{session_id}/evaluate")
        inspected = api.get(f"/api/v1/workflows/{session_id}")

    assert first["evidence_count"] > 0
    assert first["voice_features"]
    assert first["timeline"][-1]["label"] == "Generated Draft"
    assert revoiced.status_code == 200, revoiced.text
    assert revoiced.json()["revoiced_content"] == edited_content
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["evaluation_score"] > 0
    assert evaluated.json()["dimensions"]
    assert inspected.json()["evaluation_status"] in {"pass", "warning", "fail"}


def test_unknown_workflow_is_a_transport_level_not_found(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        response = api.get("/api/v1/workflows/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 404


def test_x_showcase_has_platform_specific_voice_and_structure_evidence(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        response = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "jensen-huang",
                "platform": "x",
                "content_type": "post",
                "idea": "Explain why accelerated computing is becoming infrastructure.",
                "constraints": "Connect the platform shift to builders.",
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["platform"] == "x"
    assert len(response.json()["content"]) <= 280
