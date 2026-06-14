"""Map narratives and sandboxes to CSTA standards, objectives, and assessments."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from agents.teaching.education_models import (
    AssessmentRubric,
    CSTAStandard,
    CurriculumMapping,
    LearningObjective,
    LessonContent,
    RubricCriterion,
    StandardCoverage,
    Sandbox,
)
from agents.teaching.narrative_types import NarrativeResult, Story
from agents.teaching.tools.csta_mapper import CSTAMapper
from config.constants import AgentType
from core.base_agent import BaseAgent
from core.message_bus import MessageBus

logger = structlog.get_logger(__name__)


def _scene_ids_from_story(story: Story) -> list[str]:
    arc = story.arc
    ids = [arc.setup.id]
    ids.extend(s.id for s in arc.rising_action)
    ids.append(arc.climax.id)
    ids.extend(s.id for s in arc.falling_action)
    ids.append(arc.resolution.id)
    return ids


def _concept_labels(narrative: NarrativeResult) -> list[str]:
    labels: list[str] = []
    for m in narrative.concepts_taught:
        labels.append(m.concept_id)
    arc = narrative.story.arc
    for scene in [arc.setup, *arc.rising_action, arc.climax, *arc.falling_action, arc.resolution]:
        for c in scene.concepts_demonstrated:
            labels.append(c.label)
    return list(dict.fromkeys(labels))


class CurriculumIntegrationAgent(BaseAgent):
    """Aligns generated lessons with CSTA coverage, objectives, and assessment design."""

    def __init__(
        self,
        message_bus: MessageBus,
        config: dict[str, Any],
        *,
        name: str = "teaching_curriculum",
        mapper: CSTAMapper | None = None,
    ) -> None:
        super().__init__(name, AgentType.TEACHING_CURRICULUM, message_bus, config)
        self._mapper = mapper or CSTAMapper()
        self._grade_band = str(config.get("csta_grade_band", "9-12"))

    async def _run_iteration(self) -> None:
        await asyncio.sleep(0.5)

    def _segments_for_concept(self, narrative: NarrativeResult, concept: str) -> list[str]:
        segs: list[str] = []
        arc = narrative.story.arc
        for scene in [
            arc.setup,
            *arc.rising_action,
            arc.climax,
            *arc.falling_action,
            arc.resolution,
        ]:
            if any(c.label == concept or c.id == concept for c in scene.concepts_demonstrated):
                segs.append(scene.id)
        for m in narrative.concepts_taught:
            if m.concept_id == concept and m.scene_id not in segs:
                segs.append(m.scene_id)
        return segs

    async def map_curriculum(self, narrative: NarrativeResult, sandbox: Sandbox) -> CurriculumMapping:
        """Produce traceable CSTA coverage, objectives, rubric, prerequisites, and sequencing."""

        concepts = _concept_labels(narrative)
        if not concepts:
            concepts = ["cybersecurity awareness"]

        standards_hit: dict[str, Any] = {}
        for c in concepts:
            for std in self._mapper.find_standards([c], self._grade_band)[:3]:
                standards_hit.setdefault(std.id, std)

        if not standards_hit:
            for std in self._mapper.find_standards(["encryption"], self._grade_band):
                standards_hit.setdefault(std.id, std)

        concept_to_stds: dict[str, list[CSTAStandard]] = {}
        for c in concepts:
            concept_to_stds[c] = self._mapper.find_standards([c], self._grade_band)

        coverage: list[StandardCoverage] = []
        for std in standards_hit.values():
            related = [c for c, sts in concept_to_stds.items() if any(s.id == std.id for s in sts)]
            if not related:
                related = concepts[:1]
            lesson_segments: list[str] = []
            for rc in related[:5]:
                lesson_segments.extend(self._segments_for_concept(narrative, rc))
            lesson_segments = list(dict.fromkeys(lesson_segments))
            coverage.append(
                StandardCoverage(
                    standard=std,
                    lesson_segments=lesson_segments or _scene_ids_from_story(narrative.story)[:2],
                    assessment_method="rubric + sandbox challenge completion",
                    mastery_criteria="Learner explains the control or artifact and completes aligned sandbox checks.",
                ),
            )

        objectives: list[LearningObjective] = []
        for i, std in enumerate(standards_hit.values()):
            objectives.append(
                LearningObjective(
                    id=f"obj-{std.id}-{i}",
                    text=f"Students will explain {std.description[:160]} in the context of the lesson narrative.",
                    aligned_standard_ids=[std.id],
                    bloom_level="analyze",
                ),
            )

        rubric = AssessmentRubric(
            title="Cyber lesson mastery",
            criteria=[
                RubricCriterion(
                    criterion="Conceptual explanation",
                    weight=0.35,
                    mastery_description="Accurate use of security vocabulary tied to narrative evidence.",
                ),
                RubricCriterion(
                    criterion="Sandbox execution",
                    weight=0.45,
                    mastery_description=f"Completes {len(sandbox.challenges)} challenges with evidence-based reasoning.",
                ),
                RubricCriterion(
                    criterion="Responsible computing",
                    weight=0.2,
                    mastery_description="Discusses ethics, privacy, or impact appropriately.",
                ),
            ],
            passing_score=0.72,
        )

        prereq_map: dict[str, list[str]] = {}
        for sid in standards_hit:
            prereq_map[sid] = self._mapper.get_prerequisites(sid)

        sequence = self._mapper.get_learning_path(list(standards_hit.keys()))

        lesson = LessonContent(
            title=narrative.title,
            narrative_summary=narrative.story.synopsis,
            scene_ids=_scene_ids_from_story(narrative.story),
            concept_labels=concepts,
            default_difficulty=narrative.difficulty_level,
            sandbox_challenge_ids=[c.id for c in sandbox.challenges],
            pacing_minutes=narrative.estimated_duration_minutes,
        )
        report = self._mapper.validate_coverage(lesson)

        logger.info(
            "curriculum_mapped",
            standards=len(standards_hit),
            gaps=len(report.unmapped_concepts),
        )
        return CurriculumMapping(
            standards_covered=coverage,
            learning_objectives=objectives,
            assessment_rubric=rubric,
            concept_prerequisites=prereq_map,
            recommended_sequence=sequence,
            gaps=report.unmapped_concepts,
        )
