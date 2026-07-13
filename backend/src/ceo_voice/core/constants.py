"""Stable application-wide constants and enumerations.

Only values shared across module boundaries belong here. Feature-specific values should
remain next to the feature that owns them instead of turning this module into a catch-all.
"""

from enum import StrEnum


class Environment(StrEnum):
    """Supported runtime environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Logging levels accepted by the centralized logging configuration."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(StrEnum):
    """Available log rendering formats."""

    CONSOLE = "console"
    JSON = "json"


APPLICATION_NAME = "CEO Voice Platform"
DEFAULT_SERVICE_NAME = "ceo-voice-platform"
DEFAULT_TEXT_ENCODING = "utf-8"
DEFAULT_LANGUAGE_CODE = "en"
DEFAULT_FILE_READ_LIMIT_BYTES = 10 * 1024 * 1024
REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_LOG_FIELD = "request_id"

# Attributes created by logging.LogRecord. Additional attributes are treated as structured
# context and copied into JSON log output.
LOG_RECORD_RESERVED_ATTRIBUTES = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
        REQUEST_ID_LOG_FIELD,
    }
)
