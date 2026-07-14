"""Deterministic provider adapter for zero-credential local product testing."""

from ceo_voice.generation.contracts import ProviderRequest, ProviderResult, TokenUsage
from ceo_voice.generation.enums import ProviderName


class ShowcaseProvider:
    """Return a planned response while exercising the real model-provider boundary."""

    name = ProviderName.OPENAI

    def __init__(self, response: str) -> None:
        self._response = response

    async def generate(self, request: ProviderRequest) -> ProviderResult:
        """Produce deterministic output with realistic accounting metadata."""

        return ProviderResult(
            text=self._response,
            provider=self.name,
            model=request.model,
            usage=TokenUsage(
                input_tokens=max(1, (len(request.system) + len(request.user)) // 4),
                output_tokens=max(1, len(self._response) // 4),
            ),
            latency_ms=18,
        )
