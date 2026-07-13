"""Shared model primitives and validation rules."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, JsonValue, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def validate_non_blank_text(value: str) -> str:
    """Require visible text without changing its voice-significant whitespace."""

    if not value.strip():
        raise ValueError("text must not be blank")
    return value


NonBlankText = Annotated[str, AfterValidator(validate_non_blank_text)]


def normalize_utc_datetime(value: datetime) -> datetime:
    """Reject naive timestamps and normalize aware timestamps to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include timezone information")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(normalize_utc_datetime)]


class ContractModel(BaseModel):
    """Strict, immutable base for data that crosses module boundaries."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
    )


__all__ = ["ContractModel", "JsonValue", "NonBlankText", "NonEmptyStr", "UtcDatetime"]
