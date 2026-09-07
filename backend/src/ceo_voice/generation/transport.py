"""Concrete asynchronous JSON transport for model-provider adapters."""

import math
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import cast

import httpx
from pydantic import JsonValue

from ceo_voice.core.exceptions import ProviderError

_RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429})


class HttpxJsonTransport:
    """Send bounded provider requests while translating network failures safely.

    The transport owns connection pooling, timeouts, HTTP status classification, and JSON
    decoding. Provider adapters remain responsible only for vendor request/response shapes.
    Response bodies are never copied into exceptions because they may contain generated content.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
        )

    async def post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, JsonValue],
    ) -> tuple[dict[str, JsonValue], int]:
        """POST JSON and return a validated object plus measured latency."""

        started = monotonic()
        try:
            response = await self._client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "model provider request timed out",
                retryable=True,
                details={"failure": "timeout"},
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                "model provider network request failed",
                retryable=True,
                details={"failure": "network"},
            ) from exc

        latency_ms = max(0, int((monotonic() - started) * 1000))
        if response.is_error:
            status = response.status_code
            retry_after = _retry_after(response)
            raise ProviderError(
                "model provider returned an HTTP error",
                retryable=status in _RETRYABLE_STATUS_CODES or status >= 500,
                details={
                    "status_code": status,
                    **({"retry_after_seconds": retry_after} if retry_after is not None else {}),
                    "provider_request_id": _request_id(response),
                },
            )
        try:
            decoded = response.json()
        except ValueError as exc:
            raise ProviderError(
                "model provider returned invalid JSON",
                details={
                    "status_code": response.status_code,
                    "provider_request_id": _request_id(response),
                },
            ) from exc
        if not isinstance(decoded, dict):
            raise ProviderError(
                "model provider returned a non-object JSON payload",
                details={
                    "status_code": response.status_code,
                    "provider_request_id": _request_id(response),
                },
            )
        return cast(dict[str, JsonValue], decoded), latency_ms

    async def aclose(self) -> None:
        """Close the internally owned connection pool."""

        if self._owns_client:
            await self._client.aclose()


def _request_id(response: httpx.Response) -> str | None:
    """Read common request identifiers without exposing response content."""

    return cast(
        str | None,
        response.headers.get("x-request-id") or response.headers.get("request-id"),
    )


def _retry_after(response: httpx.Response) -> float | None:
    """Read only a bounded delay, never retain the provider's error text."""
    raw = response.headers.get("retry-after")
    if raw:
        try:
            delay = float(raw)
        except ValueError:
            try:
                date = parsedate_to_datetime(raw)
                delay = (date - datetime.now(UTC)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                delay = -1
        if math.isfinite(delay) and delay >= 0:
            return min(delay, 86_400)
    if response.status_code == 429:
        try:
            details = response.json()["error"]["details"]
            for item in details:
                if item.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                    match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(item.get("retryDelay", "")))
                    if match:
                        return min(float(match[1]), 86_400)
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
    return None
