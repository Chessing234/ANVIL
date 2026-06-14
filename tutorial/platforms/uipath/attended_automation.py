"""Attended automation hooks for UiPath Assistant (non-blocking analyst UX)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from shared.models import Lesson


class ContainmentAction(BaseModel):
    """Analyst-facing containment decision payload (UiPath Assistant card)."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    requires_human_approval: bool = True
    incident_id: str = ""


@dataclass
class AssistantSurface:
    """In-memory stand-in for UiPath Assistant UI channels (tests + demos)."""

    investigation_cards: list[dict[str, Any]] = field(default_factory=list)
    approval_prompts: list[dict[str, Any]] = field(default_factory=list)
    lesson_previews: list[dict[str, Any]] = field(default_factory=list)
    dashboard_frames: list[dict[str, Any]] = field(default_factory=list)


class AttendedAutomation:
    """Async-friendly Assistant operations; heavy UI work is offloaded to tasks."""

    def __init__(self) -> None:
        self._surface = AssistantSurface()
        self._approval_handler: Callable[[ContainmentAction], Awaitable[bool]] | None = None
        self._lock = asyncio.Lock()

    def set_approval_handler(self, handler: Callable[[ContainmentAction], Awaitable[bool]]) -> None:
        """Register analyst decision handler (defaults to safe deny for destructive ops)."""

        self._approval_handler = handler

    async def show_investigation_summary(self, incident_id: str) -> None:
        """Push investigation summary to Assistant (non-blocking)."""

        card = {
            "type": "investigation_summary",
            "incident_id": incident_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        async def _push() -> None:
            async with self._lock:
                self._surface.investigation_cards.append(card)

        asyncio.create_task(_push())
        await asyncio.sleep(0)

    async def prompt_for_approval(self, action: ContainmentAction) -> bool:
        """Ask analyst for approval; bounded wait when a handler is installed."""

        if self._approval_handler is not None:
            return await asyncio.wait_for(self._approval_handler(action), timeout=300.0)
        if action.requires_human_approval and any(
            x in action.name.lower() for x in ("isolate", "wipe", "delete", "block")
        ):
            return False
        return True

    async def display_lesson_preview(self, lesson: Lesson) -> None:
        """Render lesson preview card for instructor review."""

        preview = {
            "lesson_id": str(lesson.id),
            "title": lesson.title,
            "difficulty": lesson.difficulty.value,
            "standards": lesson.csta_standards[:10],
        }

        async def _push() -> None:
            async with self._lock:
                self._surface.lesson_previews.append(preview)

        asyncio.create_task(_push())
        await asyncio.sleep(0)

    async def show_realtime_dashboard(self) -> None:
        """Refresh live SOC metrics frame in Assistant."""

        frame = {"type": "soc_dashboard", "generated": datetime.now(timezone.utc).isoformat()}

        async def _push() -> None:
            async with self._lock:
                self._surface.dashboard_frames.append(frame)

        asyncio.create_task(_push())
        await asyncio.sleep(0)

    def assistant_snapshot(self) -> AssistantSurface:
        """Return Assistant channel buffers (for tests and Maestro callbacks)."""

        return self._surface
