"""Person/platform isolation, observable evidence, emoji policy and editor intent regressions."""

import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ceo_voice.api import create_app
from ceo_voice.api.schemas import GenerateWorkflowRequest
from ceo_voice.config import ModelSettings, Settings
from ceo_voice.core.exceptions import GenerationError
from ceo_voice.generation import GenerationPolicy, OutputValidator
from ceo_voice.generation.enums import ProviderName, ValidationCode
from ceo_voice.generation.validation import validate_generation_input
from ceo_voice.models.enums import Platform
from ceo_voice.models.expression import ExpressionDirection
from ceo_voice.profiles import CuratedCorpus
from ceo_voice.revoice import ReVoicePolicy
from ceo_voice.revoice.contracts import RegionPlan
from ceo_voice.revoice.validation import ReVoiceValidator
from ceo_voice.services.expression import build_expression_profile, emoji_sequences
from ceo_voice.showcase import ShowcaseWorkflowService
from ceo_voice.showcase.catalog import PROFILES
from ceo_voice.showcase.fixtures import profile_manifest
from ceo_voice.voice.enums import SourceModality
from tests.unit.generation.test_engine import FakeProvider, _generation_input
from tests.unit.revoice.test_engine import revoice_input


def _corpus() -> CuratedCorpus:
    base = profile_manifest(PROFILES[0]).corpus
    sample = base.documents[0]
    entries = (
        (
            Platform.X,
            "I am not excited. We should ask why. 👩🏽‍💻",
            SourceModality.AUTHORED_WRITTEN,
        ),
        (
            Platform.X,
            "I am not excited. We should ask why. 👩🏽‍💻",
            SourceModality.AUTHORED_WRITTEN,
        ),
        (
            Platform.X,
            "Thanks to the team. I wonder what we learned. It may be a risk.",
            SourceModality.AUTHORED_WRITTEN,
        ),
        (Platform.LINKEDIN, "Delighted to share this news! 🚀", SourceModality.AUTHORED_WRITTEN),
        (Platform.X, "I believe everything is perfect! 🎉", SourceModality.SPONTANEOUS_SPOKEN),
        (Platform.X, "An ordinary technical observation.", SourceModality.AUTHORED_WRITTEN),
    )
    return base.model_copy(
        update={
            "documents": tuple(
                sample.model_copy(
                    update={
                        "document": sample.document.model_copy(
                            update={
                                "id": UUID(int=index + 1),
                                "platform": platform,
                                "content": text,
                                "url": None,
                            }
                        ),
                        "source_modality": modality,
                    }
                )
                for index, (platform, text, modality) in enumerate(entries)
            )
        }
    )


def test_profile_is_platform_and_modality_specific_deduplicated_and_span_grounded() -> None:
    corpus = _corpus()
    x = build_expression_profile(corpus, Platform.X)
    linkedin = build_expression_profile(corpus, Platform.LINKEDIN)
    assert x.document_count == 3
    assert x.documents_with_emoji == 1
    assert x.emoji_inventory == ("👩🏽‍💻",)
    assert linkedin.emoji_inventory == ("🚀",)
    assert x.corpus_hash != linkedin.corpus_hash
    assert x.cue_document_counts["enthusiasm"] == 1  # visible cue, NOT a positive emotion label
    assert "not excited" in x.examples[0].text or "not excited" in x.examples[1].text
    assert all("🎉" not in example.text for example in x.examples)
    documents = {item.document.id: item.document for item in corpus.documents}
    for example in x.examples:
        assert documents[example.document_id].content[example.start : example.end] == example.text
    assert build_expression_profile(corpus, Platform.YOUTUBE).document_count == 0


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2026 #100 * © plain text", ()),
        ("👨‍👩‍👧‍👦 👍🏽 🇮🇳 1️⃣", ("👨‍👩‍👧‍👦", "👍🏽", "🇮🇳", "1️⃣")),
        ("❤️ 🚀 ™️", ("❤️", "🚀", "™️")),
    ],
)
def test_emoji_sequences_keep_visual_units(text: str, expected: tuple[str, ...]) -> None:
    assert emoji_sequences(text) == expected


