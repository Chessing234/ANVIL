"""WebSocket API tests."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from config.settings import get_settings


@pytest.fixture
def ws_app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("TUTORIAL_DATABASE__URL", f"sqlite+aiosqlite:///{tmp_path}/ws.sqlite")
    monkeypatch.setenv("TUTORIAL_ORCHESTRATION__PERSISTENCE_DB_PATH", str(tmp_path / "orch.db"))
    monkeypatch.setenv("TUTORIAL_ORCHESTRATION__DEFENSE_CHECKPOINT_DB", str(tmp_path / "def.sqlite"))
    monkeypatch.setenv("TUTORIAL_ORCHESTRATION__TEACHING_CHECKPOINT_DB", str(tmp_path / "teach.sqlite"))
    monkeypatch.setenv("TUTORIAL_MCP__REGISTRY_CACHE_PATH", str(tmp_path / "mcp.sqlite"))
    monkeypatch.setenv("TUTORIAL_API__EVIDENCE_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("TUTORIAL_API__WS_POLL_SECONDS", "0.2")
    # Pin auth so the test is independent of any developer .env key rotation.
    monkeypatch.setenv("TUTORIAL_API__DEMO_API_KEY", "tutorial-demo-key")
    get_settings.cache_clear()
    from api.main import create_app

    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()


def test_websocket_receives_heartbeat(ws_app_client: TestClient) -> None:
    with ws_app_client.websocket_connect("/api/v1/ws/events?api_key=tutorial-demo-key") as ws:
        msg = ws.receive_json()
        assert "event" in msg
        assert "data" in msg


def test_websocket_rejects_bad_key(ws_app_client: TestClient) -> None:
    with pytest.raises(Exception):
        with ws_app_client.websocket_connect("/api/v1/ws/events?api_key=wrong"):
            ws_app_client.app  # pragma: no cover
