"""Tests for structured logs and execution-context correlation."""

import json
import logging
from collections.abc import Iterator

import pytest

from ceo_voice.core.constants import LogFormat, LogLevel
from ceo_voice.core.logging import (
    JsonFormatter,
    RequestContextFilter,
    configure_logging,
    get_logger,
    get_request_id,
    request_context,
)


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    """Restore process logging state after each unit test."""

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)


def test_request_context_sets_and_resets_identifier() -> None:
    assert get_request_id() is None

    with request_context("request-123") as request_id:
        assert request_id == "request-123"
        assert get_request_id() == "request-123"

    assert get_request_id() is None


def test_request_context_generates_identifier() -> None:
    with request_context() as request_id:
        assert len(request_id) == 32


def test_json_formatter_emits_standard_and_extra_fields() -> None:
    record = logging.LogRecord(
        name="ceo_voice.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="accepted %s",
        args=("document",),
        exc_info=None,
    )
    record.tenant_id = "tenant-1"
    with request_context("request-456"):
        RequestContextFilter().filter(record)
        output = JsonFormatter(service_name="test-service").format(record)

    payload = json.loads(output)
    assert payload["message"] == "accepted document"
    assert payload["request_id"] == "request-456"
    assert payload["service"] == "test-service"
    assert payload["tenant_id"] == "tenant-1"
    assert payload["timestamp"].endswith("+00:00")


def test_configure_logging_outputs_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level=LogLevel.WARNING, output_format=LogFormat.JSON, service_name="test")

    with request_context("request-789"):
        get_logger("ceo_voice.test").warning("careful", extra={"operation": "unit-test"})

    payload = json.loads(capsys.readouterr().out)
    assert payload["level"] == "WARNING"
    assert payload["request_id"] == "request-789"
    assert payload["operation"] == "unit-test"


def test_configure_logging_outputs_console(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", output_format="console")

    get_logger("ceo_voice.test").info("ready")

    output = capsys.readouterr().out
    assert "INFO ceo_voice.test" in output
    assert "[request_id=-] ready" in output
