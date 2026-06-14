"""Async retry helpers for JSON-RPC and HTTP blockchain backends."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def async_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 4,
    base_delay: float = 0.35,
    max_delay: float = 6.0,
) -> T:
    """Run ``operation`` with exponential backoff and jitter on transient failures."""
    last: BaseException | None = None
    attempts = max(1, max_attempts)
    for attempt in range(attempts):
        try:
            return await operation()
        except (asyncio.TimeoutError, OSError, RuntimeError, ValueError) as exc:
            last = exc
            if attempt == attempts - 1:
                break
            delay = min(max_delay, base_delay * (2**attempt) + random.random() * 0.12)
            await asyncio.sleep(delay)
    assert last is not None
    raise last
