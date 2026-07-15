"""Configuration-driven composition for the existing model-provider boundary."""

from ceo_voice.config import ModelSettings
from ceo_voice.core.exceptions import ConfigurationError
from ceo_voice.generation.enums import ProviderName
from ceo_voice.generation.ports import JsonTransport, ModelProvider
from ceo_voice.generation.providers import AnthropicProvider, GeminiProvider, OpenAIProvider


def create_model_provider(settings: ModelSettings, transport: JsonTransport) -> ModelProvider:
    """Create exactly one configured vendor adapter without leaking it into domain code."""

    if not settings.enabled or settings.api_key is None or settings.provider is None:
        raise ConfigurationError("model provider is not completely enabled")
    try:
        provider = ProviderName(settings.provider.lower())
    except ValueError as exc:
        raise ConfigurationError(
            "unsupported model provider",
            details={
                "provider": settings.provider,
                "supported": tuple(item.value for item in ProviderName),
            },
        ) from exc
    base_url = settings.base_url
    if provider is ProviderName.OPENAI:
        return OpenAIProvider(
            transport,
            settings.api_key,
            **({"base_url": base_url} if base_url is not None else {}),
        )
    if provider is ProviderName.ANTHROPIC:
        return AnthropicProvider(
            transport,
            settings.api_key,
            **({"base_url": base_url} if base_url is not None else {}),
        )
    return GeminiProvider(
        transport,
        settings.api_key,
        **({"base_url": base_url} if base_url is not None else {}),
    )