@pytest.mark.parametrize(
    "policy, text, blocked",
    [
        ("none", "Infrastructure needs evaluation 🚀", True),
        ("none", "Infrastructure needs evaluation", False),
        ("one", "Infrastructure needs evaluation 👨‍👩‍👧‍👦", False),
        ("one", "Infrastructure needs evaluation 🚀👍", True),
        ("match_profile", "Infrastructure needs evaluation 🚀", True),
        ("match_profile", "Infrastructure needs evaluation 👩🏽‍💻", False),
    ],
)
def test_emoji_constraints_block_or_allow_observable_outputs(
    policy: str, text: str, blocked: bool
) -> None:
    value = _generation_input()
    direction = ExpressionDirection.model_validate({"emoji_policy": policy})
    profile = build_expression_profile(_corpus(), Platform.X)
    value = value.model_copy(
        update={
            "request": value.request.model_copy(
                update={
                    "expression": direction,
                    "expression_profile": profile,
                }
            )
        }
    )
    result = OutputValidator().validate(
        text,
        value,
        GenerationPolicy(provider=ProviderName.OPENAI, model="test", model_context_tokens=10000),
    )
    assert (
        any(finding.code is ValidationCode.EMOJI_POLICY for finding in result.findings) is blocked
    )


def test_cross_person_profile_and_changed_direction_cannot_cross_sealed_request() -> None:
    value = _generation_input()
    raw = value.request.model_dump()
    raw["expression_profile"] = build_expression_profile(_corpus(), Platform.LINKEDIN)
    with pytest.raises(ValidationError, match="expression profile"):
        type(value.request).model_validate(raw)
    changed = value.model_copy(
        update={
            "request": value.request.model_copy(
                update={
                    "expression": ExpressionDirection(emotion="enthusiastic"),
                }
            )
        }
    )
    with pytest.raises(GenerationError) as error:
        validate_generation_input(changed)
    assert error.value.details["reason"] == "expression_mismatch"


@pytest.mark.parametrize(
    "candidate",
    [
        "Infrastructure may help.\n\nThanks to the team.",
        "Infrastructure may help. 🚀\n\nThanks to the team.",
        "Infrastructure may help.\n\nThanks to the team. ❤️",
    ],
)
def test_revoice_cannot_remove_replace_or_move_editor_emoji(candidate: str) -> None:
    edited = "Infrastructure may help.\n\nThanks to the team. 🚀"
    value = revoice_input(original=edited, edited=edited)
    result = ReVoiceValidator().validate(
        candidate,
        value,
        RegionPlan(editable=(), protected=()),
        ReVoicePolicy(provider=ProviderName.OPENAI, model="test"),
    )
    assert any("emoji" in finding.message for finding in result.findings)


def test_expression_and_note_flow_to_generation_then_latest_edit_governs_revoice(
    tmp_path: Path,
) -> None:
    draft = "Compound systems may help retrieval.\n\nEvaluation still matters."
    edited = "Compound systems may help retrieval.\n\nCareful evaluation still matters."
    provider = FakeProvider((draft, edited))
    service = ShowcaseWorkflowService(output_directory=tmp_path, provider=provider)
    direction = {
        "emotion": "enthusiastic",
        "intensity": "restrained",
        "emoji_policy": "none",
        "viewpoint": "Compound systems may help; they are not universally superior.",
    }
    with TestClient(
        create_app(Settings(_env_file=None, model=ModelSettings(enabled=False)), service)
    ) as api:
        generated = api.post(
            "/api/v1/workflows/generate",
            json={
                "profile_slug": "matei-zaharia",
                "platform": "x",
                "idea": "Compound systems may help retrieval; do not claim universal superiority.",
                "expression": direction,
            },
        )
        assert generated.status_code == 200, generated.text
        result = generated.json()
        assert result["expression"]["viewpoint"] == direction["viewpoint"]
        note = "Keep my new paragraph and the cautious stance."
        restored = api.post(
            f"/api/v1/workflows/{result['session_id']}/revoice",
            json={"content": edited, "editor_note": note},
        )
        assert restored.status_code == 200, restored.text
    assert "never the strength, certainty" in provider.requests[0].system
    assert "[EXPRESSION]" in provider.requests[0].user
    payload = json.loads(provider.requests[-1].user)
    assert payload["editor_note"] == note
    assert payload["edited_draft"] == edited
    assert "latest human edit is authoritative" in payload["expression_preservation"]
    assert "editor_direction" not in payload


@pytest.mark.parametrize(
    "direction",
    [
        {"emotion": "psychological_diagnosis"},
        {"rationale": " "},
        {"viewpoint": "a" * 601},
        {"emoji_policy": "unlimited"},
        {"hidden_belief": "invented"},
    ],
)
def test_expression_boundary_rejects_unknown_or_invalid_controls(direction: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        GenerateWorkflowRequest.model_validate(
            {
                "profile_slug": "ali-ghodsi",
                "platform": "linkedin",
                "idea": "Discuss the role of open source in data infrastructure.",
                "expression": direction,
            }
        )
