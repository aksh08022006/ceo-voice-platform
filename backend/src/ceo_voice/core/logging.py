"""Centralized structured logging with request-context support."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from uuid import uuid4

from ceo_voice.core.constants import (
    DEFAULT_SERVICE_NAME,
    LOG_RECORD_RESERVED_ATTRIBUTES,
    REQUEST_ID_LOG_FIELD,
    LogFormat,
    LogLevel,
)

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestContextFilter(logging.Filter):
    """Attach the active request identifier to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Enrich a record and allow it to be emitted."""

        setattr(record, REQUEST_ID_LOG_FIELD, _request_id.get() or "-")
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as one JSON object per line."""

    def __init__(self, *, service_name: str = DEFAULT_SERVICE_NAME) -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """Convert a log record into stable structured JSON."""

        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": self._service_name,
            "logger": record.name,
            "module": record.module,
            "message": record.getMessage(),
            REQUEST_ID_LOG_FIELD: getattr(record, REQUEST_ID_LOG_FIELD, "-"),
        }

        for key, value in record.__dict__.items():
            if key not in LOG_RECORD_RESERVED_ATTRIBUTES and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=_json_default, ensure_ascii=False, separators=(",", ":"))


def configure_logging(
    *,
    level: LogLevel | str = LogLevel.INFO,
    output_format: LogFormat | str = LogFormat.CONSOLE,
    service_name: str = DEFAULT_SERVICE_NAME,
) -> None:
    """Configure the process-wide root logger.

    The function accepts primitives rather than a settings object to keep the logging layer
    independent from the configuration implementation. Application bootstrap code will inject
    validated values later.
    """

    resolved_level = LogLevel(level)
    resolved_format = LogFormat(output_format)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestContextFilter())
    if resolved_format is LogFormat.JSON:
        handler.setFormatter(JsonFormatter(service_name=service_name))
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt=(
                    "%(asctime)s %(levelname)s %(name)s " "[request_id=%(request_id)s] %(message)s"
                ),
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(resolved_level.value)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger governed by the centralized root configuration."""

    return logging.getLogger(name)


def get_request_id() -> str | None:
    """Return the request identifier active in the current execution context."""

    return _request_id.get()


@contextmanager
def request_context(request_id: str | None = None) -> Iterator[str]:
    """Set and reliably reset a request identifier around a unit of work.

    Context variables isolate concurrent asynchronous tasks, so this mechanism can later be
    used by HTTP middleware, queue workers, and durable workflows without changing log calls.
    """

    resolved_request_id = request_id or uuid4().hex
    token = _request_id.set(resolved_request_id)
    try:
        yield resolved_request_id
    finally:
        _request_id.reset(token)


def _json_default(value: object) -> str:
    """Serialize common structured logging values without failing the log call."""

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, Path):
        return str(value)
    return str(value)
