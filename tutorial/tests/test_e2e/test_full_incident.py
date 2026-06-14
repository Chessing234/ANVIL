"""End-to-end: incident submission through investigation, evidence, and auto-lesson."""

from __future__ import annotations

from starlette.testclient import TestClient

from tests.conftest import API_KEY_HEADERS


def test_complete_incident_lifecycle(api_client: TestClient) -> None:
    fly0 = api_client.get("/api/v1/system/flywheel", headers=API_KEY_HEADERS)
    assert fly0.status_code == 200
    initial_nodes = int(fly0.json()["graph_stats"]["nodes"])
    initial_edges = int(fly0.json()["graph_stats"]["edges"])

    payload = {
        "title": "E2E urgent lateral movement",
        "description": "Suspicious PowerShell and outbound DNS tunneling.",
        "severity": "high",
        "status": "open",
        "incident_type": "e2e",
    }
    r = api_client.post("/api/v1/incidents/", json=payload, headers=API_KEY_HEADERS)
    assert r.status_code == 201
    incident_id = r.json()["id"]

    inv = api_client.post(f"/api/v1/incidents/{incident_id}/investigate", headers=API_KEY_HEADERS)
    assert inv.status_code == 202

    detail = api_client.get(f"/api/v1/incidents/{incident_id}", headers=API_KEY_HEADERS)
    assert detail.status_code == 200
    body = detail.json()
    steps = body["investigation_steps"]
    assert len(steps) >= 3
    assert any(s.get("is_self_correction") for s in steps)

    evidence = body["evidence"]
    assert len(evidence) >= 1
    assert all(e.get("verified_at") is not None for e in evidence)

    coc = api_client.get(f"/api/v1/investigations/{incident_id}/chain-of-custody", headers=API_KEY_HEADERS)
    assert coc.status_code == 200
    chains = coc.json().get("chains") or {}
    assert isinstance(chains, dict)
    assert len(chains) >= 1

    acc = api_client.get(f"/api/v1/incidents/{incident_id}/accuracy-report", headers=API_KEY_HEADERS)
    assert acc.status_code == 200
    report = acc.json().get("accuracy_report") or {}
    assert report.get("overall_accuracy_rating") in ("HIGH", "MEDIUM")
    assert int(report.get("self_corrections_performed", 0)) > 0

    lessons = body.get("lessons") or []
    assert len(lessons) >= 1
    lesson_id = lessons[0]["id"]

    les = api_client.get(f"/api/v1/lessons/{lesson_id}", headers=API_KEY_HEADERS)
    assert les.status_code == 200
    lbody = les.json()
    assert lbody.get("narrative")
    assert len(lbody.get("interactive_elements") or []) > 0

    cur = api_client.get(f"/api/v1/lessons/{lesson_id}/curriculum-mapping", headers=API_KEY_HEADERS)
    assert cur.status_code == 200
    cmap = cur.json()
    assert len(cmap.get("standards_covered") or []) > 0

    fly1 = api_client.get("/api/v1/system/flywheel", headers=API_KEY_HEADERS)
    assert fly1.status_code == 200
    g1 = fly1.json()["graph_stats"]
    assert int(g1["nodes"]) >= initial_nodes
    assert int(g1["edges"]) >= initial_edges
