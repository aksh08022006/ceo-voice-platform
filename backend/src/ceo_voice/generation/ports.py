"""Dependency-injected provider boundary."""

from typing import Protocol, runtime_checkable

from pydantic import JsonValue

from ceo_voice.generation.contracts import ProviderRequest, ProviderResult
from ceo_voice.generation.enums import ProviderName


@runtime_checkable
class ModelProvider(Protocol):
    name: ProviderName

    async def generate(self, request: ProviderRequest) -> ProviderResult: ...


@runtime_checkable
class JsonTransport(Protocol):
    async def post(
        self, *, url: str, headers: dict[str, str], payload: dict[str, JsonValue]
    ) -> tuple[dict[str, JsonValue], int]: ...
