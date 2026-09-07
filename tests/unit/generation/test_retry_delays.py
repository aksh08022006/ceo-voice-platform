"""Respect provider cooldowns without an unbounded wait or immediate retry burst."""

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from ceo_voice.core.exceptions import ProviderError
from ceo_voice.generation.retry import RetryStrategy
from ceo_voice.generation.transport import _retry_after
from tests.unit.generation.test_engine import FakeProvider, _engine, _generation_input
from tests.unit.generation.test_prompt_coverage import _policy


@pytest.mark.parametrize(
    "header, expected",
    [("12", 12), ("0", 0), ("nan", None), ("-1", None), ("bad", None), ("999999", 86400)],
)
def test_retry_header_is_numeric_finite_and_bounded(header: str, expected: float | None) -> None:
    assert _retry_after(httpx.Response(503, headers={"Retry-After": header})) == expected


def test_retry_date_and_google_delay() -> None:
    response = httpx.Response(
        503, headers={"Retry-After": format_datetime(datetime.now(UTC) + timedelta(seconds=30))}
    )
    delay = _retry_after(response)
    assert delay is not None and 28 <= delay <= 30
    response = httpx.Response(
        429,
        json={
            "error": {
                "details": [
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "4.5s"}
                ]
            }
        },
    )
    assert _retry_after(response) == 4.5
    assert _retry_after(httpx.Response(429, json={"error": "sensitive"})) is None


def test_long_cooldown_is_not_shortened_or_retried() -> None:
    retry = RetryStrategy(_policy())
    error = ProviderError(
        "quota", retryable=True, details={"status_code": 429, "retry_after_seconds": 120}
    )
    assert not retry.provider_allowed(error, 0)
    assert retry.delay_seconds(error, 0) == 120
    assert retry.delay_seconds(ProviderError("quota", details={"status_code": 429}), 1) == 20
    assert retry.delay_seconds(ProviderError("unavailable", details={"status_code": 503}), 1) == 2


def test_generation_waits_before_retry_and_keeps_cost_accounting() -> None:
    provider = FakeProvider(
        (
            ProviderError(
                "rate limited",
                retryable=True,
                details={"status_code": 429, "retry_after_seconds": 12},
            ),
            "Ownership creates speed.\n\nClear decisions compound.",
        )
    )
    with patch("ceo_voice.generation.engine.asyncio.sleep", new_callable=AsyncMock) as sleep:
        draft = asyncio.run(_engine(provider).generate(_generation_input()))
    sleep.assert_awaited_once_with(12)
    assert len(provider.requests) == 2
    assert draft.report.total_latency_ms == 12020
