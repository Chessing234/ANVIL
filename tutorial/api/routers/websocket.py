"""WebSocket fan-out for live dashboards."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState

from config.constants import MessageBusTopics
from core.message_bus import MessageBus
from shared.models import Message

router = APIRouter()

_TOPIC_EVENTS: dict[str, str] = {
    MessageBusTopics.INCIDENTS: "incident_update",
    MessageBusTopics.INVESTIGATIONS: "investigation_step",
    MessageBusTopics.EVIDENCE: "investigation_step",
    MessageBusTopics.LESSONS: "lesson_generated",
    MessageBusTopics.AGENTS: "agent_status",
    MessageBusTopics.SYSTEM: "system_heartbeat",
}


def _serialize_bus_message(topic: str, msg: Message) -> dict[str, object]:
    """Map bus traffic to dashboard-friendly envelopes."""
    event = _TOPIC_EVENTS.get(topic, "bus_event")
    payload = msg.payload if isinstance(msg.payload, dict) else {}
    if "event" in payload:
        event = str(payload["event"])
    return {
        "event": event,
        "topic": topic,
        "data": msg.model_dump(mode="json"),
    }


@router.websocket("/events")
async def event_websocket(websocket: WebSocket) -> None:
    """Stream bus events and synthetic heartbeats to the browser client."""
    settings = websocket.app.state.settings
    if websocket.query_params.get("api_key") != settings.api.demo_api_key:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    bus: MessageBus = websocket.app.state.message_bus
    await websocket.accept()

    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=512)

    def make_handler(topic: str):
        async def forward(msg: Message) -> None:
            try:
                await queue.put(_serialize_bus_message(topic, msg))
            except asyncio.QueueFull:
                return

        return forward

    sub_ids: list[str] = []
    for topic in (
        MessageBusTopics.INCIDENTS,
        MessageBusTopics.INVESTIGATIONS,
        MessageBusTopics.EVIDENCE,
        MessageBusTopics.LESSONS,
        MessageBusTopics.AGENTS,
        MessageBusTopics.SYSTEM,
    ):
        sub_ids.append(bus.subscribe(topic, make_handler(topic)))

    try:
        while True:
            try:
                outgoing = await asyncio.wait_for(queue.get(), timeout=settings.api.ws_poll_seconds)
            except asyncio.TimeoutError:
                outgoing = {
                    "event": "system_heartbeat",
                    "topic": MessageBusTopics.SYSTEM,
                    "data": {"timestamp": datetime.now(timezone.utc).isoformat(), "keepalive": True},
                }
            try:
                await websocket.send_json(outgoing)
            except (WebSocketDisconnect, RuntimeError):
                break
    finally:
        for sid in sub_ids:
            bus.unsubscribe(sid)
        if websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(RuntimeError):
                await websocket.close()
