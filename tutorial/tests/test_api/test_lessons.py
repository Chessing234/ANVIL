"""Lesson API tests."""

from __future__ import annotations

import asyncio

from starlette.testclient import TestClient

from database.crud import incidents as incidents_crud
from database.crud import lessons as lessons_crud
from database.crud import students as students_crud
from database.models import IncidentSeverity, IncidentStatus, LessonDifficulty, StudentExperience
from tests.conftest import API_KEY_HEADERS


def test_lesson_list_get_start_interaction_sandbox(api_client: TestClient) -> None:
    async def _seed() -> tuple[str, str]:
        async with api_client.app.state.db_manager.session() as s:
            inc = await incidents_crud.create(
                s,
                {
                    "title": "T",
                    "description": "d",
                    "severity": IncidentSeverity.LOW,
                    "status": IncidentStatus.OPEN,
                },
            )
            les = await lessons_crud.create(
                s,
                {
                    "incident_id": inc.id,
                    "title": "Intro lesson",
                    "narrative": "Hello",
                    "difficulty": LessonDifficulty.BEGINNER,
                },
            )
            stu = await students_crud.create(
                s,
                {
                    "name": "Alex",
                    "email": "alex@example.com",
                    "experience_level": StudentExperience.INTERMEDIATE,
                },
            )
            return str(les.id), str(stu.id)

    lesson_id, student_id = asyncio.run(_seed())

    r = api_client.get("/api/v1/lessons/", headers=API_KEY_HEADERS)
    assert r.status_code == 200
    assert any(x["id"] == lesson_id for x in r.json())

    r2 = api_client.get(f"/api/v1/lessons/{lesson_id}", headers=API_KEY_HEADERS)
    assert r2.status_code == 200
    assert r2.json()["title"] == "Intro lesson"

    r3 = api_client.post(
        f"/api/v1/lessons/{lesson_id}/start",
        params={"student_id": student_id},
        headers=API_KEY_HEADERS,
    )
    assert r3.status_code == 201

    body = {"student_id": student_id, "interaction": {"type": "click", "target": "step-1"}}
    r4 = api_client.post(
        f"/api/v1/lessons/{lesson_id}/interaction",
        json=body,
        headers=API_KEY_HEADERS,
    )
    assert r4.status_code == 204

    r5 = api_client.get(f"/api/v1/lessons/{lesson_id}/sandbox", headers=API_KEY_HEADERS)
    assert r5.status_code == 200
    assert r5.json()["lesson_id"] == lesson_id
