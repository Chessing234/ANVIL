"""Event routing package."""

from events.context import bind_coordinator, clear_coordinator, get_coordinator
from events.handlers import setup_router
from events.router import EventRouter

__all__ = [
    "EventRouter",
    "bind_coordinator",
    "clear_coordinator",
    "get_coordinator",
    "setup_router",
]
