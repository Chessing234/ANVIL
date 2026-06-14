"""Event router with latency tracking and safe dispatch."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from config.constants import EventType
from shared.models import Message

logger = structlog.get_logger(__name__)

EventHandler = Callable[[Message], Awaitable[None]]


class EventRouter:
    """Maps ``EventType`` values to async handlers with observability."""

    def __init__(self) -> None:
        self._routes: dict[EventType, EventHandler] = {}
        self._default: EventHandler | None = None
        self._stats: dict[str, dict[str, Any]] = {}

    def register(self, event_type: EventType, handler: EventHandler) -> None:
        """Bind ``handler`` to ``event_type``."""

        self._routes[event_type] = handler
        self._stats.setdefault(handler.__name__, {"calls": 0, "errors": 0, "latency_total_ms": 0.0})

    def register_default(self, handler: EventHandler) -> None:
        """Register fallback handler."""

        self._default = handler
        self._stats.setdefault(handler.__name__, {"calls": 0, "errors": 0, "latency_total_ms": 0.0})

    def get_routing_table(self) -> dict[str, str]:
        """Return human-readable routing map."""

        table = {event.value: handler.__name__ for event, handler in self._routes.items()}
        if self._default:
            table["__default__"] = self._default.__name__
        return table

    def get_handler_stats(self) -> dict[str, dict[str, Any]]:
        """Return call counts and latency aggregates."""

        result: dict[str, dict[str, Any]] = {}
        for name, raw in self._stats.items():
            calls = int(raw["calls"])
            errors = int(raw["errors"])
            total_ms = float(raw["latency_total_ms"])
            avg = total_ms / calls if calls else 0.0
            result[name] = {
                "calls": calls,
                "errors": errors,
                "avg_latency_ms": round(avg, 4),
            }
        return result

    async def route(self, message: Message) -> None:
        """Dispatch ``message`` to the correct handler."""

        event_value = message.payload.get("event")
        try:
            event_type = EventType(str(event_value))
        except ValueError:
            event_type = None
        handler = self._routes.get(event_type, self._default)
        if handler is None:
            logger.warning("event_router_no_handler", event=event_value)
            return
        name = handler.__name__
        self._stats.setdefault(name, {"calls": 0, "errors": 0, "latency_total_ms": 0.0})
        start = time.perf_counter()
        try:
            await handler(message)
        except Exception as exc:  # pragma: no cover - exercised via tests
            self._stats[name]["errors"] += 1
            logger.error("event_router_handler_failed", handler=name, error=str(exc))
            raise
        else:
            self._stats[name]["calls"] += 1
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._stats[name]["latency_total_ms"] += elapsed_ms
