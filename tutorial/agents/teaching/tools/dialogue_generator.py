"""Dialogue generation with optional MCP-backed LLM and deterministic pedagogy fallback."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

import structlog

from agents.teaching.narrative_types import Character, Scene

logger = structlog.get_logger(__name__)

LLMCallback = Callable[[str], Awaitable[str | None]]


class DialogueGenerator:
    """Produces in-character lines grounded in the scene and investigation context."""

    def __init__(self, llm_complete: LLMCallback | None = None) -> None:
        self._llm = llm_complete

    def _fallback(self, character: Character, scene: Scene, context: dict[str, Any]) -> str:
        level = str(context.get("student_level", "beginner"))
        step_ref = scene.investigation_step_ref or "general triage"
        opener = {
            "formal": "Let us proceed methodically.",
            "casual": "Alright, let's untangle this together.",
            "visual": "Picture the timeline on the wall—each dot is evidence.",
            "auditory": "Listen for the pattern in these alerts—they tell a story.",
            "kinesthetic": "Trace the attack path with me, step by step.",
        }.get(character.dialogue_style.lower(), "Let's stay evidence-first.")
        body = (
            f"{character.name} ({character.role}): {opener} "
            f"In “{scene.title}”, we stay faithful to investigation step {step_ref}. "
            f"Key idea: {scene.narrative_text[:320].strip()}..."
        )
        if character.knowledge_level == "expert" and level == "beginner":
            body += " I'll define jargon the moment we use it."
        if character.id == "investigation_agent":
            body += " My conclusions mirror the SOC record—no invented exploits."
        alts = [
            body,
            body + " What assumption are you willing to challenge?",
            body + " Which artifact would you inspect next, and why?",
        ]
        return "\n---\n".join(alts[:3])

    async def generate_dialogue(self, character: Character, scene: Scene, context: dict[str, Any]) -> str:
        """Return 2–3 dialogue variations for the character in this scene."""

        prompt = json.dumps(
            {
                "task": "teaching_dialogue",
                "character": character.model_dump(),
                "scene_title": scene.title,
                "scene_excerpt": scene.narrative_text[:1200],
                "context": context,
            },
            default=str,
        )
        if self._llm is not None:
            try:
                out = await self._llm(prompt)
                if out and len(out.strip()) > 40:
                    return out.strip()
            except Exception as exc:
                logger.warning("dialogue_llm_failed", error=str(exc))
        return self._fallback(character, scene, context)
