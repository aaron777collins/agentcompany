"""
Heartbeat and trigger system.

Determines when agents wake up. Four modes (from the architecture spec):
  always_on       — Runs on a fixed interval (e.g. every 30s)
  event_triggered — Wakes when a qualifying event arrives via webhook
  scheduled       — Cron-style schedule (e.g. daily at 9am)
  manual          — Only runs when explicitly triggered via API

The HeartbeatService:
  1. Registers/deregisters APScheduler jobs for always_on and scheduled agents
  2. Routes incoming platform events to matching event_triggered agents
  3. Enqueues trigger messages to Redis Streams for the TriggerConsumer

Redis Stream key pattern: triggers:{agent_id}
Each message in the stream contains a trigger payload (see TriggerMessage).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class HeartbeatMode(str, Enum):
    ALWAYS_ON = "always_on"
    EVENT_TRIGGERED = "event_triggered"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


@dataclass
class EventFilter:
    """
    Rules that determine which platform events wake an event_triggered agent.

    An event must match ALL non-empty conditions to trigger the agent.
    If a field is empty/None it is treated as "match any".
    """

    event_types: list[str] = field(default_factory=list)
    # e.g. ["task.assigned", "message.mention", "document.created"]

    # Only wake if the event is directed at this agent's platform user ID
    match_assigned_to_agent: bool = True

    # Optional regex patterns applied to event content (ORed together)
    content_patterns: list[str] = field(default_factory=list)

    # Platform sources to listen to. Use ["all"] to listen to all sources.
    sources: list[str] = field(default_factory=lambda: ["all"])

    # Only wake for events at or above this priority ("low", "medium", "high", "critical")
    min_priority: Optional[str] = None

    def __post_init__(self) -> None:
        # Validate regex patterns at construction time so errors surface early
        for pattern in self.content_patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(
                    f"Invalid content_pattern regex '{pattern}': {exc}"
                ) from exc


@dataclass
class HeartbeatConfig:
    """Configuration for how and when an agent wakes up."""

    mode: HeartbeatMode
    interval_seconds: Optional[int] = None    # always_on only
    cron: Optional[str] = None                # scheduled only, e.g. "0 9 * * 1-5"
    event_filter: Optional[EventFilter] = None  # event_triggered only
    max_run_seconds: int = 300                 # Safety ceiling per invocation

    def __post_init__(self) -> None:
        if self.mode == HeartbeatMode.ALWAYS_ON:
            if not self.interval_seconds or self.interval_seconds < 1:
                raise ValueError(
                    "interval_seconds must be >= 1 for always_on mode"
                )
        if self.mode == HeartbeatMode.SCHEDULED:
            if not self.cron:
                raise ValueError("cron expression is required for scheduled mode")
        if self.mode == HeartbeatMode.EVENT_TRIGGERED:
            if self.event_filter is None:
                raise ValueError("event_filter is required for event_triggered mode")


@dataclass
class TriggerMessage:
    """
    A trigger message enqueued to Redis Streams.

    The TriggerConsumer deserializes this and passes it to the dispatcher.
    """

    trigger_id: str
    agent_id: str
    trigger_type: str          # "heartbeat.tick" | event type | "manual"
    source: str                # "heartbeat" | "plane" | "mattermost" | "outline" | "api"
    payload: dict[str, Any]
    enqueued_at: str           # ISO 8601
    attempt: int = 1

    def to_redis_dict(self) -> dict[str, str]:
        """Serialize to the flat string dict that Redis Streams requires."""
        return {
            "trigger_id": self.trigger_id,
            "agent_id": self.agent_id,
            "trigger_type": self.trigger_type,
            "source": self.source,
            "payload": json.dumps(self.payload),
            "enqueued_at": self.enqueued_at,
            "attempt": str(self.attempt),
        }

    @classmethod
    def from_redis_dict(cls, data: dict[str, str]) -> "TriggerMessage":
        """Deserialize from a Redis Streams message."""
        return cls(
            trigger_id=data["trigger_id"],
            agent_id=data["agent_id"],
            trigger_type=data["trigger_type"],
            source=data["source"],
            payload=json.loads(data.get("payload", "{}")),
            enqueued_at=data["enqueued_at"],
            attempt=int(data.get("attempt", 1)),
        )


_PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class HeartbeatService:
    """
    Routes platform events and timer ticks to the correct agents.

    Responsibilities:
      - Registering APScheduler jobs for always_on and scheduled agents
      - Matching incoming events against active agents' event filters
      - Enqueuing trigger messages to Redis Streams
    """

    GLOBAL_STREAM = "triggers:all"

    def __init__(
        self,
        agent_repo: Any,       # AgentRepository (provides list_active_*)
        trigger_queue: Any,    # Redis asyncio client
        scheduler: Any,        # APScheduler AsyncIOScheduler
    ) -> None:
        self._agents = agent_repo
        self._redis = trigger_queue
        self._scheduler = scheduler

    async def register_agent(self, agent_id: str, config: HeartbeatConfig) -> None:
        """
        Register an agent's heartbeat schedule.

        Called when an agent transitions to ACTIVE. For event_triggered and
        manual agents this is a no-op because they wake on demand, not on a
        schedule.
        """
        if not agent_id:
            raise ValueError("agent_id must not be empty")

        if config.mode == HeartbeatMode.ALWAYS_ON:
            job_id = f"heartbeat_{agent_id}"
            self._scheduler.add_job(
                self._tick,
                "interval",
                seconds=config.interval_seconds,
                id=job_id,
                args=[agent_id],
                replace_existing=True,
                max_instances=1,  # Prevent overlapping ticks for slow agents
            )
            logger.info(
                "Registered always_on heartbeat for agent %s (interval=%ds)",
                agent_id,
                config.interval_seconds,
            )

        elif config.mode == HeartbeatMode.SCHEDULED:
            job_id = f"schedule_{agent_id}"
            cron_kwargs = self._parse_cron(config.cron)
            self._scheduler.add_job(
                self._tick,
                "cron",
                id=job_id,
                args=[agent_id],
                replace_existing=True,
                max_instances=1,
                **cron_kwargs,
            )
            logger.info(
                "Registered scheduled heartbeat for agent %s (cron=%s)",
                agent_id,
                config.cron,
            )

        # event_triggered and manual modes have no scheduler job

    async def deregister_agent(self, agent_id: str) -> None:
        """
        Remove an agent's scheduled jobs.

        Called when an agent transitions to PAUSED or TERMINATED.
        """
        if not agent_id:
            raise ValueError("agent_id must not be empty")

        for prefix in ("heartbeat_", "schedule_"):
            job_id = f"{prefix}{agent_id}"
            try:
                self._scheduler.remove_job(job_id)
                logger.info("Removed scheduler job %s", job_id)
            except Exception:
                pass  # Job may not exist if the agent was event_triggered/manual

    async def handle_platform_event(self, event: dict[str, Any]) -> int:
        """
        Route a platform event to all matching active agents.

        Called by webhook handlers (Plane, Mattermost, Outline).
        Returns the number of agents triggered.
        """
        if not event:
            raise ValueError("event must not be empty")

        active_agents = await self._agents.list_active_event_triggered()
        triggered = 0

        for agent in active_agents:
            config = agent.get("heartbeat_config") or {}
            event_filter_data = config.get("event_filter")
            if not event_filter_data:
                continue

            # Reconstruct EventFilter from the stored config
            event_filter = self._build_event_filter(event_filter_data)
            agent_user_id = agent.get("platform_user_id", "")

            if self._matches(event, event_filter, agent_user_id):
                await self._enqueue_trigger(
                    agent_id=agent["agent_id"],
                    trigger_type=event.get("type", "platform_event"),
                    source=event.get("source", "unknown"),
                    payload=event,
                )
                triggered += 1

        logger.debug(
            "Platform event '%s' triggered %d agents", event.get("type"), triggered
        )
        return triggered

    async def enqueue_manual_trigger(
        self,
        agent_id: str,
        payload: dict[str, Any],
        triggered_by: str,
    ) -> str:
        """
        Enqueue a manual trigger for an agent.

        Returns the trigger_id for tracking.
        """
        if not agent_id:
            raise ValueError("agent_id must not be empty")

        trigger_id = await self._enqueue_trigger(
            agent_id=agent_id,
            trigger_type="manual",
            source="api",
            payload={"triggered_by": triggered_by, **payload},
        )
        logger.info(
            "Manual trigger %s enqueued for agent %s by %s",
            trigger_id,
            agent_id,
            triggered_by,
        )
        return trigger_id

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _tick(self, agent_id: str) -> None:
        """Periodic heartbeat callback invoked by APScheduler."""
        await self._enqueue_trigger(
            agent_id=agent_id,
            trigger_type="heartbeat.tick",
            source="heartbeat",
            payload={"type": "heartbeat.tick", "agent_id": agent_id},
        )

    async def _enqueue_trigger(
        self,
        agent_id: str,
        trigger_type: str,
        source: str,
        payload: dict[str, Any],
    ) -> str:
        trigger_id = f"trig_{uuid.uuid4().hex}"
        msg = TriggerMessage(
            trigger_id=trigger_id,
            agent_id=agent_id,
            trigger_type=trigger_type,
            source=source,
            payload=payload,
            enqueued_at=datetime.now(timezone.utc).isoformat(),
        )

        # Write to the global stream. The TriggerConsumer reads from here.
        await self._redis.xadd(self.GLOBAL_STREAM, msg.to_redis_dict())

        logger.debug(
            "Enqueued trigger %s for agent %s (type=%s)",
            trigger_id,
            agent_id,
            trigger_type,
        )
        return trigger_id

    def _matches(
        self,
        event: dict[str, Any],
        event_filter: EventFilter,
        agent_user_id: str,
    ) -> bool:
        """Return True if the event satisfies all conditions in the filter."""
        # Source check
        if "all" not in event_filter.sources:
            if event.get("source") not in event_filter.sources:
                return False

        # Event type check
        if event_filter.event_types:
            if event.get("type") not in event_filter.event_types:
                return False

        # Assignment check — agent must be the target
        if event_filter.match_assigned_to_agent:
            assigned_to = event.get("assigned_to") or event.get("mentioned_user_id")
            if assigned_to != agent_user_id:
                return False

        # Priority check
        if event_filter.min_priority:
            event_priority = event.get("priority", "low")
            min_rank = _PRIORITY_RANK.get(event_filter.min_priority, 0)
            event_rank = _PRIORITY_RANK.get(event_priority, 0)
            if event_rank < min_rank:
                return False

        # Content pattern check (OR across patterns)
        if event_filter.content_patterns:
            content = str(event.get("content", "") or event.get("description", ""))
            if not any(
                re.search(pattern, content, re.IGNORECASE)
                for pattern in event_filter.content_patterns
            ):
                return False

        return True

    def _build_event_filter(self, data: dict) -> EventFilter:
        """Construct an EventFilter from a stored config dict."""
        return EventFilter(
            event_types=data.get("event_types", []),
            match_assigned_to_agent=data.get("match_assigned_to_agent", True),
            content_patterns=data.get("content_patterns", []),
            sources=data.get("sources", ["all"]),
            min_priority=data.get("min_priority"),
        )

    @staticmethod
    def _parse_cron(cron_expr: str) -> dict:
        """
        Parse a cron expression string into APScheduler keyword arguments.

        Supports standard 5-field format: minute hour day month day_of_week
        e.g. "0 9 * * 1-5" => every weekday at 09:00
        """
        if not cron_expr:
            raise ValueError("cron expression must not be empty")

        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(
                f"cron expression must have 5 fields (minute hour day month day_of_week), "
                f"got: '{cron_expr}'"
            )

        return {
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "day_of_week": parts[4],
        }
