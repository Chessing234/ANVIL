"""Agents, knowledge graph, and student recommendation API tests."""

from __future__ import annotations

import asyncio

from starlette.testclient import TestClient

from database.crud import agents as agents_crud
from database.models import AgentStatus, AgentType
from tests.conftest import API_KEY_HEADERS


def test_agents_list_pause_resume(api_client: TestClient) -> None:
    async def _seed() -> None:
        async with api_client.app.state.db_manager.session() as s:
            await agents_crud.create(
                s,
                {"name": "demo-agent", "agent_type": AgentType.INVESTIGATION, "status": AgentStatus.ACTIVE},
            )

    asyncio.run(_seed())

    r = api_client.get("/api/v1/agents/", headers=API_KEY_HEADERS)
    assert r.status_code == 200
    names = {x["name"] for x in r.json()}
    assert "demo-agent" in names

    m = api_client.get("/api/v1/agents/demo-agent/metrics", headers=API_KEY_HEADERS)
    assert m.status_code == 200
    assert "failure_rate" in m.json()

    p = api_client.post("/api/v1/agents/demo-agent/pause", headers=API_KEY_HEADERS)
    assert p.status_code == 200
    res = api_client.post("/api/v1/agents/demo-agent/resume", headers=API_KEY_HEADERS)
    assert res.status_code == 200


def test_knowledge_graph_and_path(api_client: TestClient) -> None:
    r = api_client.get("/api/v1/knowledge/graph", headers=API_KEY_HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert "nodes" in body and "edges" in body

    stats = api_client.get("/api/v1/knowledge/statistics", headers=API_KEY_HEADERS)
    assert stats.status_code == 200
    assert "node_count" in stats.json()


def test_student_create_and_recommendations(api_client: TestClient) -> None:
    payload = {
        "name": "Jamie",
        "email": "jamie@example.com",
        "experience_level": "intermediate",
    }
    r = api_client.post("/api/v1/students/", json=payload, headers=API_KEY_HEADERS)
    assert r.status_code == 201
    sid = r.json()["id"]

    d = api_client.get(f"/api/v1/students/{sid}", headers=API_KEY_HEADERS)
    assert d.status_code == 200

    rec = api_client.get(f"/api/v1/students/{sid}/recommendations", headers=API_KEY_HEADERS)
    assert rec.status_code == 200
    assert isinstance(rec.json(), list)

    cred = api_client.get(f"/api/v1/students/{sid}/credentials", headers=API_KEY_HEADERS)
    assert cred.status_code == 200
    assert cred.json()[0]["verification_hash"]
