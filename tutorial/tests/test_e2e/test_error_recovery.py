"""End-to-end: error containment and recovery paths (idempotency + pool restart)."""

from __future__ import annotations

import asyncio

from starlette.testclient import TestClient

from tests.conftest import API_KEY_HEADERS


def test_error_recovery_double_investigate(api_client: TestClient) -> None:
    """Re-running defense sync must not duplicate investigation steps."""
    payload = {
        "title": "Recovery duplicate run",
        "description": "Ensure replace-sync semantics.",
        "severity": "low",
        "status": "open",
    }
    r = api_client.post("/api/v1/incidents/", json=payload, headers=API_KEY_HEADERS)
    incident_id = r.json()["id"]
    assert api_client.post(f"/api/v1/incidents/{incident_id}/investigate", headers=API_KEY_HEADERS).status_code == 202
    before = api_client.get(f"/api/v1/incidents/{incident_id}", headers=API_KEY_HEADERS).json()
    n_steps = len(before["investigation_steps"])
    assert api_client.post(f"/api/v1/incidents/{incident_id}/investigate", headers=API_KEY_HEADERS).status_code == 202
    after = api_client.get(f"/api/v1/incidents/{incident_id}", headers=API_KEY_HEADERS).json()
    assert len(after["investigation_steps"]) == n_steps
    assert len(after["evidence"]) == len(before["evidence"])


def test_error_recovery_agent_restart(api_client: TestClient) -> None:
    coordinator = api_client.app.state.coordinator
    restarted = asyncio.run(coordinator._pool.restart_one_idle_agent())
    assert restarted is True

    payload = {
        "title": "Recovery row",
        "description": "Post-restart sanity",
        "severity": "low",
        "status": "open",
    }
    r = api_client.post("/api/v1/incidents/", json=payload, headers=API_KEY_HEADERS)
    incident_id = r.json()["id"]
    inv = api_client.post(f"/api/v1/incidents/{incident_id}/investigate", headers=API_KEY_HEADERS)
    assert inv.status_code == 202
    detail = api_client.get(f"/api/v1/incidents/{incident_id}", headers=API_KEY_HEADERS).json()
    assert len(detail["investigation_steps"]) >= 1
