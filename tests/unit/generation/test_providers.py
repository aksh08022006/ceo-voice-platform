"""Provider-specific wire translations behind the common adapter contract."""

import asyncio
from uuid import UUID

import pytest
from pydantic import JsonValue, SecretStr

from ceo_voice.core.exceptions import ProviderError
from ceo_voice.generation.contracts import ProviderRequest
from ceo_voice.generation.providers import AnthropicProvider, GeminiProvider, OpenAIProvider


class Transport:
    def __init__(self, response: dict[str, JsonValue]) -> None:
        self.response = response
        self.call: tuple[str, dict[str, str], dict[str, JsonValue]] | None = None

    async def post(
        self, *, url: str, headers: dict[str, str], payload: dict[str, JsonValue]
    ) -> tuple[dict[str, JsonValue], int]:
        self.call = (url, headers, payload)
        return self.response, 7


def request() -> ProviderRequest:
    return ProviderRequest(
        request_id=UUID(int=1),
        system="system",
        user="user",
        model="model",
        maximum_output_tokens=100,
    )


@pytest.mark.parametrize(
    ("provider_type", "response", "endpoint"),
    (
        (
            OpenAIProvider,
            {
                "id": "o",
                "output": [{"content": [{"type": "output_text", "text": "openai"}]}],
                "usage": {"input_tokens": 3, "output_tokens": 2},
            },
            "/responses",
        ),
        (
            AnthropicProvider,
            {
                "id": "a",
                "content": [{"type": "text", "text": "anthropic"}],
                "usage": {"input_tokens": 4, "output_tokens": 3},
            },
            "/messages",
        ),
        (
            GeminiProvider,
            {
                "responseId": "g",
                "candidates": [{"content": {"parts": [{"text": "gemini"}]}}],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 4},
            },
            ":generateContent",
        ),
    ),
)
def test_provider_translation(
    provider_type: type[OpenAIProvider], response: dict[str, JsonValue], endpoint: str
) -> None:
    transport = Transport(response)
    result = asyncio.run(provider_type(transport, SecretStr("secret")).generate(request()))
    assert result.text
    assert transport.call is not None and transport.call[0].endswith(endpoint)
    assert "secret" not in str(transport.call[2])


def test_empty_provider_response_is_rejected() -> None:
    with pytest.raises(ProviderError, match="no text"):
        asyncio.run(OpenAIProvider(Transport({}), SecretStr("secret")).generate(request()))
