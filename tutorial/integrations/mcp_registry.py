"""Central registry of MCP tools with SQLite-backed discovery cache."""

from __future__ import annotations

import asyncio
import json
import shlex
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from pydantic import TypeAdapter

from config.constants import AgentType
from config.settings import MCPServerDefinition
from integrations.mcp_client import MCPClient, ServerConnection
from integrations.mcp_types import RegisteredTool

logger = structlog.get_logger(__name__)

_TOOL_CATEGORY_DEFAULT_AGENTS: dict[str, list[AgentType]] = {
    "forensics": [
        AgentType.DEFENSE_INVESTIGATION,
        AgentType.DEFENSE_EVIDENCE,
        AgentType.DEFENSE_REMEDIATION,
    ],
    "network": [AgentType.DEFENSE_INVESTIGATION, AgentType.DEFENSE_CONTAINMENT],
    "logs": [AgentType.DEFENSE_INVESTIGATION, AgentType.DEFENSE_EVIDENCE],
    "containment": [AgentType.DEFENSE_CONTAINMENT, AgentType.DEFENSE_REMEDIATION],
    "education": [
        AgentType.TEACHING_NARRATIVE,
        AgentType.TEACHING_CURRICULUM,
        AgentType.TEACHING_SANDBOX,
        AgentType.TEACHING_PERSONALIZATION,
    ],
    "llm": [
        AgentType.TEACHING_NARRATIVE,
        AgentType.TEACHING_PERSONALIZATION,
        AgentType.DEFENSE_INVESTIGATION,
    ],
    "sandbox": [AgentType.TEACHING_SANDBOX, AgentType.TEACHING_CURRICULUM],
}

_AGENT_CATEGORY_ALLOWLIST: dict[AgentType, frozenset[str]] = {
    AgentType.DEFENSE_INVESTIGATION: frozenset({"forensics", "network", "logs", "llm"}),
    AgentType.DEFENSE_CONTAINMENT: frozenset({"containment", "network"}),
    AgentType.DEFENSE_EVIDENCE: frozenset({"forensics", "logs"}),
    AgentType.DEFENSE_REMEDIATION: frozenset({"forensics", "containment"}),
    AgentType.TEACHING_NARRATIVE: frozenset({"education", "llm"}),
    AgentType.TEACHING_SANDBOX: frozenset({"education", "sandbox"}),
    AgentType.TEACHING_CURRICULUM: frozenset({"education", "sandbox"}),
    AgentType.TEACHING_PERSONALIZATION: frozenset({"education", "llm"}),
}


def infer_tool_category(server_name: str, tool_name: str) -> str:
    """Heuristic category assignment for catalog filtering."""

    lower = tool_name.lower()
    sn = server_name.lower()
    if sn.startswith("sift") or lower.startswith("sift_"):
        return "forensics"
    if lower.startswith(("complete", "embed", "classify", "summarize", "extract_entities")):
        return "llm"
    if lower in {"isolate_host", "block_ip", "kill_process"}:
        return "containment"
    if "sandbox" in lower or "lesson" in lower:
        return "sandbox"
    if any(k in lower for k in ("curriculum", "csta", "rubric")):
        return "education"
    if any(k in lower for k in ("log", "splunk", "syslog", "apache", "event")):
        return "logs"
    if any(k in lower for k in ("pcap", "dns", "whois", "network")):
        return "network"
    if any(
        k in lower
        for k in (
            "yara",
            "capa",
            "hash",
            "entropy",
            "exif",
            "strings",
            "volatility",
            "memory",
            "file_type",
        )
    ):
        return "forensics"
    return "forensics"


def _default_agents_for_category(category: str) -> list[str]:
    agents = _TOOL_CATEGORY_DEFAULT_AGENTS.get(category, [])
    return [a.value for a in agents]


