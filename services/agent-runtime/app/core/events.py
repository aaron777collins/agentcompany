"""Redis pub/sub event bus.

The event bus has two responsibilities:
1. Publishing structured events to a Redis channel so SSE subscribers receive
   them in real time without polling the database.
2. Providing an async generator for SSE endpoints to consume those events.

The bus is intentionally thin — it does not own event persistence.  The API
layer writes event rows to PostgreSQL before publishing here.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)

# Channel naming convention: events:{company_id}
# A wildcard subscription on "events:*" lets the SSE endpoint receive events
# for any company the authenticated user can access.
_CHANNEL_PREFIX = "events"


def _channel_for(company_id: str) -> str:
    return f"{_CHANNEL_PREFIX}:{company_id}"


class EventBus:
    """Thin wrapper around Redis pub/sub.

    One EventBus instance lives on app.state for the lifetime of the process.
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def publish(self, company_id: str, event: dict[str, Any]) -> None:
        """Serialize event to JSON and publish to the company channel."""
        channel = _channel_for(company_id)
        try:
            await self._redis.publish(channel, json.dumps(event, default=str))
        except Exception as exc:
            # Bus failures must never crash the calling API handler — the event
            # row is already persisted to Postgres before we get here.
            logger.warning("Failed to publish event to Redis channel %s: %s", channel, exc)

    async def subscribe(
        self, company_id: str, timeout_seconds: float = 30.0
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield parsed event dicts from the company channel.

        Intended for SSE endpoints.  The generator closes when the client
        disconnects or after `timeout_seconds` of inactivity.
        """
        channel = _channel_for(company_id)
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            while True:
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=timeout_seconds,
                    )
                    if message and message["type"] == "message":
                        yield json.loads(message["data"])
                except asyncio.TimeoutError:
                    # Yield a keepalive comment so the SSE connection stays open
                    yield {"type": "keepalive"}
                except asyncio.CancelledError:
                    break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()


_bus: EventBus | None = None


def init_event_bus(redis: aioredis.Redis) -> EventBus:
    global _bus
    _bus = EventBus(redis)
    return _bus


def get_event_bus() -> EventBus:
    if _bus is None:
        raise RuntimeError("Event bus has not been initialised. Call init_event_bus() first.")
    return _bus
