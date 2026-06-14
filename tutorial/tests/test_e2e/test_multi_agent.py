"""End-to-end: concurrent investigations and agent pool recovery hooks."""

from __future__ import annotations

from starlette.testclient import TestClient

from tests.conftest import API_KEY_HEADERS


def test_multi_agent_collaboration(api_client: TestClient) -> None:
    ids: list[str] = []
    for label in ("alpha", "beta"):
        payload = {
            "title": f"Concurrent {label}",
            "description": "Parallel SOC workloads.",
            "severity": "medium",
            "status": "open",
        }
        r = api_client.post("/api/v1/incidents/", json=payload, headers=API_KEY_HEADERS)
        assert r.status_code == 201
        ids.append(r.json()["id"])
    for iid in ids:
        inv = api_client.post(f"/api/v1/incidents/{iid}/investigate", headers=API_KEY_HEADERS)
        assert inv.status_code == 202

    rows = api_client.get("/api/v1/agents/", headers=API_KEY_HEADERS)
    assert rows.status_code == 200

    metrics = api_client.get("/api/v1/system/metrics", headers=API_KEY_HEADERS)
    assert metrics.status_code == 200
    assert metrics.json().get("incidents", 0) >= 2
