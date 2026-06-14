"""Shared type aliases, protocols, and generic variables."""

from __future__ import annotations

from typing import Any, Protocol, TypeVar

JsonDict = dict[str, Any]
AgentConfig = dict[str, Any]
IncidentId = str
LessonId = str

StateT = TypeVar("StateT")


class InvestigativeAgent(Protocol):
    """Agents capable of handling incident investigations."""

    name: str

    async def analyze(self, incident_id: IncidentId) -> JsonDict:
        """Perform investigative reasoning for an incident."""


class TeachingAgent(Protocol):
    """Agents capable of synthesizing lessons."""

    name: str

    async def build_lesson(self, incident_id: IncidentId) -> LessonId:
        """Create a lesson anchored to an incident."""
