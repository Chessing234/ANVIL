"""Narrative generation agent: investigations become student-led detective stories."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import structlog

from agents.teaching.character_system import CharacterSystem
from agents.teaching.interactive_elements import InteractiveElementsFactory
from agents.teaching.narrative_types import (
    AnyInteractiveElement,
    ConceptMapping,
    NarrativeResult,
    Scene,
    Story,
    StoryArc,
)
from agents.teaching.story_engine import StoryEngine
from agents.teaching.tools.dialogue_generator import DialogueGenerator
from agents.teaching.tools.narrative_templates import infer_incident_category, select_template
from agents.teaching.tools.visual_descriptions import describe_discovery, describe_setting
from config.constants import AgentType, LessonDifficulty
from core.base_agent import BaseAgent
from core.message_bus import MessageBus
from shared.models import Incident, InvestigationStep, StudentProfile

logger = structlog.get_logger(__name__)


def _scene_ids(arc: StoryArc) -> list[str]:
    ids = [arc.setup.id]
    ids.extend(s.id for s in arc.rising_action)
    ids.append(arc.climax.id)
    ids.extend(s.id for s in arc.falling_action)
    ids.append(arc.resolution.id)
    return ids


def _difficulty(profile: StudentProfile) -> LessonDifficulty:
    return {
        "beginner": LessonDifficulty.BEGINNER,
        "intermediate": LessonDifficulty.INTERMEDIATE,
        "advanced": LessonDifficulty.ADVANCED,
        "expert": LessonDifficulty.EXPERT,
    }.get(profile.experience_level.lower(), LessonDifficulty.BEGINNER)


def _simplify_for_beginner(text: str) -> str:
    """Lightweight readability pass without altering technical claims."""

    replacements = {
        r"\bSIEM\b": "security monitoring system (SIEM)",
        r"\bIOC\b": "indicator of compromise (IOC)",
        r"\bC2\b": "command-and-control (C2)",
    }
    out = text
    for pat, rep in replacements.items():
        out = re.sub(pat, rep, out, flags=re.I)
    return out


def _inject_interactives(story: Story, mapping: dict[str, AnyInteractiveElement]) -> Story:
    """Attach interactives to scenes by id."""

    def patch(scene: Scene) -> Scene:
        if scene.id in mapping:
            return scene.model_copy(update={"interactive_element": mapping[scene.id]})
        return scene

    arc = story.arc
    new_arc = StoryArc(
        arc_type=arc.arc_type,
        setup=patch(arc.setup),
        rising_action=[patch(s) for s in arc.rising_action],
        climax=patch(arc.climax),
        falling_action=[patch(s) for s in arc.falling_action],
        resolution=patch(arc.resolution),
    )
    return story.model_copy(update={"arc": new_arc})


def _ensure_terminal_interactives(
    mapping: dict[str, AnyInteractiveElement],
    arc: StoryArc,
    last_step: InvestigationStep | None,
) -> None:
    from agents.teaching.narrative_types import DiscoveryMoment, ReflectionPrompt

    if arc.climax.id not in mapping:
        reveal = last_step.interpretation if last_step and last_step.interpretation else last_step.action_taken if last_step else "The evidence converges."
        mapping[arc.climax.id] = DiscoveryMoment(
            id=f"{arc.climax.id}_discovery",
            build_up="Every prior step narrows the hypothesis space.",
            reveal=str(reveal)[:800],
            technical_explanation=(
                "The climax mirrors the real investigation's decisive finding—wording is grounded in supplied steps, "
                "not fictional exploits."
            ),
            visual_description=describe_discovery(str(reveal)),
            emotional_beat="You trust the process because the artifacts agree.",
        )
    if arc.resolution.id not in mapping:
        mapping[arc.resolution.id] = ReflectionPrompt(
            id=f"{arc.resolution.id}_reflect",
            question="Which control would have detected this incident sooner, and why?",
            guidance="Tie recommendations to evidence types you actually saw.",
            sample_good_answer="Better DNS visibility plus MFA on remote access would have raised earlier alarms.",
            concept_reinforced="defense_in_depth",
        )


def _concept_mappings(story: Story) -> list[ConceptMapping]:
    mappings: list[ConceptMapping] = []
    csta_cycle = ("1B-AP-08", "2-AP-13", "3A-AP-15", "3B-AP-21")

    def consume(scene: Scene) -> None:
        std = csta_cycle[len(mappings) % len(csta_cycle)]
        for concept in scene.concepts_demonstrated:
            mappings.append(
                ConceptMapping(
                    concept_id=concept.id,
                    scene_id=scene.id,
                    interactive_element_id=scene.interactive_element.id if scene.interactive_element else None,
                    csta_standard=std,
                ),
            )

    arc = story.arc
    consume(arc.setup)
    for s in arc.rising_action:
        consume(s)
    consume(arc.climax)
    for s in arc.falling_action:
        consume(s)
    consume(arc.resolution)
    return mappings


def _validate_step_coverage(steps: list[InvestigationStep], story: Story) -> list[str]:
    """Ensure each investigation step id appears in at least one scene."""

    ids = {str(s.id) for s in steps}
    refs: set[str] = set()

    def scan(scene: Scene) -> None:
        if scene.investigation_step_ref:
            refs.add(scene.investigation_step_ref)

    arc = story.arc
    scan(arc.setup)
    for s in arc.rising_action:
        scan(s)
    scan(arc.climax)
    for s in arc.falling_action:
        scan(s)
    scan(arc.resolution)
    missing = sorted(ids - refs)
    if missing:
        logger.error("narrative_missing_step_refs", missing=missing)
    return missing


class NarrativeGenerationAgent(BaseAgent):
    """Transforms investigation steps into interactive, standards-mapped stories."""

    def __init__(
        self,
        message_bus: MessageBus,
        config: dict[str, Any],
        *,
        name: str = "teaching_narrative",
        story_engine: StoryEngine | None = None,
        character_system: CharacterSystem | None = None,
        dialogue: DialogueGenerator | None = None,
    ) -> None:
        super().__init__(name, AgentType.TEACHING_NARRATIVE, message_bus, config)
        dlg = dialogue or DialogueGenerator(llm_complete=config.get("llm_dialogue_callback"))
        self._dialogue = dlg
        self._characters = character_system or CharacterSystem(dlg)
        self._engine = story_engine or StoryEngine()

    async def _run_iteration(self) -> None:
        await asyncio.sleep(0.5)

    async def generate_narrative(
        self,
        investigation_steps: list[InvestigationStep],
        incident: Incident,
        student_profile: StudentProfile,
    ) -> NarrativeResult:
        """Produce a complete ``NarrativeResult`` faithful to the investigation record."""

        template = select_template(infer_incident_category(incident))
        arc = self._engine.create_arc(
            investigation_steps,
            incident,
            student_level=student_profile.experience_level,
            template=template,
        )
        story = self._engine.wrap_story(arc, incident, template)

        scene_ids = _scene_ids(arc)
        factory = InteractiveElementsFactory(student_profile)
        mapping = factory.build_for_investigation(investigation_steps, scene_ids)
        last_step = sorted(investigation_steps, key=lambda s: s.timestamp)[-1] if investigation_steps else None
        _ensure_terminal_interactives(mapping, arc, last_step)
        story = _inject_interactives(story, mapping)

        if student_profile.experience_level.lower() == "beginner":
            arc2 = story.arc

            def soften(scene: Scene) -> Scene:
                return scene.model_copy(update={"narrative_text": _simplify_for_beginner(scene.narrative_text)})

            softened = StoryArc(
                arc_type=arc2.arc_type,
                setup=soften(arc2.setup),
                rising_action=[soften(s) for s in arc2.rising_action],
                climax=soften(arc2.climax),
                falling_action=[soften(s) for s in arc2.falling_action],
                resolution=soften(arc2.resolution),
            )
            story = story.model_copy(update={"arc": softened})

        missing = _validate_step_coverage(investigation_steps, story)
        if missing:
            logger.warning("narrative_step_coverage_gaps", missing=missing)

        interactives = factory.collect_flat_ordered(mapping, _scene_ids(story.arc))
        concepts = _concept_mappings(story)
        duration = min(600, max(12, len(investigation_steps) * 4 + 18))

        teacher_notes = (
            f"Run this case as a jigsaw: groups own different investigation steps, then debrief. "
            f"Highlight that scenes marked checkpoint gate progress. "
            f"Setting visualization cue: {describe_setting(story.arc.setup.setting)[:400]}..."
        )

        cast = self._characters.build_default_cast(student_profile)
        mentor = next(c for c in cast if c.id == "lead_analyst")
        dialogue_block = await self._dialogue.generate_dialogue(
            mentor,
            story.arc.setup,
            {"student_level": student_profile.experience_level, "incident_id": str(incident.id)},
        )
        teacher_notes += f"\n\nSample mentor dialogue bundle:\n{dialogue_block[:1500]}"

        title = template.title if template.title.startswith("The ") else f"The Case of {template.title}"
        return NarrativeResult(
            title=title,
            story=story,
            interactive_elements=interactives,
            concepts_taught=concepts,
            estimated_duration_minutes=duration,
            difficulty_level=_difficulty(student_profile),
            csta_standards=list(template.csta_standards),
            teacher_notes=teacher_notes,
        )
