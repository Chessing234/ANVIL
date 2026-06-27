"""Idempotent seed data: concepts, agents, sample learner, CSTA map, OWASP templates."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.constants import DEMO_STUDENT_EMAIL, DEMO_STUDENT_ID
from database.models import (
    Agent,
    AgentStatus,
    AgentType,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    KnowledgeCategory,
    KnowledgeEdge,
    KnowledgeEdgeRelation,
    KnowledgeNode,
    LessonDifficulty,
    Student,
    StudentExperience,
)

# Twenty representative CSTA 1.x–2.x standards (codes + titles) for curriculum tagging.
CSTA_STANDARDS: list[dict[str, str]] = [
    {"id": "1A-AP-08", "title": "Model daily processes by creating and following algorithms"},
    {"id": "1A-AP-10", "title": "Document programs to make them easier to follow"},
    {"id": "1A-AP-11", "title": "Decompose problems into smaller, manageable tasks"},
    {"id": "1A-CS-01", "title": "Communicate about technology using appropriate terminology"},
    {"id": "1B-AP-08", "title": "Compare and refine algorithms"},
    {"id": "1B-AP-10", "title": "Use flowcharts to plan sequences and outcomes"},
    {"id": "1B-AP-11", "title": "Decompose problems into sub-problems"},
    {"id": "1B-CS-02", "title": "Model how computers transmit data"},
    {"id": "2-AP-10", "title": "Use flowcharts to express algorithms"},
    {"id": "2-AP-11", "title": "Decompose problems and compose solutions"},
    {"id": "2-AP-12", "title": "Create procedures with parameters"},
    {"id": "2-AP-13", "title": "Decompose problems and debug programs"},
    {"id": "2-CS-01", "title": "Recommend technologies for collaborative projects"},
    {"id": "2-CS-02", "title": "Model critical Internet systems (DNS, routing)"},
    {"id": "2-DA-08", "title": "Collect and analyze data using computational tools"},
    {"id": "2-IC-20", "title": "Describe tradeoffs between usability and security"},
    {"id": "2-NI-04", "title": "Model how data are sent across networks"},
    {"id": "3A-AP-13", "title": "Create modules and document program behavior"},
    {"id": "3A-CS-01", "title": "Explain abstractions in hardware and software"},
    {"id": "3B-NI-02", "title": "Compare security tradeoffs of network designs"},
]

OWASP_TEMPLATE_INCIDENTS: list[dict[str, Any]] = [
    {"title": "A01 Broken Access Control", "incident_type": "owasp_a01", "severity": IncidentSeverity.HIGH},
    {"title": "A02 Cryptographic Failures", "incident_type": "owasp_a02", "severity": IncidentSeverity.HIGH},
    {"title": "A03 Injection", "incident_type": "owasp_a03", "severity": IncidentSeverity.CRITICAL},
    {"title": "A04 Insecure Design", "incident_type": "owasp_a04", "severity": IncidentSeverity.MEDIUM},
    {"title": "A05 Security Misconfiguration", "incident_type": "owasp_a05", "severity": IncidentSeverity.MEDIUM},
    {"title": "A06 Vulnerable Components", "incident_type": "owasp_a06", "severity": IncidentSeverity.MEDIUM},
    {"title": "A07 Auth Failures", "incident_type": "owasp_a07", "severity": IncidentSeverity.HIGH},
    {"title": "A08 Software/Data Integrity", "incident_type": "owasp_a08", "severity": IncidentSeverity.HIGH},
    {"title": "A09 Logging/Monitoring Failures", "incident_type": "owasp_a09", "severity": IncidentSeverity.LOW},
    {"title": "A10 SSRF", "incident_type": "owasp_a10", "severity": IncidentSeverity.HIGH},
]

CONCEPT_NODES: list[dict[str, Any]] = [
    {
        "id": "concept:dns",
        "name": "DNS",
        "description": "Name resolution, records, and cache poisoning basics.",
        "category": KnowledgeCategory.NETWORK,
        "difficulty": LessonDifficulty.BEGINNER,
    },
    {
        "id": "concept:tcpip",
        "name": "TCP/IP",
        "description": "Layered model, ports, handshakes, and congestion signals.",
        "category": KnowledgeCategory.NETWORK,
        "difficulty": LessonDifficulty.INTERMEDIATE,
    },
    {
        "id": "concept:malware",
        "name": "Malware",
        "description": "Viruses, worms, trojans, and behavioral indicators.",
        "category": KnowledgeCategory.MALWARE,
        "difficulty": LessonDifficulty.INTERMEDIATE,
    },
    {
        "id": "concept:encryption",
        "name": "Encryption",
        "description": "Symmetric/asymmetric crypto and key management hygiene.",
        "category": KnowledgeCategory.CRYPTO,
        "difficulty": LessonDifficulty.INTERMEDIATE,
    },
    {
        "id": "concept:authentication",
        "name": "Authentication",
        "description": "Passwords, MFA, sessions, and common bypass patterns.",
        "category": KnowledgeCategory.IDENTITY,
        "difficulty": LessonDifficulty.BEGINNER,
    },
    {
        "id": "concept:authorization",
        "name": "Authorization",
        "description": "RBAC/ABAC, IDOR, and scope enforcement.",
        "category": KnowledgeCategory.IDENTITY,
        "difficulty": LessonDifficulty.ADVANCED,
    },
    {
        "id": "concept:logging",
        "name": "Logging & Monitoring",
        "description": "Telemetry, retention, detection engineering fundamentals.",
        "category": KnowledgeCategory.OPS,
        "difficulty": LessonDifficulty.BEGINNER,
    },
    {
        "id": "concept:web_security",
        "name": "Web Application Security",
        "description": "HTTP semantics, cookies, CSRF, XSS, SSRF.",
        "category": KnowledgeCategory.WEB,
        "difficulty": LessonDifficulty.ADVANCED,
    },
    {
        "id": "concept:data_protection",
        "name": "Data Protection",
        "description": "Classification, least privilege, and exfiltration paths.",
        "category": KnowledgeCategory.DATA,
        "difficulty": LessonDifficulty.INTERMEDIATE,
    },
    {
        "id": "concept:incident_response",
        "name": "Incident Response",
        "description": "Triage, containment, eradication, recovery, and lessons learned.",
        "category": KnowledgeCategory.OPS,
        "difficulty": LessonDifficulty.ADVANCED,
    },
]

DEFAULT_AGENTS: list[dict[str, Any]] = [
    {"name": "investigator-alpha", "agent_type": AgentType.INVESTIGATION, "status": AgentStatus.ACTIVE},
    {"name": "containment-bravo", "agent_type": AgentType.CONTAINMENT, "status": AgentStatus.IDLE},
    {"name": "teacher-charlie", "agent_type": AgentType.TEACHING, "status": AgentStatus.ACTIVE},
    {"name": "evidence-delta", "agent_type": AgentType.EVIDENCE, "status": AgentStatus.IDLE},
    {"name": "orchestrator-omega", "agent_type": AgentType.ORCHESTRATOR, "status": AgentStatus.ACTIVE},
]


async def _has_rows(session: AsyncSession, model: type) -> bool:
    res = await session.execute(select(model).limit(1))
    return res.first() is not None


async def seed_database(session: AsyncSession) -> dict[str, int]:
    """
    Populate baseline knowledge, agents, sample student, and OWASP template incidents.

    Safe to call multiple times: skips entities that already exist.
    """
    counts = {"knowledge_nodes": 0, "knowledge_edges": 0, "agents": 0, "students": 0, "incidents": 0}

    if not await _has_rows(session, KnowledgeNode):
        for node in CONCEPT_NODES:
            session.add(KnowledgeNode(**node))
            counts["knowledge_nodes"] += 1
        await session.flush()

        edges = [
            ("concept:dns", "concept:tcpip", KnowledgeEdgeRelation.PREREQUISITE),
            ("concept:tcpip", "concept:web_security", KnowledgeEdgeRelation.PREREQUISITE),
            ("concept:authentication", "concept:authorization", KnowledgeEdgeRelation.PREREQUISITE),
            ("concept:encryption", "concept:data_protection", KnowledgeEdgeRelation.PREREQUISITE),
            ("concept:logging", "concept:incident_response", KnowledgeEdgeRelation.RELATED),
        ]
        for src, tgt, rel in edges:
            session.add(
                KnowledgeEdge(
                    id=uuid.uuid4(),
                    source_id=src,
                    target_id=tgt,
                    relation_type=rel,
                    weight=1.0,
                    evidence_count=0,
                )
            )
            counts["knowledge_edges"] += 1

    if not await _has_rows(session, Agent):
        for cfg in DEFAULT_AGENTS:
            session.add(Agent(id=uuid.uuid4(), **cfg))
            counts["agents"] += 1

    existing = await session.scalar(select(Student).where(Student.email == DEMO_STUDENT_EMAIL))
    if existing is None:
        session.add(
            Student(
                id=DEMO_STUDENT_ID,
                name="Seed Student",
                email=DEMO_STUDENT_EMAIL,
                experience_level=StudentExperience.INTERMEDIATE,
                preferred_learning_style="visual",
                skill_scores={"dns": 0.8, "tcpip": 0.4, "malware": 0.3},
                completed_lessons=[],
                streak_days=1,
                total_time_minutes=0,
            )
        )
        counts["students"] += 1

    if not await _has_rows(session, Incident):
        csta_ids = [x["id"] for x in CSTA_STANDARDS[:5]]
        for tmpl in OWASP_TEMPLATE_INCIDENTS:
            session.add(
                Incident(
                    id=uuid.uuid4(),
                    title=tmpl["title"],
                    description=f"Template aligned to CSTA examples: {', '.join(csta_ids)}",
                    severity=tmpl["severity"],
                    status=IncidentStatus.OPEN,
                    incident_type=tmpl["incident_type"],
                    tags=["owasp", "template"],
                )
            )
            counts["incidents"] += 1

    await session.flush()
    return counts
