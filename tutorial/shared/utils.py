"""Async utilities, retry helpers, timing decorators, and resilience primitives."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import inspect
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast

import httpx
import structlog

from config.constants import RETRIES

P = ParamSpec("P")
R = TypeVar("R")

logger = structlog.get_logger(__name__)


def merge_dicts(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-merge two mappings without mutating inputs.

    Args:
        base: Baseline mapping.
        override: Values that should take precedence.

    Returns:
        New dictionary representing the merged structure.
    """

    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], Mapping)
            and isinstance(value, Mapping)
        ):
            result[key] = merge_dicts(
                cast(Mapping[str, Any], result[key]),
                cast(Mapping[str, Any], value),
            )
        else:
            result[key] = value
    return result


def retry(
    max_attempts: int = RETRIES.DEFAULT_MAX_ATTEMPTS,
    backoff: float = RETRIES.DEFAULT_BACKOFF_SECONDS,
    exceptions: tuple[type[BaseException], ...] = (ConnectionError, TimeoutError),
) -> Callable[[Callable[P, R | Awaitable[R]]], Callable[P, R | Awaitable[R]]]:
    """Retry synchronous or asynchronous callables with exponential backoff.

    Args:
        max_attempts: Total attempts including the first try.
        backoff: Multiplicative backoff base in seconds.
        exceptions: Tuple of recoverable exception types.

    Returns:
        Decorator that wraps functions or coroutine functions.
    """

    def decorator(func: Callable[P, R | Awaitable[R]]) -> Callable[P, R | Awaitable[R]]:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                attempt = 0
                delay = backoff
                while True:
                    attempt += 1
                    try:
                        return await cast(Callable[P, Awaitable[R]], func)(*args, **kwargs)
                    except exceptions as exc:  # pragma: no cover - exercised in tests
                        if attempt >= max_attempts:
                            raise
                        logger.warning(
                            "retrying_async_call",
                            function=func.__name__,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            error=str(exc),
                        )
                        try:
                            await asyncio.sleep(delay)
                        except asyncio.CancelledError:
                            raise
                        delay *= backoff

            return cast(Callable[P, R | Awaitable[R]], async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            attempt = 0
            delay = backoff
            while True:
                attempt += 1
                try:
                    return cast(Callable[P, R], func)(*args, **kwargs)
                except exceptions as exc:
                    if attempt >= max_attempts:
                        raise
                    logger.warning(
                        "retrying_sync_call",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        error=str(exc),
                    )
                    time.sleep(delay)
                    delay *= backoff

        return cast(Callable[P, R | Awaitable[R]], sync_wrapper)

    return decorator


def timed(func: Callable[P, R | Awaitable[R]]) -> Callable[P, R | Awaitable[R]]:
    """Log execution duration for sync or async callables.

    Args:
        func: Callable to wrap.

    Returns:
        Wrapped callable emitting structured timing logs.
    """

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.perf_counter()
            try:
                return await cast(Callable[P, Awaitable[R]], func)(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    "function_timed",
                    function=func.__name__,
                    duration_ms=round(duration_ms, 3),
                )

        return cast(Callable[P, R | Awaitable[R]], async_wrapper)

    @functools.wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        try:
            return cast(Callable[P, R], func)(*args, **kwargs)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "function_timed",
                function=func.__name__,
                duration_ms=round(duration_ms, 3),
            )

    return cast(Callable[P, R | Awaitable[R]], sync_wrapper)


@dataclass(slots=True)
class SubprocessResult:
    """Structured result for subprocess execution."""

    returncode: int
    stdout: str
    stderr: str


async def run_subprocess(cmd: list[str], timeout: float = 60.0) -> SubprocessResult:
    """Execute a subprocess safely with cancellation-aware timeout handling.

    Args:
        cmd: Argument vector including executable in index zero.
        timeout: Wall-clock timeout in seconds.

    Returns:
        Aggregated stdout, stderr, and return code.

    Raises:
        asyncio.TimeoutError: If the process exceeds ``timeout``.
        FileNotFoundError: If the executable cannot be resolved.
    """

    if not cmd:
        raise ValueError("cmd must be non-empty")

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        process.kill()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.CancelledError:
            process.kill()
            raise
        except asyncio.TimeoutError:
            process.kill()
        raise
    except asyncio.CancelledError:
        process.kill()
        try:
            await process.wait()
        finally:
            raise

    stdout = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
    stderr = stderr_bytes.decode(errors="replace") if stderr_bytes else ""
    return SubprocessResult(returncode=process.returncode or 0, stdout=stdout, stderr=stderr)


def compute_file_hash(path: str) -> str:
    """Compute SHA-256 for a file on disk in fixed-size chunks.

    Args:
        path: Filesystem path to hash.

    Returns:
        Lowercase hex digest.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """

    digest = hashlib.sha256()
    file_path = Path(path)
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sanitize_filename(name: str) -> str:
    """Reduce a string to a filesystem-friendly filename stem.

    Args:
        name: Raw filename candidate.

    Returns:
        Sanitized filename containing alphanumeric, dash, and underscore.
    """

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return cleaned[:200] if cleaned else "unnamed"


@retry(max_attempts=3, backoff=2.0, exceptions=(httpx.HTTPError, TimeoutError))
async def download_file(url: str, dest: Path, timeout: float = 60.0) -> Path:
    """Download a remote resource to ``dest`` with retries and timeouts.

    Args:
        url: HTTP or HTTPS URL.
        dest: Destination path (parent directories must exist or be creatable).
        timeout: Per-request timeout in seconds.

    Returns:
        Path to the written file.

    Raises:
        httpx.HTTPError: When the remote server returns an error after retries.
    """

    dest.parent.mkdir(parents=True, exist_ok=True)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    timeout_cfg = httpx.Timeout(timeout)
    async with httpx.AsyncClient(limits=limits, timeout=timeout_cfg) as client:
        response = await client.get(url)
        response.raise_for_status()
        dest.write_bytes(response.content)
    return dest


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker refuses traffic."""

    def __init__(self, message: str = "circuit breaker is open") -> None:
        super().__init__(message)


@dataclass
class CircuitBreaker:
    """Fail-fast guard for unreliable external services."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_attempts: int = 1
    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _half_open_left: int = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def call(
        self,
        func: Callable[..., Awaitable[Any]],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Invoke ``func`` while enforcing breaker semantics.

        Args:
            func: Async callable to protect.
            *args: Positional arguments forwarded to ``func``.
            **kwargs: Keyword arguments forwarded to ``func``.

        Returns:
            Result of ``func``.

        Raises:
            CircuitBreakerOpen: When the breaker is open and recovery window elapsed.
        """

        async with self._lock:
            now = time.monotonic()
            if self._opened_at is not None:
                if now - self._opened_at < self.recovery_timeout:
                    raise CircuitBreakerOpen()
                self._half_open_left = self.half_open_attempts
                self._opened_at = None

        try:
            result = await func(*args, **kwargs)
        except BaseException:
            async with self._lock:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._opened_at = time.monotonic()
            raise
        else:
            async with self._lock:
                self._failures = 0
                self._opened_at = None
            return result
