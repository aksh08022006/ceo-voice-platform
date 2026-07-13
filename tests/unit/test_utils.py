"""Tests for conservative cross-cutting utilities."""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from ceo_voice.utils import (
    RetryPolicy,
    dumps_json,
    ensure_path_within,
    ensure_utc,
    is_blank,
    isoformat_utc,
    loads_json,
    normalize_line_endings,
    read_text_limited,
    remove_null_characters,
    retry_call,
    retry_call_async,
    sha256_bytes,
    sha256_file,
    sha256_text,
    truncate_text,
    utc_now,
)


def test_text_helpers_are_conservative() -> None:
    assert normalize_line_endings("one\r\ntwo\rthree") == "one\ntwo\nthree"
    assert remove_null_characters("one\x00two") == "onetwo"
    assert is_blank(" \n") is True
    assert is_blank(" value ") is False
    assert truncate_text("abcdef", 4) == "abc…"
    assert truncate_text("abc", 4) == "abc"
    assert truncate_text("abc", 2, suffix="...") == ".."
    with pytest.raises(ValueError, match="non-negative"):
        truncate_text("abc", -1)


def test_file_helpers_enforce_root_and_size(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("voice", encoding="utf-8")

    assert ensure_path_within(source, tmp_path) == source.resolve()
    assert read_text_limited(source, max_bytes=5) == "voice"
    with pytest.raises(ValueError, match="read limit"):
        read_text_limited(source, max_bytes=4)
    with pytest.raises(ValueError, match="must be positive"):
        read_text_limited(source, max_bytes=0)
    with pytest.raises(ValueError, match="outside the allowed root"):
        ensure_path_within(tmp_path.parent / "outside.txt", tmp_path)


def test_json_helpers_are_deterministic() -> None:
    compact = dumps_json({"z": 1, "a": [True, None]})
    pretty = dumps_json({"z": 1, "a": [True, None]}, pretty=True)

    assert compact == '{"a":[true,null],"z":1}'
    assert pretty.startswith('{\n  "a"')
    assert loads_json(compact) == {"a": [True, None], "z": 1}


def test_time_helpers_require_aware_values() -> None:
    local = datetime(2026, 7, 13, 15, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))

    assert utc_now().tzinfo is UTC
    assert ensure_utc(local) == datetime(2026, 7, 13, 9, 30, tzinfo=UTC)
    assert isoformat_utc(local) == "2026-07-13T09:30:00+00:00"
    with pytest.raises(ValueError, match="timezone information"):
        ensure_utc(datetime(2026, 7, 13))


def test_hash_helpers_are_consistent(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("voice", encoding="utf-8")

    expected = sha256_bytes(b"voice")
    assert len(expected) == 64
    assert sha256_text("voice") == expected
    assert sha256_file(source) == expected


def test_retry_call_retries_selected_failures() -> None:
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("temporary")
        return "done"

    result = retry_call(
        operation,
        policy=RetryPolicy(
            max_attempts=3,
            initial_delay_seconds=0.25,
            multiplier=2,
            max_delay_seconds=0.4,
        ),
        retry_on=(TimeoutError,),
        sleep=delays.append,
    )

    assert result == "done"
    assert delays == [0.25, 0.4]


def test_retry_call_propagates_final_failure() -> None:
    def operation() -> None:
        raise TimeoutError("still unavailable")

    with pytest.raises(TimeoutError, match="still unavailable"):
        retry_call(
            operation,
            policy=RetryPolicy(max_attempts=2, initial_delay_seconds=0),
            retry_on=(TimeoutError,),
            sleep=lambda _: None,
        )


def test_retry_policy_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="at least one"):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError, match="non-negative"):
        RetryPolicy(initial_delay_seconds=-1)
    with pytest.raises(ValueError, match="at least one"):
        RetryPolicy(multiplier=0.5)
    with pytest.raises(ValueError, match="non-negative"):
        RetryPolicy(max_delay_seconds=-1)


def test_async_retry_uses_same_policy() -> None:
    attempts = 0
    delays: list[float] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("temporary")
        return "done"

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    result = asyncio.run(
        retry_call_async(
            operation,
            policy=RetryPolicy(max_attempts=2, initial_delay_seconds=0.1),
            retry_on=(ConnectionError,),
            sleep=fake_sleep,
        )
    )

    assert result == "done"
    assert delays == [0.1]
