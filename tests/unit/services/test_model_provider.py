"""Configuration-driven model-provider composition."""

import pytest
from pydantic import JsonValue, SecretStr

from ceo_voice.config import ModelSettings
from ceo_voice.core.exceptions import ConfigurationError
from ceo_voice.generation import AnthropicProvider, GeminiProvider, OpenAIProvider
from ceo_voice.services import create_model_provider


class UnusedTransport:
    async def post(
        self, *, url: str, headers: dict[str, str], payload: dict[str, JsonValue]
    ) -> tuple[dict[str, JsonValue], int]:
        raise AssertionError("composition tests must not make network calls")


@pytest.mark.parametrize(
    ("name", "provider_type"),
    (
        ("openai", OpenAIProvider),
        ("anthropic", AnthropicProvider),
        ("gemini", GeminiProvider),
    ),
)
def test_supported_provider_is_selected(name: str, provider_type: type[object]) -> None:
    settings = ModelSettings(
        enabled=True,
        provider=name,
        generation_model="model",
        api_key=SecretStr("secret"),
    )

    assert isinstance(create_model_provider(settings, UnusedTransport()), provider_type)


def test_disabled_and_unknown_providers_fail_configuration() -> None:
    with pytest.raises(ConfigurationError, match="not completely enabled"):
        create_model_provider(ModelSettings(), UnusedTransport())

    settings = ModelSettings(
        enabled=True,
        provider="unknown",
        generation_model="model",
        api_key=SecretStr("secret"),
    )
    with pytest.raises(ConfigurationError, match="unsupported") as captured:
        create_model_provider(settings, UnusedTransport())
    assert captured.value.details["supported"] == ("openai", "anthropic", "gemini")
