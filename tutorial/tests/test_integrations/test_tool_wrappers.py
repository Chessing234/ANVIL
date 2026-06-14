"""Tests for typed MCP tool wrappers."""

from __future__ import annotations

import json
import sys

import pytest

from config.settings import MCPSettings
from integrations.connection_manager import ConnectionManager
from integrations.mcp_client import MCPClient
from integrations.tool_wrappers import ForensicsTools, LLMTools, NetworkTools


def _three_servers(tmp_path) -> str:
    return json.dumps(
        [
            {
                "name": "security",
                "command": sys.executable,
                "args": ["-m", "integrations.servers.security_tools_server"],
            },
            {
                "name": "sift",
                "command": sys.executable,
                "args": ["-m", "integrations.servers.sift_server"],
                "env": {"SIFT_ARTIFACT_ROOT": str(tmp_path)},
            },
            {
                "name": "llm",
                "command": sys.executable,
                "args": ["-m", "integrations.servers.llm_server"],
            },
        ],
    )


@pytest.mark.asyncio
async def test_forensics_wrappers(tmp_path) -> None:
    settings = MCPSettings(servers_json=_three_servers(tmp_path), health_interval_seconds=3600.0)
    client = MCPClient(default_timeout_seconds=30.0, ping_enabled=False)
    manager = ConnectionManager(client, settings)
    await manager.initialize_connections()
    dump = tmp_path / "mem.dmp"
    dump.write_bytes(b"\x00" * 1024)
    forensics = ForensicsTools(manager)
    mem = await forensics.analyze_memory(str(dump))
    assert mem.ok is True
    sample = tmp_path / "data.bin"
    sample.write_bytes(b"hello-world")
    hashes = await forensics.compute_hashes(str(sample))
    assert set(hashes.keys()) == {"md5", "sha1", "sha256"}
    strings = await forensics.extract_strings(str(sample))
    assert any("hello" in s for s in strings)
    await manager.shutdown_all()


@pytest.mark.asyncio
async def test_network_and_llm_wrappers(tmp_path) -> None:
    settings = MCPSettings(servers_json=_three_servers(tmp_path), health_interval_seconds=3600.0)
    client = MCPClient(default_timeout_seconds=30.0, ping_enabled=False)
    manager = ConnectionManager(client, settings)
    await manager.initialize_connections()
    net = NetworkTools(manager)
    dns = await net.dns_lookup("localhost")
    assert dns.domain == "localhost"
    llm = LLMTools(manager)
    text = await llm.generate_text("Explain DNS in one sentence.")
    assert len(text) > 0
    threat = await llm.classify_threat("ransomware encrypted files")
    assert threat.label in {"benign", "suspicious", "malicious", "unknown"}
    await manager.shutdown_all()
