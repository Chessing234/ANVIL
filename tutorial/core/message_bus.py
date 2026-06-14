"""Async in-memory pub/sub message bus with TTL tracking and dead-letter handling."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from uuid import UUID

from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from shared.models import Message

logger = structlog.get_logger(__name__)

Subscriber = Callable[[Message], Awaitable[None]]

_MAX_DLQ = 1000


@dataclass
class DeadLetterEntry:
    """Record for a failed subscriber delivery."""

    topic: str
    subscription_id: str
    error: str
    message: Message
    failed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MessageBus:
    """Async singleton-style message bus with pub/sub and lightweight RPC.

    The bus routes messages to subscribers concurrently, captures failures in a
    dead-letter buffer, and exposes operational statistics for observability.
    """

    _instance: MessageBus | None = None
    _instance_lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, max_queue_size: int = 10_000, message_ttl_seconds: int = 3600) -> None:
        self._max_queue_size = max_queue_size
        self._message_ttl_seconds = message_ttl_seconds
        self._topics: dict[str, dict[str, Subscriber]] = defaultdict(dict)
        self._lock = asyncio.Lock()
        self._started = False
        self._stop_event = asyncio.Event()
        self._ttl_task: asyncio.Task[None] | None = None
        self._messages_processed = 0
        self._publish_count = 0
        self._errors = 0
        self._dead_letters: deque[DeadLetterEntry] = deque(maxlen=_MAX_DLQ)
        self._queued_metadata: deque[tuple[datetime, UUID]] = deque(maxlen=max_queue_size)

    @classmethod
    async def get_instance(
        cls,
        max_queue_size: int = 10_000,
        message_ttl_seconds: int = 3600,
    ) -> MessageBus:
        """Return the shared bus instance, constructing it on first use.

        Args:
            max_queue_size: Upper bound for retained message metadata.
            message_ttl_seconds: TTL applied to retained message metadata.

        Returns:
            Initialized ``MessageBus`` singleton.
        """

        async with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(
                    max_queue_size=max_queue_size,
                    message_ttl_seconds=message_ttl_seconds,
                )
                await cls._instance.start()
            return cls._instance

    @classmethod
    async def reset_instance(cls) -> None:
        """Tear down singleton for tests."""

        async with cls._instance_lock:
            if cls._instance is not None:
                await cls._instance.stop()
                cls._instance = None

    @asynccontextmanager
    async def connection(self) -> Iterator[MessageBus]:
        """Context manager ensuring clean startup and shutdown.

        Yields:
            Active ``MessageBus`` instance.
        """

        await self.start()
        try:
            yield self
        finally:
            await self.stop()

    async def start(self) -> None:
        """Start background maintenance tasks."""

        async with self._lock:
            if self._started:
                return
            self._started = True
            self._stop_event.clear()
            self._ttl_task = asyncio.create_task(self._ttl_cleanup_loop(), name="message-bus-ttl")

    async def stop(self) -> None:
        """Cancel background tasks and mark the bus as stopped."""

        async with self._lock:
            if not self._started:
                return
            self._started = False
            self._stop_event.set()
            if self._ttl_task is not None:
                self._ttl_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._ttl_task
                self._ttl_task = None

    def subscribe(self, topic: str, callback: Subscriber) -> str:
        """Register a subscriber on ``topic``.

        Args:
            topic: Topic channel name.
            callback: Async function invoked for each message.

        Returns:
            Opaque subscription identifier used for ``unsubscribe``.
        """

        subscription_id = str(uuid.uuid4())
        self._topics[topic][subscription_id] = callback
        logger.info("message_bus_subscribed", topic=topic, subscription_id=subscription_id)
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscriber by identifier.

        Args:
            subscription_id: Identifier returned from ``subscribe``.

        Returns:
            True if a subscription was removed.
        """

        removed = False
        for topic, subscribers in self._topics.items():
            if subscription_id in subscribers:
                subscribers.pop(subscription_id, None)
                removed = True
                logger.info(
                    "message_bus_unsubscribed",
                    topic=topic,
                    subscription_id=subscription_id,
                )
                if not subscribers:
                    del self._topics[topic]
                break
        return removed

    async def publish(self, topic: str, message: Message) -> bool:
        """Publish ``message`` to all subscribers of ``topic``.

        Args:
            topic: Destination topic.
            message: Payload envelope.

        Returns:
            True if at least one subscriber received a delivery attempt.
        """

        async with self._lock:
            self._publish_count += 1
            self._queued_metadata.append(
                (datetime.now(timezone.utc) + self._ttl_delta(), message.id),
            )

        subscribers = list(self._topics.get(topic, {}).items())
        if not subscribers:
            logger.debug("message_bus_no_subscribers", topic=topic, message_id=str(message.id))
            return False

        await asyncio.gather(
            *[
                self._safe_deliver(sub_id, topic, callback, message)
                for sub_id, callback in subscribers
            ],
        )
        return True

    async def publish_wait(
        self,
        topic: str,
        message: Message,
        timeout: float = 30.0,
    ) -> list[Message]:
        """Publish and collect replies sent to the implicit reply topic.

        Args:
            topic: Primary topic for the request.
            message: Initial message; correlation id groups replies.
            timeout: Maximum time to wait for replies.

        Returns:
            List of response messages (possibly empty on timeout).
        """

        reply_topic = f"tutorial.rpc.reply.{message.correlation_id}"
        responses: list[Message] = []
        queue: asyncio.Queue[Message] = asyncio.Queue()

        async def _collector(msg: Message) -> None:
            await queue.put(msg)

        sub_id = self.subscribe(reply_topic, _collector)
        try:
            enriched_payload = {
                **message.payload,
                "_reply_topic": reply_topic,
            }
            outbound = message.model_copy(update={"payload": enriched_payload})
            await self.publish(topic, outbound)
            deadline = asyncio.get_running_loop().time() + timeout
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=remaining)
                    responses.append(item)
                except asyncio.TimeoutError:
                    break
        finally:
            self.unsubscribe(sub_id)
        return responses

    def get_stats(self) -> dict[str, Any]:
        """Return lightweight operational statistics."""

        subscribers_per_topic = {topic: len(subs) for topic, subs in self._topics.items()}
        return {
            "subscribers_per_topic": subscribers_per_topic,
            "messages_processed": self._messages_processed,
            "errors": self._errors,
            "publish_count": self._publish_count,
            "dead_letter_count": len(self._dead_letters),
            "retained_metadata": len(self._queued_metadata),
        }

    def dead_letters(self) -> list[DeadLetterEntry]:
        """Return a snapshot of dead-letter records for diagnostics."""

        return list(self._dead_letters)

    def _ttl_delta(self) -> timedelta:
        """Return TTL span for retained message metadata."""

        return timedelta(seconds=self._message_ttl_seconds)

    async def _ttl_cleanup_loop(self) -> None:
        """Expire retained metadata according to ``message_ttl_seconds``."""

        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(1.0)
                now = datetime.now(timezone.utc)
                while self._queued_metadata and self._queued_metadata[0][0] < now:
                    self._queued_metadata.popleft()
        except asyncio.CancelledError:
            logger.info("message_bus_ttl_cancelled")
            raise

    async def _safe_deliver(
        self,
        subscription_id: str,
        topic: str,
        callback: Subscriber,
        message: Message,
    ) -> None:
        """Deliver to a single subscriber without impacting peers."""

        try:
            await callback(message)
            self._messages_processed += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - broad by design
            self._errors += 1
            entry = DeadLetterEntry(
                topic=topic,
                subscription_id=subscription_id,
                error=str(exc),
                message=message,
            )
            self._dead_letters.append(entry)
            logger.error(
                "message_bus_delivery_failed",
                topic=topic,
                subscription_id=subscription_id,
                error=str(exc),
            )


async def get_message_bus(
    max_queue_size: int = 10_000,
    message_ttl_seconds: int = 3600,
) -> MessageBus:
    """Module-level helper returning the async singleton bus."""

    return await MessageBus.get_instance(
        max_queue_size=max_queue_size,
        message_ttl_seconds=message_ttl_seconds,
    )
