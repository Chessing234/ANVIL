"""Pydantic types for interactive teaching narratives derived from investigations."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from config.constants import LessonDifficulty


class Concept(BaseModel):
    """Single cybersecurity concept demonstrated in a scene."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)


class ConceptMapping(BaseModel):
    """Maps a concept to where it appears in the narrative."""

    model_config = {"extra": "forbid"}

    concept_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    interactive_element_id: str | None = Field(default=None, max_length=64)
    csta_standard: str = Field(min_length=1, max_length=32)


class Setting(BaseModel):
    """Where and when a scene takes place."""

    model_config = {"extra": "forbid"}

    location: str = Field(min_length=1, max_length=500)
    time_description: str = Field(min_length=1, max_length=500)
    mood: str = Field(default="tense", min_length=1, max_length=120)
    props: list[str] = Field(default_factory=list)


class Character(BaseModel):
    """A persona in the teaching story."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=64)
    personality: str = Field(min_length=1, max_length=500)
    knowledge_level: str = Field(pattern="^(expert|peer|novice)$")
    dialogue_style: str = Field(min_length=1, max_length=120)
    avatar_description: str = Field(min_length=1, max_length=500)


class Choice(BaseModel):
    """One option at a choice point."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=1000)


class InteractiveElement(BaseModel):
    """Base interactive learning element (discriminated by ``kind``)."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=64)
    kind: str = Field(min_length=1, max_length=32)


class ChoicePoint(InteractiveElement):
    """Branching decision for the student detective."""

    kind: Literal["choice_point"] = "choice_point"
    question: str = Field(min_length=1, max_length=1000)
    choices: list[Choice] = Field(min_length=2)
    correct_choice_id: str = Field(min_length=1)
    explanation_correct: str = Field(min_length=1, max_length=4000)
    explanation_incorrect: dict[str, str] = Field(default_factory=dict)
    concept_tested: str = Field(min_length=1, max_length=200)


class PuzzleType(StrEnum):
    LOG_ANALYSIS = "log_analysis"
    NETWORK_DECODE = "network_decode"
    MALWARE_IDENTIFICATION = "malware_identification"
    MEMORY_ARTIFACT = "memory_artifact"
    GENERIC = "generic"


class Puzzle(InteractiveElement):
    """Hands-on analytic puzzle."""

    kind: Literal["puzzle"] = "puzzle"
    puzzle_type: PuzzleType
    description: str = Field(min_length=1, max_length=4000)
    data_provided: str = Field(min_length=1, max_length=20_000)
    solution: str = Field(min_length=1, max_length=2000)
    hints: list[str] = Field(default_factory=list)
    expected_answer: str = Field(min_length=1, max_length=500)
    validation_logic: str = Field(min_length=1, max_length=2000)


class DiscoveryMoment(InteractiveElement):
    """Dramatic reveal aligned with a real finding."""

    kind: Literal["discovery_moment"] = "discovery_moment"
    build_up: str = Field(min_length=1, max_length=4000)
    reveal: str = Field(min_length=1, max_length=4000)
    technical_explanation: str = Field(min_length=1, max_length=6000)
    visual_description: str = Field(min_length=1, max_length=4000)
    emotional_beat: str = Field(min_length=1, max_length=2000)


class ReflectionPrompt(InteractiveElement):
    """Metacognitive reflection."""

    kind: Literal["reflection_prompt"] = "reflection_prompt"
    question: str = Field(min_length=1, max_length=2000)
    guidance: str = Field(min_length=1, max_length=4000)
    sample_good_answer: str = Field(min_length=1, max_length=4000)
    concept_reinforced: str = Field(min_length=1, max_length=200)


AnyInteractiveElement = Annotated[
    Union[ChoicePoint, Puzzle, DiscoveryMoment, ReflectionPrompt],
    Field(discriminator="kind"),
]


class Scene(BaseModel):
    """One story beat linked to investigation reality."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    narrative_text: str = Field(min_length=1, max_length=20_000)
    setting: Setting
    characters_present: list[Character] = Field(default_factory=list)
    investigation_step_ref: str | None = Field(default=None, max_length=64)
    concepts_demonstrated: list[Concept] = Field(default_factory=list)
    interactive_element: AnyInteractiveElement | None = None
    next_scenes: list[str] = Field(default_factory=list)
    is_checkpoint: bool = False


class StoryArcType(StrEnum):
    MYSTERY = "mystery"
    RACING_CLOCK = "racing_clock"
    DEEP_DIVE = "deep_dive"
    WHODUNIT = "whodunit"


class StoryArc(BaseModel):
    """Five-part arc mapping investigation phases to story structure."""

    model_config = {"extra": "forbid"}

    arc_type: StoryArcType
    setup: Scene
    rising_action: list[Scene] = Field(default_factory=list)
    climax: Scene
    falling_action: list[Scene] = Field(default_factory=list)
    resolution: Scene


class Story(BaseModel):
    """Complete narrative package."""

    model_config = {"extra": "forbid"}

    arc: StoryArc
    synopsis: str = Field(min_length=1, max_length=4000)
    detective_hook: str = Field(min_length=1, max_length=2000)


class NarrativeResult(BaseModel):
    """Generated lesson narrative from a real investigation."""

    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=500)
    story: Story
    interactive_elements: list[AnyInteractiveElement] = Field(default_factory=list)
    concepts_taught: list[ConceptMapping] = Field(default_factory=list)
    estimated_duration_minutes: int = Field(ge=1, le=600)
    difficulty_level: LessonDifficulty
    csta_standards: list[str] = Field(default_factory=list)
    teacher_notes: str = Field(min_length=1, max_length=20_000)
