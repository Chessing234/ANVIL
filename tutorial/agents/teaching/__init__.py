"""Teaching cluster: narrative generation and lesson scaffolding."""

from agents.teaching.character_system import CharacterSystem
from agents.teaching.curriculum_integration import CurriculumIntegrationAgent
from agents.teaching.interactive_elements import InteractiveElementsFactory
from agents.teaching.narrative_generation import NarrativeGenerationAgent
from agents.teaching.narrative_types import (
    Character,
    Choice,
    ChoicePoint,
    Concept,
    ConceptMapping,
    DiscoveryMoment,
    NarrativeResult,
    Puzzle,
    PuzzleType,
    ReflectionPrompt,
    Scene,
    Setting,
    Story,
    StoryArc,
    StoryArcType,
)
from agents.teaching.personalization import PersonalizationEngine
from agents.teaching.sandbox_generation import SandboxGenerationAgent
from agents.teaching.story_engine import StoryEngine
from agents.teaching.tools.dialogue_generator import DialogueGenerator

__all__ = [
    "Character",
    "CharacterSystem",
    "Choice",
    "ChoicePoint",
    "Concept",
    "ConceptMapping",
    "CurriculumIntegrationAgent",
    "DialogueGenerator",
    "DiscoveryMoment",
    "InteractiveElementsFactory",
    "NarrativeGenerationAgent",
    "NarrativeResult",
    "PersonalizationEngine",
    "Puzzle",
    "PuzzleType",
    "ReflectionPrompt",
    "SandboxGenerationAgent",
    "Scene",
    "Setting",
    "Story",
    "StoryArc",
    "StoryArcType",
    "StoryEngine",
]
