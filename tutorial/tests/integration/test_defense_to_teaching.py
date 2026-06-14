"""Integration: defense workflow artifacts appear in teaching-ready lesson rows."""

from __future__ import annotations

from starlette.testclient import TestClient

from tests.conftest import API_KEY_HEADERS


def test_defense_output_feeds_teaching_row(api_client: TestClient) -> None:
    payload = {
        "title": "Defense→Teaching bridge",
        "description": "Validate narrative carries investigation language.",
        "severity": "medium",
        "status": "open",
    }
    r = api_client.post("/api/v1/incidents/", json=payload, headers=API_KEY_HEADERS)
    incident_id = r.json()["id"]
    assert api_client.post(f"/api/v1/incidents/{incident_id}/investigate", headers=API_KEY_HEADERS).status_code == 202
    detail = api_client.get(f"/api/v1/incidents/{incident_id}", headers=API_KEY_HEADERS).json()
    assert detail["investigation_steps"]
    lesson_id = detail["lessons"][0]["id"]
    les = api_client.get(f"/api/v1/lessons/{lesson_id}", headers=API_KEY_HEADERS).json()
    narrative = les.get("narrative", "")
    assert "investigation" in narrative.lower() or "detective" in narrative.lower() or "clue" in narrative.lower()
