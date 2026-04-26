"""
TriggerConsumer — reads from the Redis Stream that HeartbeatService writes to
and dispatches trigger messages to the agent engine.

HeartbeatService enqueues all triggers (ticks, manual, event-routed) to the
global stream key ``triggers:all``.  This consumer reads that stream via a
Redis consumer group so each message is processed exactly once even when
multiple service instances run (horizontal scale-out).

Consumer group: ``agent_triggers``
Stream key:     ``triggers:all``  (HeartbeatService.GLOBAL_STREAM)

Each iteration tries to read up to 10 messages, blocking for up to 5 s if
the stream is empty.  On success the message is acknowledged immediately so
no redelivery occurs.  Failures are logged but do not kill the loop — a
single bad message should not stop the entire consumer.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from redis.asyncio import Redis

from app.engine.heartbeat import TriggerMessage

logger = logging.getLogger(__name__)

# Must match HeartbeatService.GLOBAL_STREAM
_GLOBAL_STREAM = "triggers:all"
_CONSUMER_GROUP = "agent_triggers"


class TriggerConsumer:
    """
    Consumes trigger messages from the Redis Stream and dispatches them to
    the AgentEngineService for execution.

    Each TriggerMessage was written by HeartbeatService._enqueue_trigger and
    contains the agent_id and a fully-typed payload.  The consumer only needs
    to route — it does not decide whether the agent *should* run; that is the
    engine's responsibility.
    """

    def __init__(
        self,
        redis: Redis,
        engine_service: Any,  # AgentEngineService
        stream_key: str = _GLOBAL_STREAM,
    ) -> None:
        if not stream_key:
            raise ValueError("stream_key must not be empty")
        self._redis = redis
        self._engine = engine_service
        self._stream_key = stream_key
        self._consumer_group = _CONSUMER_GROUP
        # Unique consumer name within the group; avoids collisions when multiple
        # instances of this service run behind the same Redis.
        self._consumer_name = f"consumer_{id(self)}"
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """
        Start consuming.  Idempotent — calling start() on an already-running
        consumer is a no-op.
        """
        if self._running:
            return

        # Create the consumer group if it does not exist yet.
        # mkstream=True creates the stream itself if it is absent, so the
        # service can start before any triggers have been enqueued.
        try:
            await self._redis.xgroup_create(
                self._stream_key,
                self._consumer_group,
                id="0",
                mkstream=True,
            )
            logger.debug(
                "Created consumer group '%s' on stream '%s'",
                self._consumer_group,
                self._stream_key,
            )
        except Exception:
            # BUSYGROUP is the Redis error when the group already exists; we
            # intentionally swallow all exceptions here so startup is idempotent.
            pass

        self._running = True
        self._task = asyncio.create_task(
            self._consume_loop(),
            name="trigger_consumer_loop",
        )
        logger.info(
            "TriggerConsumer started (stream=%s group=%s consumer=%s)",
            self._stream_key,
            self._consumer_group,
            self._consumer_name,
        )

    async def stop(self) -> None:
        """Gracefully stop the consumer loop, waiting for the current batch."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TriggerConsumer stopped")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _consume_loop(self) -> None:
        """
        Main loop: read batches of up to 10 messages, handle each one, then
        acknowledge so they are not redelivered.

        Uses ">" as the message ID to only request messages that have not
        yet been delivered to any consumer in the group.
        """
        while self._running:
            try:
                messages = await self._redis.xreadgroup(
                    groupname=self._consumer_group,
                    consumername=self._consumer_name,
                    streams={self._stream_key: ">"},
                    count=10,
                    block=5000,  # 5 s long-poll; avoids tight CPU spin
                )

                if not messages:
                    continue

                for _stream, entries in messages:
                    for msg_id, raw_data in entries:
                        await self._handle_message(msg_id, raw_data)

            except asyncio.CancelledError:
                # Propagate so stop() can await the task cleanly
                raise
            except Exception as exc:
                logger.error(
                    "TriggerConsumer loop error (will retry in 1s): %s",
                    exc,
                    exc_info=True,
                )
                # Brief back-off so we don't hammer Redis on persistent errors
                await asyncio.sleep(1)

    async def _handle_message(
        self,
        msg_id: bytes | str,
        raw_data: dict,
    ) -> None:
        """
        Decode one Redis Streams entry, dispatch it, then acknowledge.

        Acknowledgement happens after dispatch so a crash before ack results
        in redelivery rather than silent loss.  The engine is expected to be
        idempotent on duplicate trigger_ids.
        """
        # Redis may return keys/values as bytes or str depending on whether
        # decode_responses was set on the client.
        data: dict[str, str] = {
            (k.decode() if isinstance(k, bytes) else k): (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in raw_data.items()
        }

        try:
            trigger = TriggerMessage.from_redis_dict(data)
        except (KeyError, ValueError) as exc:
            logger.warning(
                "Skipping malformed trigger message %s: %s",
                msg_id,
                exc,
            )
            # Ack the bad message so it is not endlessly redelivered
            await self._ack(msg_id)
            return

        logger.debug(
            "Dispatching trigger %s for agent %s (type=%s)",
            trigger.trigger_id,
            trigger.agent_id,
            trigger.trigger_type,
        )

        try:
            await self._engine.dispatch_trigger(trigger)
        except Exception as exc:
            # Log and ack rather than crashing the loop; a trigger that
            # repeatedly fails would stall the entire stream for everyone.
            logger.error(
                "Failed to dispatch trigger %s for agent %s: %s",
                trigger.trigger_id,
                trigger.agent_id,
                exc,
                exc_info=True,
            )

        await self._ack(msg_id)

    async def _ack(self, msg_id: bytes | str) -> None:
        """Acknowledge a message.  Non-fatal if it fails — Redis will redeliver."""
        try:
            await self._redis.xack(self._stream_key, self._consumer_group, msg_id)
        except Exception as exc:
            logger.warning("Failed to ack message %s: %s", msg_id, exc)
