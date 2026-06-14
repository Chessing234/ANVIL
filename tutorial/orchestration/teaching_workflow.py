"""LangGraph teaching workflow for lesson synthesis with SQLite checkpointing."""

from __future__ import annotations

import operator
from uuid import UUID
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, NotRequired, TypedDict

import structlog
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from config.constants import LessonDifficulty
from shared.models import Lesson, StudentProfile

logger = structlog.get_logger(__name__)

TeachingCheckpointHook = Callable[["TeachingState"], Awaitable[None]]
TeachingEventHook = Callable[[str, dict[str, Any]], Awaitable[None]]


class TeachingState(TypedDict, total=False):
    """Teaching LangGraph state."""

    incident_id: str
    investigation_steps: Annotated[list[dict[str, Any]], operator.add]
    narrative: str
    student_profile: dict[str, Any]
    lesson: dict[str, Any] | None
    interactive_sandbox: dict[str, Any] | None
    difficulty_assessment: str
    csta_mappings: Annotated[list[str], operator.add]
    personalization_params: dict[str, Any]
    current_step: str
    errors: Annotated[list[str], operator.add]
    completed: bool
    recovery: NotRequired[dict[str, Any]]


def _iso_now() -> str:
    """Serialize current UTC time."""

    return datetime.now(timezone.utc).isoformat()


def _to_teaching_error(state: TeachingState, node: str, exc: Exception) -> Command:
    """Route failures to the teaching error handler."""

    return Command(
        goto="teaching_error_handler",
        update={
            "errors": state.get("errors", []) + [f"{node}:{exc}"],
            "current_step": "teaching_error_handler",
        },
    )


async def analyze_investigation(state: TeachingState) -> dict[str, Any] | Command:
    """Extract teachable concepts from investigation artifacts."""

    try:
        concepts = ["dns_tunneling", "memory_forensics", "lateral_movement"]
        narrative_bits = [f"Concept:{c}" for c in concepts]
        return {
            "narrative": state.get("narrative", "") + " ".join(narrative_bits),
            "current_step": "analyze_investigation",
        }
    except Exception as exc:  # pragma: no cover - defensive
        return _to_teaching_error(state, "analyze_investigation", exc)


async def assess_student(state: TeachingState) -> dict[str, Any] | Command:
    """Infer difficulty from learner profile."""

    try:
        profile = StudentProfile.model_validate(state["student_profile"])
        avg_skill = (
            sum(profile.skill_scores.values()) / len(profile.skill_scores)
            if profile.skill_scores
            else 40.0
        )
        if avg_skill > 80:
            difficulty = LessonDifficulty.ADVANCED
        elif avg_skill > 55:
            difficulty = LessonDifficulty.INTERMEDIATE
        else:
            difficulty = LessonDifficulty.BEGINNER
        return {"difficulty_assessment": difficulty.value, "current_step": "assess_student"}
    except Exception as exc:  # pragma: no cover - defensive
        return _to_teaching_error(state, "assess_student", exc)


async def generate_narrative(state: TeachingState) -> dict[str, Any] | Command:
    """Create detective storyline anchored to real investigation steps."""

    try:
        steps = state.get("investigation_steps", [])
        story = (
            "You are the lead detective. Each clue below came from the live SOC investigation: "
            + "; ".join(f"{idx}:{step.get('action_taken','')}" for idx, step in enumerate(steps))
        )
        return {"narrative": story, "current_step": "generate_narrative"}
    except Exception as exc:  # pragma: no cover - defensive
        return _to_teaching_error(state, "generate_narrative", exc)


async def build_sandbox(state: TeachingState) -> dict[str, Any] | Command:
    """Describe an isolated sandbox replica."""

    try:
        sandbox = {
            "runtime": "container",
            "image": "tutorial-lesson-sandbox:latest",
            "capabilities": ["shell", "file_read", "network_trace"],
            "ttl_minutes": 45,
        }
        return {"interactive_sandbox": sandbox, "current_step": "build_sandbox"}
    except Exception as exc:  # pragma: no cover - defensive
        return _to_teaching_error(state, "build_sandbox", exc)


async def map_curriculum(state: TeachingState) -> dict[str, Any] | Command:
    """Map teachable beats to CSTA identifiers."""

    try:
        standards = ["1B-AP-08", "2-CS-02", "3A-DA-09"]
        return {"csta_mappings": standards, "current_step": "map_curriculum"}
    except Exception as exc:  # pragma: no cover - defensive
        return _to_teaching_error(state, "map_curriculum", exc)


async def personalize(state: TeachingState) -> dict[str, Any] | Command:
    """Tune pacing and scaffolding."""

    try:
        profile = StudentProfile.model_validate(state["student_profile"])
        stem_boost = "stem" in profile.name.lower()
        params = {
            **state.get("personalization_params", {}),
            "depth": "technical" if stem_boost else "conceptual",
            "hints": "sparse" if profile.experience_level == "advanced" else "frequent",
            "pacing": "fast" if profile.preferred_learning_style == "kinesthetic" else "moderate",
        }
        return {"personalization_params": params, "current_step": "personalize"}
    except Exception as exc:  # pragma: no cover - defensive
        return _to_teaching_error(state, "personalize", exc)


