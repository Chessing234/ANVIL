"""Tests for ``MCPClient``."""

from __future__ import annotations

import sys

import pytest

from integrations.mcp_client import MCPClient


@pytest.mark.asyncio
async def test_mcp_client_connect_list_call_disconnect(tmp_path) -> None:
    """Exercise stdio MCP against the bundled security tools server."""

    client = MCPClient(default_timeout_seconds=30.0, ping_enabled=False)
    cmd = f"{sys.executable} -m integrations.servers.security_tools_server"
    conn = await client.connect(cmd, reuse_pool=False)
    try:
        tools = await client.list_tools(conn)
        names = {t.name for t in tools}
        assert "hash_file" in names
        sample = tmp_path / "sample.bin"
        sample.write_bytes(b"hello-mcp")
        result = await client.call_tool(conn, "hash_file", {"file_path": str(sample)})
        assert "sha256" in result.data
        assert len(result.data["sha256"]) == 64
    finally:
        await client.disconnect(conn)


@pytest.mark.asyncio
async def test_mcp_client_pool_reuse(tmp_path) -> None:
    """Idle connections should be reused when ``reuse_pool`` is enabled."""

    client = MCPClient(default_timeout_seconds=20.0, ping_enabled=False, max_pool_size=2)
    cmd = f"{sys.executable} -m integrations.servers.security_tools_server"
    first = await client.connect(cmd, reuse_pool=False)
    await client.release_to_pool(first)
    second = await client.connect(cmd, reuse_pool=True)
    assert second.connection_id == first.connection_id
    await client.disconnect(second)
