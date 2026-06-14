"""Generic async MCP client over stdio with retries, circuit breaker, and health pings."""

from __future__ import annotations

import asyncio
import json
import shlex
import time
import uuid
from collections import defaultdict
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import mcp.types as mtypes
import structlog
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from mcp.shared.exceptions import McpError

from integrations.errors import MCPConnectionError, MCPToolExecutionError
from integrations.mcp_types import ToolDefinition, ToolResult
from shared.utils import CircuitBreaker, CircuitBreakerOpen

logger = structlog.get_logger(__name__)

RECOVERABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    McpError,
    TimeoutError,
    asyncio.TimeoutError,
    ConnectionError,
    OSError,
    EOFError,
    BrokenPipeError,
)


def _tool_result_payload(result: mtypes.CallToolResult) -> dict[str, Any]:
    """Extract JSON payload from ``CallToolResult``."""

    if result.isError:
        parts: list[str] = []
        for block in result.content:
            if isinstance(block, mtypes.TextContent):
                parts.append(block.text)
        raise MCPToolExecutionError("; ".join(parts) if parts else "tool error")

    if result.structuredContent is not None:
        return dict(result.structuredContent)

    for block in result.content:
        if isinstance(block, mtypes.TextContent):
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                return {"text": block.text}
    return {}


@dataclass
class ServerConnection:
    """Live MCP session bound to a spawned stdio server process."""

    connection_id: str
    pool_key: str
    session: ClientSession
    _stack: AsyncExitStack
    session_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _ping_task: asyncio.Task[None] | None = None
    _closed: bool = False

    async def aclose(self) -> None:
        """Terminate stdio transport and child process."""

        if self._closed:
            return
        self._closed = True
        if self._ping_task is not None:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
            self._ping_task = None
        try:
            await self._stack.aclose()
        except RuntimeError as exc:
            logger.warning("mcp_stack_close_runtime_error", error=str(exc))
        except BaseException as exc:
            logger.warning("mcp_stack_close_error", error=str(exc))


