"""System API tests."""

from __future__ import annotations

from starlette.testclient import TestClient

from tests.conftest import API_KEY_HEADERS


def test_health_public_and_metrics_auth(api_client: TestClient) -> None:
    r = api_client.get("/api/v1/system/health")
    assert r.status_code == 200
    data = r.json()
    assert data["database"] is True
    assert data["coordinator_initialized"] is True

    m = api_client.get("/api/v1/system/metrics", headers=API_KEY_HEADERS)
    assert m.status_code == 200
    body = m.json()
    for key in ("incidents", "lessons", "students", "agents"):
        assert key in body


def test_shutdown_marks_coordinator_down(api_client: TestClient) -> None:
    r = api_client.post("/api/v1/system/shutdown", headers=API_KEY_HEADERS)
    assert r.status_code == 200

    r2 = api_client.get("/api/v1/system/health")
    assert r2.status_code == 503
