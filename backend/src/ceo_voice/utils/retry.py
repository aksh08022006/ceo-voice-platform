"""Dependency-free retry helpers for narrow, explicitly retryable operations."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded exponential-backoff policy.

    Attributes:
        max_attempts: Total attempts, including the initial call.
        initial_delay_seconds: Delay before the first retry.
        multiplier: Factor applied to the delay after each failed attempt.
        max_delay_seconds: Upper bound for an individual delay.
    """

    max_attempts: int = 3
    initial_delay_seconds: float = 0.1
    multiplier: float = 2.0
    max_delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.initial_delay_seconds < 0:
            raise ValueError("initial_delay_seconds must be non-negative")
        if self.multiplier < 1:
            raise ValueError("multiplier must be at least one")
        if self.max_delay_seconds < 0:
            raise ValueError("max_delay_seconds must be non-negative")


_DEFAULT_RETRY_POLICY = RetryPolicy()


def retry_call[T](
    operation: Callable[..., T],
    *args: object,
    policy: RetryPolicy = _DEFAULT_RETRY_POLICY,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
    **kwargs: object,
) -> T:
    """Call a synchronous operation using an explicit bounded retry policy."""

    delay = policy.initial_delay_seconds
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation(*args, **kwargs)
        except retry_on:
            if attempt == policy.max_attempts:
                raise
            sleep(min(delay, policy.max_delay_seconds))
            delay *= policy.multiplier
    raise RuntimeError("retry loop completed without returning or raising")


async def retry_call_async[T](
    operation: Callable[..., Awaitable[T]],
    *args: object,
    policy: RetryPolicy = _DEFAULT_RETRY_POLICY,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    **kwargs: object,
) -> T:
    """Call an asynchronous operation using an explicit bounded retry policy."""

    delay = policy.initial_delay_seconds
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await operation(*args, **kwargs)
        except retry_on:
            if attempt == policy.max_attempts:
                raise
            await sleep(min(delay, policy.max_delay_seconds))
            delay *= policy.multiplier
    raise RuntimeError("retry loop completed without returning or raising")
