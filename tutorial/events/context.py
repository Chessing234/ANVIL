"""Coordinator binding for event handlers (avoids circular imports)."""

from __future__ import annotations

from typing import Any, Protocol


class CoordinatorProtocol(Protocol):
    """Minimal coordinator surface required by event handlers."""

    async def submit_incident(self, incident: Any) -> Any:
        """Submit a defense workflow."""

    async def submit_lesson_request(self, incident_id: str, student_profile: Any) -> Any:
        """Submit a teaching workflow."""

    async def record_investigation_started(self, incident_id: str) -> None:
        """Mark investigation phase."""

    async def record_evidence(self, payload: dict[str, Any]) -> None:
        """Persist evidence metadata."""

    async def record_containment(self, payload: dict[str, Any]) -> None:
        """Record containment execution."""

    async def handle_lesson_generated_event(self, payload: dict[str, Any]) -> None:
        """Process lesson generated notifications."""

    async def handle_lesson_completed_event(self, payload: dict[str, Any]) -> None:
        """Process lesson completion."""

    async def handle_agent_error_event(self, payload: dict[str, Any]) -> None:
        """Escalate agent failures."""

    async def record_system_heartbeat(self, payload: dict[str, Any]) -> None:
        """Update heartbeat aggregates."""


_bound: CoordinatorProtocol | None = None


def bind_coordinator(coordinator: CoordinatorProtocol) -> None:
    """Attach the active coordinator for handler callbacks."""

    global _bound
    _bound = coordinator


def get_coordinator() -> CoordinatorProtocol:
    """Return the bound coordinator."""

    if _bound is None:
        raise RuntimeError("coordinator not bound; call bind_coordinator first")
    return _bound


def clear_coordinator() -> None:
    """Remove coordinator binding (mainly for tests)."""

    global _bound
    _bound = None
