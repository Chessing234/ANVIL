"""Persistent MCP connection pooling and periodic health checks."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import structlog

from config.settings import MCPSettings, MCPServerDefinition
from integrations.mcp_client import MCPClient, ServerConnection
from integrations.mcp_registry import launch_server_command
from integrations.mcp_types import ConnectionHealth

logger = structlog.get_logger(__name__)


@dataclass
class _PooledConnection:
    connection: ServerConnection
    in_use: bool = False


class ConnectionManager:
    """Pool up to ``max_connections_per_server`` MCP sessions per logical server."""

    def __init__(self, client: MCPClient, settings: MCPSettings) -> None:
        self._client = client
        self._settings = settings
        self._servers: dict[str, MCPServerDefinition] = {}
        self._pools: dict[str, list[_PooledConnection]] = {}
        self._lock = asyncio.Lock()
        self._health_task: asyncio.Task[None] | None = None
        self._shutdown = False
        self._last_health: dict[str, ConnectionHealth] = {}

    def _max_per_server(self) -> int:
        return int(self._settings.max_connections_per_server)

    async def initialize_connections(self) -> None:
        """Load server definitions and optionally pre-warm one idle session each."""

        definitions = self._settings.servers()
        async with self._lock:
            self._servers = {d.name: d for d in definitions}
            self._pools = {d.name: [] for d in definitions}
        for definition in definitions:
            try:
                conn = await self._open_new(definition)
                async with self._lock:
                    self._pools[definition.name].append(_PooledConnection(connection=conn, in_use=False))
            except BaseException as exc:
                logger.warning(
                    "mcp_prewarm_failed",
                    server=definition.name,
                    error=str(exc),
                )
        if self._health_task is None:
            self._health_task = asyncio.create_task(self._health_loop(), name="mcp-connection-health")

    async def _open_new(self, definition: MCPServerDefinition) -> ServerConnection:
        cmd = launch_server_command(definition)
        return await self._client.connect(cmd, definition.env, cwd=definition.cwd, reuse_pool=False)

    async def get_connection(self, server_name: str) -> ServerConnection:
        """Borrow a pooled connection, creating one if capacity allows."""

        if self._shutdown:
            raise RuntimeError("connection manager is shut down")
        definition = self._servers.get(server_name)
        if definition is None:
            raise KeyError(f"unknown MCP server: {server_name}")

        async with self._lock:
            pool = self._pools.setdefault(server_name, [])
            for entry in pool:
                if not entry.in_use:
                    entry.in_use = True
                    return entry.connection
            if len(pool) >= self._max_per_server():
                raise RuntimeError(f"connection pool exhausted for server {server_name}")
            conn = await self._open_new(definition)
            pool.append(_PooledConnection(connection=conn, in_use=True))
            return conn

    async def release_connection(self, server_name: str, connection: ServerConnection) -> None:
        """Mark a pooled connection as idle."""

        async with self._lock:
            pool = self._pools.get(server_name, [])
            for entry in pool:
                if entry.connection is connection:
                    entry.in_use = False
                    break

    async def health_check_all(self) -> dict[str, ConnectionHealth]:
        """Ping every known connection and record latency."""

        if not self._settings.ping_enabled:
            return {}
        results: dict[str, ConnectionHealth] = {}
        async with self._lock:
            snapshot = {name: list(pool) for name, pool in self._pools.items()}
        for server_name, pool in snapshot.items():
            for entry in pool:
                started = time.perf_counter()
                healthy = True
                err: str | None = None
                try:
                    await self._client.ping(entry.connection)
                except BaseException as exc:
                    healthy = False
                    err = str(exc)
                elapsed_ms = (time.perf_counter() - started) * 1000
                results[f"{server_name}:{entry.connection.connection_id}"] = ConnectionHealth(
                    server_name=server_name,
                    healthy=healthy,
                    last_ping_ms=round(elapsed_ms, 3),
                    error=err,
                )
        self._last_health = results
        return results

    async def reconnect(self, server_name: str) -> bool:
        """Force-close all pooled sessions for ``server_name`` and open a fresh one."""

        definition = self._servers.get(server_name)
        if definition is None:
            return False
        async with self._lock:
            old_pool = self._pools.pop(server_name, [])
        pool_keys = {entry.connection.pool_key for entry in old_pool}
        for entry in old_pool:
            await self._client.disconnect(entry.connection)
        for key in pool_keys:
            self._client.reset_circuit(key)
        try:
            fresh = await self._open_new(definition)
        except BaseException as exc:
            logger.error("mcp_reconnect_failed", server=server_name, error=str(exc))
            return False
        async with self._lock:
            self._pools[server_name] = [_PooledConnection(connection=fresh, in_use=False)]
        return True

    async def shutdown_all(self) -> None:
        """Stop health checks and disconnect every pooled session."""

        self._shutdown = True
        async with self._lock:
            pools = list(self._pools.items())
            self._pools.clear()
        for _, pool in pools:
            for entry in pool:
                await self._client.disconnect(entry.connection)
        if self._health_task is not None:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> Any:
        """Convenience helper: borrow, invoke, release."""

        conn = await self.get_connection(server_name)
        try:
            result = await self._client.call_tool(
                conn,
                tool_name,
                arguments,
                timeout_seconds=timeout_seconds or self._settings.tool_call_timeout_seconds,
            )
            return result.data
        finally:
            await self.release_connection(server_name, conn)

    async def _health_loop(self) -> None:
        try:
            while not self._shutdown:
                await asyncio.sleep(self._settings.health_interval_seconds)
                if not self._settings.ping_enabled:
                    continue
                await self.health_check_all()
        except asyncio.CancelledError:
            raise
