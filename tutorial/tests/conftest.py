"""Pytest configuration and shared fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from config.settings import get_settings
from core.base_agent import GLOBAL_REGISTRY
from core.message_bus import MessageBus

API_KEY_HEADERS = {"X-API-Key": "tutorial-demo-key"}


@pytest.fixture
def api_client(tmp_path, monkeypatch) -> TestClient:
    """HTTP client with app lifespan and isolated databases."""
    monkeypatch.setenv("TUTORIAL_DATABASE__URL", f"sqlite+aiosqlite:///{tmp_path}/api.sqlite")
    monkeypatch.setenv("TUTORIAL_ORCHESTRATION__PERSISTENCE_DB_PATH", str(tmp_path / "orch.db"))
    monkeypatch.setenv("TUTORIAL_ORCHESTRATION__DEFENSE_CHECKPOINT_DB", str(tmp_path / "def.sqlite"))
    monkeypatch.setenv("TUTORIAL_ORCHESTRATION__TEACHING_CHECKPOINT_DB", str(tmp_path / "teach.sqlite"))
    monkeypatch.setenv("TUTORIAL_MCP__REGISTRY_CACHE_PATH", str(tmp_path / "mcp.sqlite"))
    monkeypatch.setenv("TUTORIAL_API__EVIDENCE_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("TUTORIAL_API__WS_POLL_SECONDS", "0.25")
    # Pin auth so the suite is independent of any developer .env (which may carry
    # a rotated TUTORIAL_API__DEMO_API_KEY). Real env vars override .env values.
    monkeypatch.setenv("TUTORIAL_API__DEMO_API_KEY", "tutorial-demo-key")
    get_settings.cache_clear()
    from api.main import create_app

    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()


@pytest.fixture
async def tmp_evidence_dir(tmp_path: Path) -> Path:
    """Temporary directory for evidence-like artifacts."""

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    return evidence


@pytest.fixture
async def isolated_message_bus() -> AsyncIterator[MessageBus]:
    """Provide a fresh message bus without singleton coupling."""

    bus = MessageBus(max_queue_size=100, message_ttl_seconds=5)
    await bus.start()
    try:
        yield bus
    finally:
        await bus.stop()
        await MessageBus.reset_instance()


@pytest.fixture(autouse=True)
async def reset_global_state() -> AsyncIterator[None]:
    """Ensure global singletons do not leak between tests."""

    await GLOBAL_REGISTRY.clear()
    await MessageBus.reset_instance()
    yield
    await GLOBAL_REGISTRY.clear()
    await MessageBus.reset_instance()
