"""Timezone-safe clock and timestamp helpers."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return an aware timestamp in UTC."""

    return datetime.now(tz=UTC)


def ensure_utc(value: datetime) -> datetime:
    """Reject naive datetimes and normalize an aware datetime to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone information")
    return value.astimezone(UTC)


def isoformat_utc(value: datetime) -> str:
    """Return a normalized ISO 8601 UTC timestamp."""

    return ensure_utc(value).isoformat()
