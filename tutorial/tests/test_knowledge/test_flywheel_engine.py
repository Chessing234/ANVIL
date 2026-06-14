"""Tests for ``FlywheelEngine``."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from config.constants import LessonDifficulty
from core.message_bus import MessageBus
from knowledge.flywheel_engine import FlywheelEngine
from knowledge.knowledge_graph import KnowledgeGraph
from knowledge.models import DefenseInsight, StudentProgress
from shared.models import Hypothesis, HypothesisState, InvestigationResult, InvestigationStep, Lesson, Message, StudentProfile


@pytest.mark.asyncio
async def test_flywheel_defense_and_bus(tmp_path) -> None:
    bus = MessageBus()
    await bus.start()
    received: list[Message] = []

    async def tap(msg: Message) -> None:
        if msg.payload.get("event") == "teaching_opportunity":
            received.append(msg)

    bus.subscribe("tutorial.system", tap)
    graph = KnowledgeGraph(tmp_path / "fw_kg.sqlite")
    eng = FlywheelEngine(
        graph,
        bus,
        config={
            "feedback_db_path": tmp_path / "fb.sqlite",
            "embedding_db_path": tmp_path / "emb.sqlite",
            "adaptive_db_path": tmp_path / "adapt.sqlite",
            "flywheel_action_db": tmp_path / "actions.sqlite",
        },
    )
    await eng.initialize()
    eng.register_handlers(bus)
    iid = uuid4()
    inv = InvestigationResult(
        incident_id=iid,
        steps=[
            InvestigationStep(
                incident_id=iid,
                agent_name="a",
                action_taken="memory triage",
                tool_used="volatility netscan",
                interpretation="suspicious outbound",
                raw_output="malfind hit",
                confidence=0.7,
            ),
        ],
        narrative="investigation complete",
        tools_used=["volatility"],
        hypotheses=[
            Hypothesis(text="C2 over DNS", state=HypothesisState.CONFIRMED, confidence=0.8),
            Hypothesis(text="Benign scanner", state=HypothesisState.REJECTED, confidence=0.2),
        ],
    )
    await eng.on_defense_complete(str(iid), inv)
    await bus.publish(
        "tutorial.system",
        Message(
            topic="tutorial.system",
            payload={
                "flywheel_dispatch": True,
                "kind": "defense_complete",
                "incident_id": str(iid),
                "investigation_result": inv.model_dump(mode="json"),
            },
            source_agent="test",
        ),
    )
    await asyncio.sleep(0.08)
    assert received
    related = await eng.cross_pollinate(str(iid))
    assert isinstance(related, list)
    await eng.unregister_handlers(bus)
    await bus.stop()


@pytest.mark.asyncio
async def test_flywheel_lesson_and_interaction(tmp_path) -> None:
    bus = MessageBus()
    await bus.start()
    graph = KnowledgeGraph(tmp_path / "fw_kg2.sqlite")
    eng = FlywheelEngine(
        graph,
        bus,
        config={
            "feedback_db_path": tmp_path / "fb2.sqlite",
            "embedding_db_path": tmp_path / "emb2.sqlite",
            "adaptive_db_path": tmp_path / "adapt2.sqlite",
            "flywheel_action_db": tmp_path / "act2.sqlite",
        },
    )
    await eng.initialize()
    lu = uuid4()
    lid = str(lu)
    les = Lesson(
        id=lu,
        incident_id=uuid4(),
        title="L",
        narrative="n",
        difficulty=LessonDifficulty.BEGINNER,
        student_progress={"mastery_by_concept": {"packet_analysis": 0.8}},
    )
    prog = StudentProgress(lesson_id=lid, student_id="stu-1", completion_rate=0.4, hint_usage_count=7)
    await eng.on_lesson_complete(lid, les, prog)
    await eng.on_student_interaction(
        {"student_id": "stu-1", "concept": "packet_analysis", "correct": False, "wrong_attempts": 3, "response_time_seconds": 5.0},
    )
    path = await eng.optimize_learning_path("stu-1", StudentProfile(name="x", skill_scores={"a": 80}))
    assert isinstance(path, list)
    insight = DefenseInsight(
        id="i1",
        concept_id="c1",
        insight_type="student_struggle",
        description="d",
        recommended_action="review prerequisites",
    )
    await eng.auto_enhance_lesson(lid, insight)
    await bus.stop()
