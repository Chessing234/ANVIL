"""Tests for ``MCPRegistry``."""

from __future__ import annotations

import json
import sys

import pytest

from config.constants import AgentType
from config.settings import MCPServerDefinition
from integrations.mcp_client import MCPClient
from integrations.mcp_registry import MCPRegistry, launch_server_command


@pytest.mark.asyncio
async def test_registry_discover_and_lookup(tmp_path) -> None:
    """Discover tools from a live server and persist catalog entries."""

    cache = tmp_path / "mcp.sqlite"
    client = MCPClient(ping_enabled=False, default_timeout_seconds=30.0)
    registry = MCPRegistry(client, cache)
    config = {
        "servers": [
            {
                "name": "security",
                "command": sys.executable,
                "args": ["-m", "integrations.servers.security_tools_server"],
            },
        ],
    }
    await registry.discover_servers(config)
    tool = registry.get_tool("hash_file")
    assert tool.server_name == "security"
    assert tool.category == "forensics"
    forensics = registry.list_tools(category="forensics")
    assert any(t.name == "hash_file" for t in forensics)
    agent_tools = registry.get_tools_for_agent(AgentType.DEFENSE_INVESTIGATION)
    assert any(t.name == "hash_file" for t in agent_tools)
    await registry.refresh(config)
    assert registry.get_tool("hash_file").server_name == "security"


@pytest.mark.asyncio
async def test_registry_launch_server_command() -> None:
    """``launch_server_command`` must produce a parseable argv string."""

    defn = MCPServerDefinition(name="demo", command=sys.executable, args=["-m", "integrations.servers.llm_server"])
    cmd = launch_server_command(defn)
    assert sys.executable in cmd
    assert "integrations.servers.llm_server" in cmd
