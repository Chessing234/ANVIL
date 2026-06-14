"""Tests for ``ConnectionManager``."""

from __future__ import annotations

import json
import sys

import pytest

from config.settings import MCPSettings
from integrations.connection_manager import ConnectionManager
from integrations.mcp_client import MCPClient


def _servers_manifest(tmp_path) -> str:
    return json.dumps(
        [
            {
                "name": "security",
                "command": sys.executable,
                "args": ["-m", "integrations.servers.security_tools_server"],
            },
            {
                "name": "llm",
                "command": sys.executable,
                "args": ["-m", "integrations.servers.llm_server"],
            },
        ],
    )


@pytest.mark.asyncio
async def test_connection_manager_pool_and_health(tmp_path) -> None:
    """Pool borrows, releases, and responds to health checks."""

    settings = MCPSettings(
        servers_json=_servers_manifest(tmp_path),
        max_connections_per_server=2,
        health_interval_seconds=3600.0,
        ping_enabled=False,
    )
    client = MCPClient(default_timeout_seconds=30.0, ping_interval_seconds=300.0, ping_enabled=False)
    manager = ConnectionManager(client, settings)
    await manager.initialize_connections()
    sample = tmp_path / "x.bin"
    sample.write_bytes(b"abc")
    data = await manager.call_tool("security", "hash_file", {"file_path": str(sample)})
    assert data["ok"] is True
    conn = await manager.get_connection("security")
    await manager.release_connection("security", conn)
    health = await manager.health_check_all()
    assert health == {}
    await manager.shutdown_all()


@pytest.mark.asyncio
async def test_connection_manager_llm_complete(tmp_path) -> None:
    settings = MCPSettings(
        servers_json=_servers_manifest(tmp_path),
        health_interval_seconds=3600.0,
    )
    client = MCPClient(default_timeout_seconds=20.0, ping_enabled=False)
    manager = ConnectionManager(client, settings)
    await manager.initialize_connections()
    data = await manager.call_tool("llm", "complete", {"prompt": "ping"})
    assert "text" in data
    await manager.shutdown_all()
