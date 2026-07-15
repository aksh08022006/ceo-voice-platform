"""HTTP transport behavior at the external model boundary."""

import asyncio

import httpx
import pytest
from pydantic import JsonValue

from ceo_voice.core.exceptions import ProviderError
from ceo_voice.generation.transport import HttpxJsonTransport


def _run(handler: httpx.MockTransport) -> tuple[dict[str, JsonValue], int]:
    client = httpx.AsyncClient(transport=handler)

    async def execute() -> tuple[dict[str, JsonValue], int]:
        transport = HttpxJsonTransport(timeout_seconds=1, client=client)
        try:
            return await transport.post(
                url="https://provider.invalid/v1/generate",
                headers={"Authorization": "Bearer secret"},
                payload={"input": "hello"},
            )
        finally:
            await client.aclose()

    return asyncio.run(execute())


def test_transport_returns_json_without_leaking_headers() -> None:
    payload, latency = _run(
        httpx.MockTransport(lambda _: httpx.Response(200, json={"id": "response-1"}))
    )

    assert payload == {"id": "response-1"}
    assert latency >= 0


@pytest.mark.parametrize(("status", "retryable"), ((400, False), (429, True), (503, True)))
def test_transport_classifies_http_failures(status: int, retryable: bool) -> None:
    def response(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": "sensitive provider message"},
            headers={"x-request-id": "request-1"},
        )

    with pytest.raises(ProviderError) as captured:
        _run(httpx.MockTransport(response))

    assert captured.value.retryable is retryable
    assert captured.value.details == {
        "status_code": status,
        "provider_request_id": "request-1",
    }
    assert "sensitive" not in str(captured.value.to_dict())


@pytest.mark.parametrize(
    "response",
    (
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json=["not", "an", "object"]),
    ),
)
def test_transport_rejects_invalid_success_payloads(response: httpx.Response) -> None:
    with pytest.raises(ProviderError, match=r"invalid JSON|non-object"):
        _run(httpx.MockTransport(lambda _: response))


def test_transport_translates_timeouts() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(ProviderError, match="timed out") as captured:
        _run(httpx.MockTransport(timeout))

    assert captured.value.retryable is True
