"""Tests for ``MessageBus`` delivery, RPC, and resilience."""

from __future__ import annotations

import asyncio

import pytest

from core.message_bus import MessageBus
from shared.models import Message


@pytest.mark.asyncio
async def test_publish_subscribe_delivers() -> None:
    """Subscribers receive published messages."""

    bus = MessageBus()
    await bus.start()
    received: list[Message] = []

    async def cb(msg: Message) -> None:
        received.append(msg)

    bus.subscribe("demo.topic", cb)
    message = Message(topic="demo.topic", payload={"hello": "world"}, source_agent="tester")
    published = await bus.publish("demo.topic", message)
    await asyncio.sleep(0.05)
    assert published is True
    assert len(received) == 1
    assert received[0].payload["hello"] == "world"
    await bus.stop()


@pytest.mark.asyncio
async def test_publish_without_subscribers_returns_false() -> None:
    """Publishing with no subscribers reports ``False``."""

    bus = MessageBus()
    await bus.start()
    message = Message(topic="empty.topic", payload={}, source_agent="tester")
    assert await bus.publish("empty.topic", message) is False
    await bus.stop()


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery() -> None:
    """Unsubscribed callbacks must not run."""

    bus = MessageBus()
    await bus.start()
    calls = 0

    async def cb(_: Message) -> None:
        nonlocal calls
        calls += 1

    sub_id = bus.subscribe("volatile", cb)
    assert bus.unsubscribe(sub_id) is True
    await bus.publish("volatile", Message(topic="volatile", payload={}, source_agent="x"))
    await asyncio.sleep(0.05)
    assert calls == 0
    await bus.stop()


@pytest.mark.asyncio
async def test_subscriber_exception_dead_letters() -> None:
    """Failing subscribers populate dead letters without blocking peers."""

    bus = MessageBus()
    await bus.start()
    successes = 0

    async def bad(_: Message) -> None:
        raise RuntimeError("boom")

    async def good(_: Message) -> None:
        nonlocal successes
        successes += 1

    bus.subscribe("multi", bad)
    bus.subscribe("multi", good)
    await bus.publish("multi", Message(topic="multi", payload={}, source_agent="x"))
    await asyncio.sleep(0.05)
    assert successes == 1
    assert bus.dead_letters()
    await bus.stop()


@pytest.mark.asyncio
async def test_publish_wait_rpc_pattern() -> None:
    """``publish_wait`` collects replies routed via correlation id."""

    bus = MessageBus()
    await bus.start()

    async def helper(msg: Message) -> None:
        reply_topic = msg.payload["_reply_topic"]
        response = Message(
            topic=reply_topic,
            payload={"answer": 42},
            source_agent="helper",
            correlation_id=msg.correlation_id,
        )
        await bus.publish(reply_topic, response)

    bus.subscribe("tutorial.agents.helper.help", helper)
    request = Message(
        topic="tutorial.agents.helper.help",
        payload={"problem": {"q": "?"}},
        source_agent="requester",
    )
    responses = await bus.publish_wait("tutorial.agents.helper.help", request, timeout=2.0)
    assert responses
    assert responses[0].payload["answer"] == 42
    await bus.stop()


@pytest.mark.asyncio
async def test_get_stats_reports_metrics() -> None:
    """Statistics aggregate subscriber and delivery counts."""

    bus = MessageBus()
    await bus.start()

    async def cb(_: Message) -> None:
        return None

    bus.subscribe("metrics", cb)
    await bus.publish("metrics", Message(topic="metrics", payload={}, source_agent="m"))
    await asyncio.sleep(0.05)
    stats = bus.get_stats()
    assert stats["subscribers_per_topic"]["metrics"] == 1
    assert stats["publish_count"] >= 1
    await bus.stop()


@pytest.mark.asyncio
async def test_connection_context_manager() -> None:
    """Connection context starts and stops the bus cleanly."""

    bus = MessageBus()
    async with bus.connection():
        assert bus._started is True  # noqa: SLF001 - intentional white-box check
    assert bus._started is False  # noqa: SLF001
