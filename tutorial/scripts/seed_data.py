#!/usr/bin/env python3
"""Seed base catalog data plus rich Prompt-19 demo fixtures (idempotent)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from api.converters import database_url_to_async
from config.settings import get_settings
from database.connection import DatabaseManager
from database.crud import knowledge as knowledge_crud
from database.crud import lessons as lessons_crud
from database.models import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    KnowledgeCategory,
    KnowledgeEdge,
    KnowledgeEdgeRelation,
    Lesson,
    LessonDifficulty,
    Student,
    StudentExperience,
    StudentProgress,
)
from database.seed_data import seed_database


async def _seed_rich_demo(session) -> None:
    """Add five scenario incidents, three students, graph nodes/edges, lessons, and sample progress."""

    scenarios = [
        ("Ransomware: encrypted shares", "Encryption artifacts on file servers.", "ransomware", IncidentSeverity.CRITICAL),
        ("Data exfiltration over DNS", "High-volume TXT queries to rare domains.", "exfiltration", IncidentSeverity.HIGH),
        ("Malware persistence via WMI", "Suspicious WMI event filters.", "malware", IncidentSeverity.HIGH),
        ("Insider threat: bulk download", "HR dataset accessed off-hours.", "insider", IncidentSeverity.MEDIUM),
        ("DDoS against edge CDN", "Spike in SYN floods from botnet.", "ddos", IncidentSeverity.MEDIUM),
    ]
    for title, desc, itype, sev in scenarios:
        exists = await session.scalar(select(Incident.id).where(Incident.title == title))
        if exists is None:
            session.add(
                Incident(
                    id=uuid.uuid4(),
                    title=title,
                    description=desc,
                    severity=sev,
                    status=IncidentStatus.OPEN,
                    incident_type=itype,
                    tags=["prompt19", "seed"],
                ),
            )

    students_specs = [
        ("Beginner Blake", "blake.beginner@tutorial.local", StudentExperience.NOVICE),
        ("Intermediate Ira", "ira.intermediate@tutorial.local", StudentExperience.INTERMEDIATE),
        ("Advanced Avery", "avery.advanced@tutorial.local", StudentExperience.EXPERT),
    ]
    student_ids: list[uuid.UUID] = []
    for name, email, level in students_specs:
        existing = await session.scalar(select(Student.id).where(Student.email == email))
        if existing is None:
            sid = uuid.uuid4()
            session.add(
                Student(
                    id=sid,
                    name=name,
                    email=email,
                    experience_level=level,
                    preferred_learning_style="mixed",
                    skill_scores={"stem": 0.7},
                    completed_lessons=[],
                    streak_days=0,
                    total_time_minutes=0,
                ),
            )
            student_ids.append(sid)
        else:
            student_ids.append(existing)

    node_specs: list[tuple[str, str, KnowledgeCategory, LessonDifficulty]] = [
        ("p19:ransomware", "Ransomware basics", KnowledgeCategory.MALWARE, LessonDifficulty.BEGINNER),
        ("p19:dns", "DNS tunneling", KnowledgeCategory.NETWORK, LessonDifficulty.INTERMEDIATE),
        ("p19:wmi", "WMI persistence", KnowledgeCategory.MALWARE, LessonDifficulty.ADVANCED),
        ("p19:insider", "Insider risk", KnowledgeCategory.IDENTITY, LessonDifficulty.INTERMEDIATE),
        ("p19:ddos", "DDoS mitigation", KnowledgeCategory.NETWORK, LessonDifficulty.BEGINNER),
        ("p19:stem", "STEM forensics lab", KnowledgeCategory.DATA, LessonDifficulty.INTERMEDIATE),
        ("p19:logs", "Log correlation", KnowledgeCategory.OPS, LessonDifficulty.ADVANCED),
        ("p19:netflow", "Netflow triage", KnowledgeCategory.NETWORK, LessonDifficulty.INTERMEDIATE),
        ("p19:memory", "Memory forensics", KnowledgeCategory.MALWARE, LessonDifficulty.ADVANCED),
        ("p19:ir", "Incident response playbooks", KnowledgeCategory.OPS, LessonDifficulty.BEGINNER),
        ("p19:crypto", "Crypto hygiene", KnowledgeCategory.CRYPTO, LessonDifficulty.BEGINNER),
        ("p19:web", "Web attack surface", KnowledgeCategory.WEB, LessonDifficulty.INTERMEDIATE),
        ("p19:zero", "Zero trust design", KnowledgeCategory.IDENTITY, LessonDifficulty.ADVANCED),
        ("p19:automation", "SOAR automation", KnowledgeCategory.OPS, LessonDifficulty.INTERMEDIATE),
        ("p19:edu", "Cyber education mapping", KnowledgeCategory.OTHER, LessonDifficulty.BEGINNER),
        ("p19:threat", "Threat intel fusion", KnowledgeCategory.DATA, LessonDifficulty.ADVANCED),
        ("p19:cloud", "Cloud logging", KnowledgeCategory.OPS, LessonDifficulty.INTERMEDIATE),
        ("p19:endpoint", "Endpoint telemetry", KnowledgeCategory.MALWARE, LessonDifficulty.INTERMEDIATE),
        ("p19:privacy", "Data minimization", KnowledgeCategory.DATA, LessonDifficulty.BEGINNER),
        ("p19:ethics", "Ethical disclosure", KnowledgeCategory.OTHER, LessonDifficulty.BEGINNER),
    ]
    for nid, label, cat, diff in node_specs:
        if await knowledge_crud.get_node(session, nid) is None:
            await knowledge_crud.create_node(
                session,
                {
                    "id": nid,
                    "name": label,
                    "description": f"Prompt19 seed node: {label}",
                    "category": cat,
                    "difficulty": diff,
                },
            )

    edges = [
        ("p19:ransomware", "p19:memory", KnowledgeEdgeRelation.RELATED),
        ("p19:dns", "p19:netflow", KnowledgeEdgeRelation.PREREQUISITE),
        ("p19:wmi", "p19:endpoint", KnowledgeEdgeRelation.RELATED),
        ("p19:insider", "p19:privacy", KnowledgeEdgeRelation.BUILDS_ON),
        ("p19:ddos", "p19:netflow", KnowledgeEdgeRelation.RELATED),
    ]
    for src, dst, rel in edges:
        exists = await session.scalar(
            select(KnowledgeEdge.id).where(
                KnowledgeEdge.source_id == src,
                KnowledgeEdge.target_id == dst,
                KnowledgeEdge.relation_type == rel,
            ),
        )
        if exists is None:
            await knowledge_crud.create_edge(
                session,
                {
                    "source_id": src,
                    "target_id": dst,
                    "relation_type": rel,
                    "weight": 0.85,
                    "evidence_count": 1,
                },
            )

    first_incident = await session.scalar(
        select(Incident.id).where(Incident.title == "Ransomware: encrypted shares").limit(1),
    )
    if first_incident is None:
        first_incident = await session.scalar(select(Incident.id).order_by(Incident.created_at.asc()).limit(1))
    if first_incident is not None:
        for idx in range(5):
            title = f"Prompt19 lesson pack {idx + 1}"
            lid = await session.scalar(select(Lesson.id).where(Lesson.title == title))
            if lid is None:
                await lessons_crud.create(
                    session,
                    {
                        "incident_id": first_incident,
                        "title": title,
                        "narrative": f"Seeded narrative {idx + 1} with interactive beats.",
                        "difficulty": LessonDifficulty.INTERMEDIATE,
                        "interactive_elements": [{"kind": "quiz", "id": idx}],
                        "csta_standards": ["1B-AP-08", "2-CS-02"],
                    },
                )

    if student_ids:
        lesson_any = await session.scalar(select(Lesson.id).where(Lesson.title.like("Prompt19 lesson%")).limit(1))
        if lesson_any is not None:
            sid0 = student_ids[0]
            exists_p = await session.scalar(
                select(StudentProgress.id).where(
                    StudentProgress.student_id == sid0,
                    StudentProgress.lesson_id == lesson_any,
                ),
            )
            if exists_p is None:
                session.add(
                    StudentProgress(
                        id=uuid.uuid4(),
                        student_id=sid0,
                        lesson_id=lesson_any,
                        completion_percentage=1.0,
                        score=0.92,
                        hints_used=0,
                        time_spent_minutes=42,
                        interactions=[{"type": "complete", "at": datetime.now(timezone.utc).isoformat()}],
                        completed_at=datetime.now(timezone.utc),
                    ),
                )


async def _run() -> None:
    settings = get_settings()
    url = database_url_to_async(settings.database.url)
    mgr = DatabaseManager(url, pool_size=settings.database.pool_size, echo=settings.database.echo)
    await mgr.initialize()
    async with mgr.session() as session:
        await seed_database(session)
        await _seed_rich_demo(session)
    await mgr.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
