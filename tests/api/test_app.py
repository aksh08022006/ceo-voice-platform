"""HTTP integration tests over the complete browser workflow."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ceo_voice.api import create_app
from ceo_voice.config import ApiSettings, ModelSettings, Settings
from ceo_voice.core.exceptions import ConfigurationError
from ceo_voice.showcase import ShowcaseWorkflowService


def client(tmp_path: Path) -> TestClient:
    """Return an isolated browser API with no shared workflow state."""

    return TestClient(
        create_app(
            Settings(_env_file=None, model=ModelSettings(enabled=False)),
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
    assert health.json()["model_enabled"] is False
    assert health.json()["model_provider"] is None
    assert health.json()["mode"] == "showcase"
    assert health.json()["profile_count"] == 3
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
                "idea": "Launch a governed AI feature for production data teams.",
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
    assert first["content_type"] == "post"
    assert first["platform_maximum_characters"] == 3000
    assert first["voice_features"]
    assert first["timeline"][-1]["label"] == "Generated Draft"
    assert revoiced.status_code == 200, revoiced.text
    revoiced_payload = revoiced.json()
    assert revoiced_payload["revoiced_content"] == edited_content
    assert revoiced_payload["revoice_applied"] is False
    assert revoiced_payload["revoice_fallback_used"] is False
    assert revoiced_payload["revoice_attempt_count"] == 1
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["evaluation_score"] > 0
    assert evaluated.json()["dimensions"]
    assert inspected.json()["evaluation_status"] in {"pass", "warning", "fail"}


def test_unknown_workflow_is_a_transport_level_not_found(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        response = api.get("/api/v1/workflows/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 404


def test_profile_analytics_requires_a_published_hvm_bundle(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        response = api.get("/api/v1/profiles/ali-ghodsi/analytics")

    assert response.status_code == 404
    assert response.json()["detail"] == "published profile analytics not found"


def test_x_showcase_has_platform_specific_voice_and_structure_evidence(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        response = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "jensen-huang",
                "platform": "x",
                "idea": "Explain why accelerated computing is becoming infrastructure.",
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["platform"] == "x"
    assert response.json()["platform_maximum_characters"] == 280
    assert len(response.json()["content"]) <= 280


def test_revoice_rejects_an_over_limit_human_edit_with_actionable_details(
    tmp_path: Path,
) -> None:
    with client(tmp_path) as api:
        generated = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "ali-ghodsi",
                "platform": "x",
                "idea": "Announce a mapping interface for regional climate risk.",
            },
        )
        assert generated.status_code == 200, generated.text
        session_id = generated.json()["session_id"]
        over_limit_edit = generated.json()["content"] + "\n\n" + ("x" * 281)
        response = api.post(
            f"/api/v1/workflows/{session_id}/revoice",
            json={"content": over_limit_edit},
        )

    assert response.status_code == 422
    payload = response.json()
    assert "280-character limit" in payload["message"]
    assert payload["details"]["maximum_characters"] == 280
    assert payload["details"]["characters_over"] > 0


def test_generation_contract_keeps_three_primary_inputs_and_optional_structure_control(
    tmp_path: Path,
) -> None:
    with client(tmp_path) as api:
        response = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "matei-zaharia",
                "platform": "x",
                "idea": "Explain why compound AI systems combine models, retrieval, and tools.",
            },
        )
        structure_control = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "matei-zaharia",
                "platform": "x",
                "idea": "Explain why compound AI systems combine models, retrieval, and tools.",
                "virality_influence": 0.1,
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["content_type"] == "post"
    assert payload["virality_influence"] == 0.12
    assert len(payload["content"]) <= 280
    assert structure_control.status_code == 200
    assert structure_control.json()["virality_influence"] == 0.1


def test_repeated_showcase_requests_vary_without_question_templates(tmp_path: Path) -> None:
    request = {
        "profile_slug": "ali-ghodsi",
        "platform": "linkedin",
        "idea": "Launch a governed AI feature for production data teams.",
    }
    with client(tmp_path) as api:
        first = api.post("/api/v1/workflows/generate", json=request)
        second = api.post("/api/v1/workflows/generate", json=request)

    assert first.status_code == second.status_code == 200
    first_content = first.json()["content"]
    second_content = second.json()["content"]
    assert first_content != second_content
    assert not first_content.splitlines()[0].endswith("?")
    assert not first_content.splitlines()[-1].endswith("?")


def test_generation_contract_rejects_missing_or_invalid_product_inputs(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        missing_identity = api.post(
            "/api/v1/workflows/generate",
            json={
                "platform": "linkedin",
                "idea": "Explain why an open-source acquisition benefits customers and builders.",
            },
        )
        short_idea = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "ali-ghodsi",
                "platform": "linkedin",
                "idea": "Too short.",
            },
        )
        identity_only = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "ali-ghodsi",
                "platform": "linkedin",
                "idea": "hello i am ali ghodsi",
            },
        )

    assert missing_identity.status_code == 422
    assert short_idea.status_code == 422
    assert identity_only.status_code == 422
    assert "not only the selected identity" in identity_only.text


def test_published_catalog_requires_enabled_model_access(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        api=ApiSettings(published_profile_catalog=tmp_path / "deployment" / "catalog.json"),
        model=ModelSettings(enabled=False),
    )

    with pytest.raises(ConfigurationError, match="requires model access"):
        create_app(settings)


def test_disabled_showcase_keeps_catalog_visible_but_blocks_generation(tmp_path: Path) -> None:
    with TestClient(
        create_app(
            Settings(
                _env_file=None,
                api=ApiSettings(showcase_enabled=False),
                model=ModelSettings(enabled=False),
            ),
            ShowcaseWorkflowService(output_directory=tmp_path / "artifacts"),
        )
    ) as api:
        profiles = api.get("/api/v1/profiles")
        generated = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "ali-ghodsi",
                "platform": "linkedin",
                "idea": "Explain why clear ownership helps technical teams execute.",
            },
        )

    assert profiles.status_code == 200
    assert generated.status_code == 404


@pytest.mark.parametrize("post_count", [2, 3, 4, 5])
def test_x_thread_shape_is_available_through_browser_api(tmp_path: Path, post_count: int) -> None:
    with client(tmp_path) as api:
        generated = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "matei-zaharia",
                "platform": "x",
                "idea": "Explain how compound AI systems combine models, retrieval, and tools.",
                "content_type": "thread",
                "thread_post_count": post_count,
                "virality_influence": 0,
            },
        )
    assert generated.status_code == 200, generated.text
    payload = generated.json()
    assert payload["content_type"] == "thread"
    assert len(payload["thread"]) == post_count
    assert all(0 < len(post) <= 280 for post in payload["thread"])
    assert payload["virality_influence"] == 0


@pytest.mark.parametrize(
    "controls",
    [
        {"content_type": "thread"},
        {"content_type": "thread", "thread_post_count": 1},
        {"content_type": "thread", "thread_post_count": 6},
        {"content_type": "thread", "thread_post_count": 3, "platform": "linkedin"},
        {"thread_post_count": 3},
        {"virality_influence": 0.26},
        {"minimum_words": 300, "maximum_words": 150},
        {"platform": "youtube"},
    ],
)
def test_format_controls_reject_inconsistent_or_unsupported_output(
    tmp_path: Path, controls: dict[str, object]
) -> None:
    with client(tmp_path) as api:
        response = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "ali-ghodsi",
                "platform": "x",
                "idea": "Explain why open interfaces help technical teams build useful systems.",
                **controls,
            },
        )
    assert response.status_code == 422, response.text


def test_linkedin_example_length_bounds_reach_generation(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        response = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "ali-ghodsi",
                "platform": "linkedin",
                "idea": "Explain why open interfaces help technical teams build useful systems.",
                "minimum_words": 150,
                "maximum_words": 300,
                "virality_influence": 0.25,
            },
        )
    assert response.status_code == 200, response.text
    assert 150 <= len(response.json()["content"].split()) <= 300
    assert response.json()["virality_influence"] == 0.25


def test_thread_revoice_repeats_from_latest_revision_and_rejects_stale_edit(tmp_path: Path) -> None:
    with client(tmp_path) as api:
        generated = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "matei-zaharia",
                "platform": "x",
                "idea": "Explain how compound AI systems combine models, retrieval, and tools.",
                "content_type": "thread",
                "thread_post_count": 3,
            },
        )
        assert generated.status_code == 200, generated.text
        initial = generated.json()
        endpoint = f"/api/v1/workflows/{initial['session_id']}/revoice"
        edited = initial["content"].replace("useful work", "useful and reliable work")
        assert len(edited) > 280
        first = api.post(endpoint, json={"content": edited, "expected_revision": 0})
        assert first.status_code == 200, first.text
        assert first.json()["revision_count"] == 1
        assert "\n---\n".join(first.json()["thread"]) == edited
        second_edit = first.json()["revoiced_content"].replace(
            "A platform shift", "An infrastructure shift"
        )
        second = api.post(endpoint, json={"content": second_edit, "expected_revision": 1})
        assert second.status_code == 200, second.text
        assert second.json()["revision_count"] == 2
        assert second.json()["current_candidate_id"] != first.json()["current_candidate_id"]
        assert "useful and reliable work" in second.json()["revoiced_content"]
        stale = api.post(endpoint, json={"content": edited, "expected_revision": 0})
        assert stale.status_code == 409
        inspected = api.get(f"/api/v1/workflows/{initial['session_id']}")
        assert inspected.json()["revision_count"] == 2
        assert "\n---\n".join(inspected.json()["thread"]) == second_edit