async def assemble_lesson(state: TeachingState) -> dict[str, Any] | Command:
    """Materialize the ``Lesson`` aggregate."""

    try:
        incident_uuid = UUID(str(state["incident_id"]))
        difficulty_raw = state.get("difficulty_assessment", LessonDifficulty.BEGINNER.value)
        difficulty = LessonDifficulty(str(difficulty_raw))
        lesson = Lesson(
            incident_id=incident_uuid,
            title="Detective Desk: Live SOC Case",
            narrative=state.get("narrative", ""),
            interactive_steps=[
                {"kind": "sandbox", "config": state.get("interactive_sandbox", {})},
                {"kind": "reflection", "prompt": "Which TTP was most surprising?"},
            ],
            difficulty=difficulty,
            csta_standards=list(state.get("csta_mappings", [])),
            estimated_duration_minutes=45,
            student_progress={"sandbox": "ready"},
        )
        return {"lesson": lesson.model_dump(mode="json"), "current_step": "assemble_lesson"}
    except Exception as exc:  # pragma: no cover - defensive
        return _to_teaching_error(state, "assemble_lesson", exc)


def build_teaching_checkpoint(
    on_persist: TeachingCheckpointHook,
    on_event: TeachingEventHook,
) -> Callable[[TeachingState], Awaitable[dict[str, Any]]]:
    """Persist teaching artifacts and publish completion."""

    async def checkpoint(state: TeachingState) -> dict[str, Any]:
        """Persist teaching workflow output."""

        completed: TeachingState = {**state, "completed": True, "current_step": "checkpoint"}
        await on_persist(completed)
        lesson = completed.get("lesson") or {}
        lesson_id = str(lesson.get("id", "unknown-lesson"))
        await on_event("lesson_complete", {"lesson_id": lesson_id, "incident_id": state["incident_id"]})
        logger.info("teaching_checkpoint_complete", lesson_id=lesson_id)
        return {"completed": True, "current_step": "checkpoint"}

    return checkpoint


async def teaching_error_handler(state: TeachingState) -> Command:
    """Retry failed teaching nodes up to twice."""

    recovery = dict(state.get("recovery", {}))
    retries = int(recovery.get("teaching_retries", 0))
    if retries >= 2:
        return Command(
            goto="checkpoint",
            update={
                "errors": state.get("errors", []) + ["teaching_aborted"],
                "completed": True,
                "recovery": {**recovery, "teaching_retries": retries},
            },
        )
    return Command(
        goto="analyze_investigation",
        update={"recovery": {**recovery, "teaching_retries": retries + 1}},
    )


class TeachingWorkflow:
    """Teaching LangGraph with async SQLite checkpointing."""

    def __init__(
        self,
        checkpoint_path: Path,
        *,
        on_persist: TeachingCheckpointHook,
        on_event: TeachingEventHook,
    ) -> None:
        self._checkpoint_path = Path(checkpoint_path)
        self._on_persist = on_persist
        self._on_event = on_event

    def _build_builder(self) -> StateGraph:
        """Construct the teaching ``StateGraph`` prior to compilation."""

        builder = StateGraph(TeachingState)
        builder.add_node("analyze_investigation", analyze_investigation)
        builder.add_node("assess_student", assess_student)
        builder.add_node("generate_narrative", generate_narrative)
        builder.add_node("build_sandbox", build_sandbox)
        builder.add_node("map_curriculum", map_curriculum)
        builder.add_node("personalize", personalize)
        builder.add_node("assemble_lesson", assemble_lesson)
        builder.add_node("teaching_error_handler", teaching_error_handler)
        builder.add_node("checkpoint", build_teaching_checkpoint(self._on_persist, self._on_event))
        builder.add_edge(START, "analyze_investigation")
        builder.add_edge("analyze_investigation", "assess_student")
        builder.add_edge("assess_student", "generate_narrative")
        builder.add_edge("generate_narrative", "build_sandbox")
        builder.add_edge("build_sandbox", "map_curriculum")
        builder.add_edge("map_curriculum", "personalize")
        builder.add_edge("personalize", "assemble_lesson")
        builder.add_edge("assemble_lesson", "checkpoint")
        builder.add_edge("checkpoint", END)
        return builder

    async def run(self, initial: TeachingState, thread_id: str) -> dict[str, Any]:
        """Execute the teaching workflow."""

        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(str(self._checkpoint_path)) as checkpointer:
            graph = self._build_builder().compile(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": thread_id}}
            trace: list[dict[str, Any]] = []
            async for chunk in graph.astream(initial, config=config):
                trace.append({k: _serialize(v) for k, v in chunk.items()})
            snap = await graph.aget_state(config)
            final = dict(snap.values) if snap.values else dict(initial)
            return {"trace": trace, "final_state": final}


def _serialize(value: Any) -> Any:
    """Serialize streamed fragments."""

    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return repr(value)


def initial_teaching_state(
    incident_id: str,
    investigation_steps: list[dict[str, Any]],
    narrative: str,
    profile: StudentProfile,
) -> TeachingState:
    """Build initial teaching workflow payload."""

    return {
        "incident_id": incident_id,
        "investigation_steps": list(investigation_steps),
        "narrative": narrative,
        "student_profile": profile.model_dump(mode="json"),
        "lesson": None,
        "interactive_sandbox": None,
        "difficulty_assessment": LessonDifficulty.BEGINNER.value,
        "csta_mappings": [],
        "personalization_params": {},
        "current_step": "pending",
        "errors": [],
        "completed": False,
        "recovery": {},
    }
