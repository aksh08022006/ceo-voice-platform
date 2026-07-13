"""Shared deterministic fixtures."""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest

from ceo_voice.config import clear_settings_cache


@pytest.fixture(autouse=True)
def isolate_settings_cache() -> Iterator[None]:
    """Prevent environment-sensitive settings from leaking between tests."""

    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def tenant_id() -> UUID:
    """Return a stable tenant identifier."""

    return UUID("10000000-0000-0000-0000-000000000001")


@pytest.fixture
def ceo_id() -> UUID:
    """Return a stable leader identifier."""

    return UUID("20000000-0000-0000-0000-000000000002")


@pytest.fixture
def fixed_time() -> datetime:
    """Return a stable UTC timestamp."""

    return datetime(2026, 7, 13, 9, 30, tzinfo=UTC)
