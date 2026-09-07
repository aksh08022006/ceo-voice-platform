"""Thin vendor translations; no generation policy lives here."""

from abc import ABC, abstractmethod
from time import monotonic
from typing import Literal, cast

from pydantic import JsonValue, SecretStr

from ceo_voice.core.exceptions import ProviderError
from ceo_voice.generation.contracts import ProviderRequest, ProviderResult, TokenUsage
from ceo_voice.generation.enums import ProviderName
from ceo_voice.generation.ports import JsonTransport


def _integer(value: JsonValue | None) -> int:
    """Read a numeric usage field without accepting container values."""

    return int(value) if isinstance(value, (str, int, float)) else 0


class HttpModelProvider(ABC):
    name: ProviderName

    def __init__(self, transport: JsonTransport, api_key: SecretStr, *, base_url: str) -> None:
        self._transport, self._api_key, self._base_url = transport, api_key, base_url.rstrip("/")

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        started = monotonic()
        try:
            payload, latency = await self._transport.post(
                url=self._url(request), headers=self._headers(), payload=self._payload(request)
            )
            text, request_id, usage = self._parse(payload)
        except ProviderError:
            raise
        except Exception as error:
            raise ProviderError(
                "model provider request failed",
                retryable=True,
                details={"provider": self.name.value},
            ) from error
        return ProviderResult(
            text=text,
            provider=self.name,
            model=request.model,
            provider_request_id=request_id,
            usage=usage,
            latency_ms=max(latency, int((monotonic() - started) * 1000)),
        )

    @abstractmethod
    def _url(self, request: ProviderRequest) -> str: ...
    @abstractmethod
    def _headers(self) -> dict[str, str]: ...
    @abstractmethod
    def _payload(self, request: ProviderRequest) -> dict[str, JsonValue]: ...
    @abstractmethod
    def _parse(self, payload: dict[str, JsonValue]) -> tuple[str, str | None, TokenUsage]: ...


class OpenAIProvider(HttpModelProvider):
    name = ProviderName.OPENAI

    def __init__(
        self,
        transport: JsonTransport,
        api_key: SecretStr,
        *,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        super().__init__(transport, api_key, base_url=base_url)

    def _url(self, request: ProviderRequest) -> str:
        return f"{self._base_url}/responses"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

    def _payload(self, request: ProviderRequest) -> dict[str, JsonValue]:
        return {
            "model": request.model,
            "instructions": request.system,
            "input": request.user,
            "max_output_tokens": request.maximum_output_tokens,
        }

    def _parse(self, payload: dict[str, JsonValue]) -> tuple[str, str | None, TokenUsage]:
        text = payload.get("output_text")
        if not isinstance(text, str):
            output = cast(list[dict[str, JsonValue]], payload.get("output") or [])
            content_groups = (
                cast(list[dict[str, JsonValue]], item.get("content") or []) for item in output
            )
            text = "".join(
                str(block.get("text", ""))
                for content in content_groups
                for block in content
                if block.get("type") == "output_text"
            )
        usage = cast(dict[str, JsonValue], payload.get("usage") or {})
        if not isinstance(text, str) or not text.strip():
            raise ProviderError("OpenAI returned no text")
        return (
            text,
            cast(str | None, payload.get("id")),
            TokenUsage(
                input_tokens=_integer(usage.get("input_tokens")),
                output_tokens=_integer(usage.get("output_tokens")),
            ),
        )


class AnthropicProvider(HttpModelProvider):
    name = ProviderName.ANTHROPIC

    def __init__(
        self,
        transport: JsonTransport,
        api_key: SecretStr,
        *,
        base_url: str = "https://api.anthropic.com/v1",
    ) -> None:
        super().__init__(transport, api_key, base_url=base_url)

    def _url(self, request: ProviderRequest) -> str:
        return f"{self._base_url}/messages"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key.get_secret_value(),
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _payload(self, request: ProviderRequest) -> dict[str, JsonValue]:
        return {
            "model": request.model,
            "system": request.system,
            "messages": [{"role": "user", "content": request.user}],
            "max_tokens": request.maximum_output_tokens,
        }

    def _parse(self, payload: dict[str, JsonValue]) -> tuple[str, str | None, TokenUsage]:
        content = cast(list[dict[str, JsonValue]], payload.get("content") or [])
        text = "".join(str(item.get("text", "")) for item in content if item.get("type") == "text")
        usage = cast(dict[str, JsonValue], payload.get("usage") or {})
        if not text.strip():
            raise ProviderError("Anthropic returned no text")
        return (
            text,
            cast(str | None, payload.get("id")),
            TokenUsage(
                input_tokens=_integer(usage.get("input_tokens")),
                output_tokens=_integer(usage.get("output_tokens")),
            ),
        )


class GeminiProvider(HttpModelProvider):
    name = ProviderName.GEMINI

    def __init__(
        self,
        transport: JsonTransport,
        api_key: SecretStr,
        *,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        thinking_level: Literal["low", "medium", "high"] | None = None,
    ) -> None:
        super().__init__(transport, api_key, base_url=base_url)
        self._thinking_level = thinking_level

    def _url(self, request: ProviderRequest) -> str:
        return f"{self._base_url}/models/{request.model}:generateContent"

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": self._api_key.get_secret_value(),
            "Content-Type": "application/json",
        }

    def _payload(self, request: ProviderRequest) -> dict[str, JsonValue]:
        config: dict[str, JsonValue] = {"maxOutputTokens": request.maximum_output_tokens}
        if request.response_json_schema is not None:
            config["responseMimeType"] = "application/json"
            config["responseJsonSchema"] = request.response_json_schema
        if self._thinking_level is not None:
            config["thinkingConfig"] = {"thinkingLevel": self._thinking_level}
        return {
            "systemInstruction": {"parts": [{"text": request.system}]},
            "contents": [{"role": "user", "parts": [{"text": request.user}]}],
            "generationConfig": config,
        }

    def _parse(self, payload: dict[str, JsonValue]) -> tuple[str, str | None, TokenUsage]:
        candidates = cast(list[dict[str, JsonValue]], payload.get("candidates") or [])
        finish = candidates[0].get("finishReason") if candidates else None
        if finish is not None and finish != "STOP":
            raise ProviderError(
                "Gemini did not return a complete draft", details={"finish_reason": finish}
            )
        content = cast(dict[str, JsonValue], candidates[0].get("content") if candidates else {})
        parts = cast(list[dict[str, JsonValue]], content.get("parts") or [])
        text = "".join(
            str(item.get("text", "")) for item in parts if item.get("thought") is not True
        )
        usage = cast(dict[str, JsonValue], payload.get("usageMetadata") or {})
        if not text.strip():
            raise ProviderError("Gemini returned no text")
        return (
            text,
            cast(str | None, payload.get("responseId")),
            TokenUsage(
                input_tokens=_integer(usage.get("promptTokenCount")),
                output_tokens=_integer(usage.get("candidatesTokenCount"))
                + _integer(usage.get("thoughtsTokenCount")),
            ),
        )
