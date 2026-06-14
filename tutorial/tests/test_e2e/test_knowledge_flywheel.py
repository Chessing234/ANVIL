"""End-to-end: defense outputs grow the orchestration knowledge flywheel."""

from __future__ import annotations

from starlette.testclient import TestClient

from tests.conftest import API_KEY_HEADERS


def test_knowledge_flywheel_growth(api_client: TestClient) -> None:
    fly0 = api_client.get("/api/v1/system/flywheel", headers=API_KEY_HEADERS).json()
    initial_nodes = int(fly0["graph_stats"]["nodes"])
    initial_edges = int(fly0["graph_stats"]["edges"])

    for idx in range(3):
        payload = {
            "title": f"Flywheel case {idx}",
            "description": "Synthetic workload for graph growth.",
            "severity": "medium",
            "status": "open",
        }
        r = api_client.post("/api/v1/incidents/", json=payload, headers=API_KEY_HEADERS)
        assert r.status_code == 201
        iid = r.json()["id"]
        inv = api_client.post(f"/api/v1/incidents/{iid}/investigate", headers=API_KEY_HEADERS)
        assert inv.status_code == 202

    fly1 = api_client.get("/api/v1/system/flywheel", headers=API_KEY_HEADERS).json()
    assert int(fly1["graph_stats"]["nodes"]) > initial_nodes
    assert int(fly1["graph_stats"]["edges"]) > initial_edges

    insights = fly1.get("defense_insights") or []
    assert isinstance(insights, list)
    assert len(insights) >= 1

    signals = fly1.get("learning_signals") or []
    assert len(signals) >= 1