def _init_sqlite(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mcp_tool_catalog (
                tool_name TEXT PRIMARY KEY,
                server_name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                input_schema TEXT NOT NULL,
                agent_types TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
        conn.commit()


def _persist_catalog(path: Path, rows: list[RegisteredTool]) -> None:
    _init_sqlite(path)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM mcp_tool_catalog")
        for row in rows:
            conn.execute(
                """
                INSERT INTO mcp_tool_catalog
                (tool_name, server_name, category, description, input_schema, agent_types, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.name,
                    row.server_name,
                    row.category,
                    row.description,
                    json.dumps(row.input_schema),
                    json.dumps(row.agent_types),
                    now,
                ),
            )
        conn.commit()


def _load_catalog(path: Path) -> list[RegisteredTool]:
    if not path.exists():
        return []
    rows: list[RegisteredTool] = []
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT tool_name, server_name, category, description, input_schema, agent_types FROM mcp_tool_catalog",
        )
        for r in cur.fetchall():
            rows.append(
                RegisteredTool(
                    name=str(r["tool_name"]),
                    server_name=str(r["server_name"]),
                    category=str(r["category"]),
                    description=str(r["description"]),
                    input_schema=json.loads(str(r["input_schema"])),
                    agent_types=list(json.loads(str(r["agent_types"]))),
                ),
            )
    return rows


class MCPRegistry:
    """Discover MCP tools, cache them locally, and expose lookup APIs."""

    def __init__(self, client: MCPClient, cache_path: Path) -> None:
        self._client = client
        self._cache_path = Path(cache_path)
        self._tools: dict[str, RegisteredTool] = {}
        self._by_server: dict[str, list[str]] = {}
        self._lock = asyncio.Lock()
        self._last_config: dict[str, Any] | None = None
        self._load_cache_from_disk()

    def _load_cache_from_disk(self) -> None:
        self._tools.clear()
        self._by_server.clear()
        for row in _load_catalog(self._cache_path):
            self._tools[row.name] = row
            self._by_server.setdefault(row.server_name, []).append(row.name)
        logger.info("mcp_registry_cache_loaded", tools=len(self._tools), path=str(self._cache_path))

    def get_tool(self, name: str) -> RegisteredTool:
        """Return catalog metadata for ``name``."""

        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"unknown MCP tool: {name}") from exc

    def list_tools(self, category: str | None = None) -> list[RegisteredTool]:
        """List cataloged tools, optionally filtered by category."""

        items = list(self._tools.values())
        if category is None:
            return sorted(items, key=lambda r: r.name)
        return sorted([t for t in items if t.category == category], key=lambda r: r.name)

    def get_tools_for_agent(self, agent_type: AgentType) -> list[RegisteredTool]:
        """Return tools whose categories are relevant to ``agent_type``."""

        allowed = _AGENT_CATEGORY_ALLOWLIST.get(agent_type, frozenset())
        return sorted(
            [t for t in self._tools.values() if t.category in allowed],
            key=lambda r: r.name,
        )

    async def discover_servers(self, config: dict[str, Any]) -> None:
        """Connect to each configured MCP server, list tools, and refresh the catalog."""

        async with self._lock:
            servers_raw = config.get("servers")
            if not isinstance(servers_raw, list):
                raise ValueError("config['servers'] must be a list")
            definitions = TypeAdapter(list[MCPServerDefinition]).validate_python(servers_raw)
            discovered: list[RegisteredTool] = []
            for definition in definitions:
                cmd = launch_server_command(definition)
                conn: ServerConnection | None = None
                try:
                    conn = await self._client.connect(cmd, definition.env, cwd=definition.cwd, reuse_pool=False)
                    tools = await self._client.list_tools(conn)
                    for tool in tools:
                        category = infer_tool_category(definition.name, tool.name)
                        agents = _default_agents_for_category(category)
                        discovered.append(
                            RegisteredTool(
                                name=tool.name,
                                server_name=definition.name,
                                category=category,
                                description=tool.description,
                                input_schema=tool.input_schema,
                                agent_types=agents,
                            ),
                        )
                finally:
                    if conn is not None:
                        await self._client.disconnect(conn)
            self._tools = {row.name: row for row in discovered}
            self._by_server = {}
            for row in discovered:
                self._by_server.setdefault(row.server_name, []).append(row.name)
            await asyncio.to_thread(_persist_catalog, self._cache_path, discovered)
            self._last_config = dict(config)
            logger.info("mcp_registry_discovered", servers=len(definitions), tools=len(discovered))

    async def refresh(self, config: dict[str, Any] | None = None) -> None:
        """Re-run discovery when ``config`` is provided, else use last config or disk cache."""

        if config is not None:
            await self.discover_servers(config)
            return
        if self._last_config is not None:
            await self.discover_servers(self._last_config)
            return
        async with self._lock:
            self._tools.clear()
            self._by_server.clear()
            self._load_cache_from_disk()

    def server_for_tool(self, tool_name: str) -> str:
        """Resolve the configured server name that owns ``tool_name``."""

        return self.get_tool(tool_name).server_name


def launch_server_command(defn: MCPServerDefinition) -> str:
    """Build a shell-safe single string for :class:`MCPClient.connect`."""

    return " ".join(shlex.quote(part) for part in [defn.command, *defn.args])
