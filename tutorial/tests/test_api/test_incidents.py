"""Incident API tests."""

from __future__ import annotations

import asyncio
import uuid

from starlette.testclient import TestClient

from tests.conftest import API_KEY_HEADERS


def test_incident_crud_and_upload(api_client: TestClient, tmp_path) -> None:
    payload = {
        "title": "Suspicious login",
        "description": "Multiple failed authentications observed.",
        "severity": "medium",
        "status": "open",
        "incident_type": "auth",
    }
    r = api_client.post("/api/v1/incidents/", json=payload, headers=API_KEY_HEADERS)
    assert r.status_code == 201
    body = r.json()
    incident_id = body["id"]

    r2 = api_client.get("/api/v1/incidents/", headers=API_KEY_HEADERS)
    assert r2.status_code == 200
    assert any(x["id"] == incident_id for x in r2.json())

    r3 = api_client.get(f"/api/v1/incidents/{incident_id}", headers=API_KEY_HEADERS)
    assert r3.status_code == 200
    detail = r3.json()
    assert detail["incident"]["title"] == payload["title"]

    r4 = api_client.get(f"/api/v1/incidents/{incident_id}/accuracy-report", headers=API_KEY_HEADERS)
    assert r4.status_code == 200
    assert r4.json()["accuracy_report"] is None

    files = {"file": ("note.txt", b"artifact-bytes", "text/plain")}
    r5 = api_client.post(
        f"/api/v1/incidents/{incident_id}/evidence",
        files=files,
        headers=API_KEY_HEADERS,
    )
    assert r5.status_code == 201
    assert len(r5.json()["hash_sha256"]) == 64


def test_incident_unauthorized(api_client: TestClient) -> None:
    r = api_client.get("/api/v1/incidents/")
    assert r.status_code == 401


def test_investigation_endpoints(api_client: TestClient) -> None:
    payload = {
        "title": "Case B",
        "description": "Investigation chain test",
        "severity": "low",
        "status": "open",
    }
    r = api_client.post("/api/v1/incidents/", json=payload, headers=API_KEY_HEADERS)
    incident_id = r.json()["id"]

    async def _seed() -> None:
        from database.crud import investigations as inv

        async with api_client.app.state.db_manager.session() as s:
            await inv.create_step(
                s,
                uuid.UUID(incident_id),
                {
                    "agent_name": "unit",
                    "action_taken": "scan",
                    "confidence": 0.5,
                    "is_self_correction": True,
                    "correction_reason": "adjustment",
                    "execution_time_ms": 10,
                },
            )

    asyncio.run(_seed())

    steps = api_client.get(f"/api/v1/investigations/{incident_id}/steps", headers=API_KEY_HEADERS)
    assert steps.status_code == 200
    assert len(steps.json()) == 1

    corr = api_client.get(f"/api/v1/investigations/{incident_id}/self-corrections", headers=API_KEY_HEADERS)
    assert corr.status_code == 200
    assert len(corr.json()) == 1

    ev = api_client.get(f"/api/v1/investigations/{incident_id}/evidence", headers=API_KEY_HEADERS)
    assert ev.status_code == 200

    coc = api_client.get(f"/api/v1/investigations/{incident_id}/chain-of-custody", headers=API_KEY_HEADERS)
    assert coc.status_code == 200
    assert "chains" in coc.json()
