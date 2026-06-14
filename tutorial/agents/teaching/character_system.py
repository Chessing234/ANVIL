"""Cast creation and dialogue scaffolding for teaching narratives."""

from __future__ import annotations

from collections.abc import Sequence

from agents.teaching.narrative_types import Character, Scene
from agents.teaching.tools.dialogue_generator import DialogueGenerator
from shared.models import StudentProfile


class CharacterSystem:
    """Builds default personas and assigns them across scenes."""

    def __init__(self, dialogue: DialogueGenerator | None = None) -> None:
        self._dialogue = dialogue or DialogueGenerator()

    def build_default_cast(self, student: StudentProfile) -> list[Character]:
        """Return the core cast with the student as lead detective."""

        player = Character(
            id="student_detective",
            name=student.name,
            role="lead_detective",
            personality="curious, asks clarifying questions, documents every inference",
            knowledge_level="peer" if student.experience_level in ("intermediate", "advanced") else "novice",
            dialogue_style=student.preferred_learning_style,
            avatar_description=f"Student detective avatar for {student.name}",
        )
        mentor = Character(
            id="lead_analyst",
            name="Jordan Okonkwo",
            role="mentor",
            personality="encouraging expert who never blames the learner for mistakes",
            knowledge_level="expert",
            dialogue_style="warm_professional",
            avatar_description="SOC mentor with annotated whiteboard",
        )
        iris = Character(
            id="investigation_agent",
            name="IRIS",
            role="guide",
            personality="transparent AI analyst referencing real tool outputs",
            knowledge_level="expert",
            dialogue_style="technical_plain_language",
            avatar_description="holographic assistant with timeline glyphs",
        )
        admin = Character(
            id="system_admin",
            name="Priya Nandakumar",
            role="peer",
            personality="pragmatic IT lead who escalated the alert",
            knowledge_level="peer",
            dialogue_style="casual",
            avatar_description="IT staff badge and tablet with ticket queue",
        )
        threat = Character(
            id="threat_actor",
            name="Unknown adversary",
            role="suspect",
            personality="represented only through malware behaviors—never glorified",
            knowledge_level="expert",
            dialogue_style="ominous_third_person",
            avatar_description="silhouetted figure composed of log lines and packet diagrams",
        )
        return [player, mentor, iris, admin, threat]

    async def enrich_scenes_with_dialogue(
        self,
        scenes: Sequence[Scene],
        student: StudentProfile,
        context: dict[str, str],
    ) -> list[str]:
        """Generate one dialogue block per scene for the primary mentor."""

        lines: list[str] = []
        mentor = next((c for c in self.build_default_cast(student) if c.id == "lead_analyst"), None)
        if mentor is None:
            return lines
        for scene in scenes:
            block = await self._dialogue.generate_dialogue(mentor, scene, context)
            lines.append(block)
        return lines