class MCPClient:
    """Spawn MCP servers, negotiate the protocol, and invoke tools safely."""

    def __init__(
        self,
        *,
        default_timeout_seconds: float = 60.0,
        max_retries: int = 3,
        ping_interval_seconds: float = 30.0,
        ping_enabled: bool = True,
        max_pool_size: int = 5,
    ) -> None:
        self._default_timeout = default_timeout_seconds
        self._max_retries = max_retries
        self._ping_interval = ping_interval_seconds
        self._ping_enabled = ping_enabled
        self._max_pool_size = max_pool_size
        self._circuit_breakers: dict[str, CircuitBreaker] = defaultdict(CircuitBreaker)
        self._pool_lock = asyncio.Lock()
        self._idle: dict[str, list[ServerConnection]] = defaultdict(list)

    def reset_circuit(self, pool_key: str) -> None:
        """Clear breaker state for ``pool_key`` (used after forced reconnect)."""

        self._circuit_breakers.pop(pool_key, None)

    def _pool_key(self, server_command: str, env_vars: dict[str, str] | None) -> str:
        env_part = json.dumps(env_vars or {}, sort_keys=True)
        return f"{server_command}|{env_part}"

    @staticmethod
    def _parse_command(server_command: str) -> StdioServerParameters:
        parts = shlex.split(server_command, posix=True)
        if not parts:
            raise ValueError("server_command must expand to a non-empty argv")
        command, *args = parts
        return StdioServerParameters(command=command, args=list(args))

    async def _try_reuse_idle(self, pool_key: str) -> ServerConnection | None:
        async with self._pool_lock:
            bucket = self._idle.get(pool_key)
            if not bucket:
                return None
            while bucket:
                candidate = bucket.pop()
                if candidate._closed:
                    continue
                try:
                    await self.ping(candidate)
                except BaseException:
                    await candidate.aclose()
                    continue
                return candidate
        return None

    async def _return_to_pool(self, connection: ServerConnection) -> None:
        async with self._pool_lock:
            bucket = self._idle[connection.pool_key]
            if len(bucket) >= self._max_pool_size:
                await connection.aclose()
                return
            bucket.append(connection)

    def _start_ping(self, connection: ServerConnection) -> None:
        if not self._ping_enabled:
            return

        async def _loop() -> None:
            try:
                while not connection._closed:
                    await asyncio.sleep(self._ping_interval)
                    async with connection.session_lock:
                        await connection.session.send_ping()
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                logger.warning("mcp_ping_failed", connection_id=connection.connection_id, error=str(exc))

        connection._ping_task = asyncio.create_task(_loop(), name=f"mcp-ping-{connection.connection_id}")

    async def connect(
        self,
        server_command: str,
        env_vars: dict[str, str] | None = None,
        *,
        cwd: str | None = None,
        reuse_pool: bool = True,
    ) -> ServerConnection:
        """Spawn an MCP server subprocess and complete the initialize handshake."""

        base = self._parse_command(server_command)
        combined_env = {**get_default_environment(), **(base.env or {}), **(env_vars or {})}
        params = StdioServerParameters(
            command=base.command,
            args=base.args,
            env=combined_env,
            cwd=cwd or base.cwd,
        )
        pool_key = self._pool_key(server_command, env_vars)
        if reuse_pool:
            reused = await self._try_reuse_idle(pool_key)
            if reused is not None:
                return reused

        stack = AsyncExitStack()
        try:
            transport = await stack.enter_async_context(stdio_client(params))
            read_stream, write_stream = transport
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
        except BaseException as exc:
            await stack.aclose()
            raise MCPConnectionError(f"failed to connect MCP server: {server_command}: {exc!s}") from exc

        connection = ServerConnection(
            connection_id=str(uuid.uuid4()),
            pool_key=pool_key,
            session=session,
            _stack=stack,
        )
        self._start_ping(connection)
        logger.info("mcp_connected", pool_key=pool_key, connection_id=connection.connection_id)
        return connection

    async def disconnect(self, connection: ServerConnection) -> None:
        """Close a connection and remove it from any reuse pool."""

        async with self._pool_lock:
            for bucket in self._idle.values():
                if connection in bucket:
                    bucket.remove(connection)
                    break
        await connection.aclose()
        logger.info("mcp_disconnected", connection_id=connection.connection_id)

    async def release_to_pool(self, connection: ServerConnection) -> None:
        """Return a healthy connection to the idle pool for reuse."""

        if connection._closed:
            return
        try:
            await self.ping(connection)
        except BaseException:
            await connection.aclose()
            return
        await self._return_to_pool(connection)

    async def list_tools(self, connection: ServerConnection) -> list[ToolDefinition]:
        """Discover tools exposed by the connected server."""

        async with connection.session_lock:
            listing = await connection.session.list_tools()
        tools: list[ToolDefinition] = []
        for item in listing.tools:
            tools.append(
                ToolDefinition(
                    name=item.name,
                    description=item.description or "",
                    input_schema=dict(item.inputSchema or {}),
                ),
            )
        return tools

    async def ping(self, connection: ServerConnection) -> None:
        """Send MCP ping to validate the session."""

        async with connection.session_lock:
            await asyncio.wait_for(connection.session.send_ping(), timeout=min(10.0, self._default_timeout))

    async def call_tool(
        self,
        connection: ServerConnection,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> ToolResult:
        """Invoke ``tools/call`` with retries and a per-server circuit breaker."""

        timeout = timeout_seconds or self._default_timeout
        breaker = self._circuit_breakers[connection.pool_key]

        async def _transport_call() -> mtypes.CallToolResult:
            async with connection.session_lock:
                return await asyncio.wait_for(
                    connection.session.call_tool(
                        tool_name,
                        arguments,
                        read_timeout_seconds=timedelta(seconds=timeout),
                    ),
                    timeout=timeout + 5.0,
                )

        last_error: BaseException | None = None
        for attempt in range(1, self._max_retries + 1):
            started = time.perf_counter()
            try:
                raw = await breaker.call(_transport_call)
                payload = _tool_result_payload(raw)
                duration_ms = (time.perf_counter() - started) * 1000
                logger.info(
                    "mcp_tool_call",
                    tool=tool_name,
                    connection_id=connection.connection_id,
                    attempt=attempt,
                    duration_ms=round(duration_ms, 3),
                )
                return ToolResult(data=payload)
            except MCPToolExecutionError:
                raise
            except CircuitBreakerOpen as exc:
                raise MCPConnectionError("circuit breaker open for MCP server") from exc
            except RECOVERABLE_EXCEPTIONS as exc:
                last_error = exc
                logger.warning(
                    "mcp_tool_retry",
                    tool=tool_name,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt >= self._max_retries:
                    break
                await asyncio.sleep(0.15 * attempt)
        assert last_error is not None
        raise MCPConnectionError(f"tool call failed after retries: {tool_name}") from last_error

    async def call_tool_protected(
        self,
        connection: ServerConnection,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> ToolResult:
        """Alias used by higher layers; identical to ``call_tool``."""

        return await self.call_tool(connection, tool_name, arguments, timeout_seconds=timeout_seconds)
