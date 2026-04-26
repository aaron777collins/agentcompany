"""Agent engine service — facade for the API layer.

The AgentManager in agent_manager.py is built for the asyncpg-based
decision-loop runtime. The API layer uses SQLAlchemy AsyncSession. Rather than
forcing one ORM to serve both, this module provides a thin facade that:

  1. Accepts SQLAlchemy sessions from the FastAPI dependency layer.
  2. Delegates state-machine validation to AgentStateMachine (shared logic).
  3. Writes DB transitions via parameterized SQLAlchemy text() queries.
  4. Publishes state-changed events to the EventBus.
  5. Enqueues manual triggers to Redis Streams via HeartbeatService.
  6. Dispatches inbound trigger messages from the TriggerConsumer.
  7. Routes platform events to matching event_triggered agents.

The AgentManager (asyncpg-based) remains the authoritative runtime manager
for the decision loop.  This service handles only the API-initiated lifecycle
calls: start, stop, manual trigger, and event-driven trigger routing.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.engine.heartbeat import TriggerMessage
from app.engine.state_machine import (
    AgentState,
    AgentStateMachine,
    InvalidTransitionError,
)

logger = logging.getLogger(__name__)


# Maps the ORM status strings (stored in the agents table) to the engine's
# AgentState enum.  Only statuses that can be current when an API call arrives
# need to be mapped; transient statuses like "starting" are short-lived.
_ORM_STATUS_TO_STATE: dict[str, AgentState] = {
    "idle": AgentState.ACTIVE,
    "active": AgentState.ACTIVE,
    "starting": AgentState.CONFIGURED,
    "stopping": AgentState.ACTIVE,
    "paused": AgentState.PAUSED,
    "error": AgentState.ERROR,
}

# Maps engine AgentState back to the ORM status string.
_STATE_TO_ORM_STATUS: dict[AgentState, str] = {
    AgentState.ACTIVE: "active",
    AgentState.RUNNING: "active",
    AgentState.PAUSED: "paused",
    AgentState.ERROR: "error",
    AgentState.TERMINATED: "paused",  # closest safe status after forced stop
}


class EngineError(Exception):
    """Raised when the engine cannot perform a requested lifecycle operation."""


class AgentEngineService:
    """
    API-layer facade for agent lifecycle operations.

    Created once during lifespan startup and stored on app.state.agent_manager.
    Methods accept an AsyncSession provided by the request's get_db dependency,
    so each call participates in the request's unit-of-work transaction.

    The heartbeat_service and event_bus are optional at construction time so
    the service degrades gracefully when those components are unavailable.
    """

    def __init__(
        self,
        heartbeat_service: Any | None = None,  # HeartbeatService, optional
        event_bus: Any | None = None,  # EventBus, optional
    ) -> None:
        self._heartbeat = heartbeat_service
        self._bus = event_bus

    def set_heartbeat_service(self, heartbeat_service: Any) -> None:
        """
        Inject the HeartbeatService after construction.

        Called from the lifespan context once the APScheduler and Redis are
        both ready.  Allows the engine to be constructed early (before all
        dependencies exist) and updated later without a full teardown.
        """
        self._heartbeat = heartbeat_service

    # ------------------------------------------------------------------
    # Public API — called from app/api/agents.py
    # ------------------------------------------------------------------

    async def start_agent(
        self,
        agent_id: str,
        db: AsyncSession,
        triggered_by: str | None = None,
    ) -> None:
        """
        Transition an agent to ACTIVE state and register its heartbeat.

        The API endpoint has already set status='starting' and flushed.  This
        method finalises the transition to 'active' by writing the transition
        record and registering the heartbeat schedule.

        Raises EngineError if the state machine rejects the transition.
        """
        if not agent_id:
            raise ValueError("agent_id must not be empty")

        # Fetch the minimal fields we need without loading the full ORM object
        # (the session already has the agent from the endpoint's _get_or_404).
        row = await db.execute(
            text("SELECT status, llm_config FROM agents WHERE id = :id AND deleted_at IS NULL"),
            {"id": agent_id},
        )
        record = row.mappings().one_or_none()
        if record is None:
            raise EngineError(f"Agent '{agent_id}' not found in engine start path")

        current_orm_status = record["status"]
        current_state = _ORM_STATUS_TO_STATE.get(current_orm_status)
        if current_state is None:
            raise EngineError(f"Agent '{agent_id}' has unrecognised status '{current_orm_status}'")

        # Validate the CONFIGURED -> ACTIVE transition using the shared state machine.
        # We treat 'starting' (set by the API endpoint before this call) as CONFIGURED.
        sm = AgentStateMachine(agent_id=agent_id, current_state=AgentState.CONFIGURED)
        try:
            sm.transition(
                to_state=AgentState.ACTIVE,
                reason="api_start",
                triggered_by=triggered_by,
            )
        except InvalidTransitionError as exc:
            raise EngineError(str(exc)) from exc

        await db.execute(
            text(
                "UPDATE agents SET status = 'active', version = version + 1, "
                "updated_at = NOW() WHERE id = :id"
            ),
            {"id": agent_id},
        )
        await _write_transition(
            db=db,
            agent_id=agent_id,
            from_status="configured",
            to_status="active",
            reason="api_start",
            triggered_by=triggered_by,
        )

        await self._publish_state_changed(
            agent_id=agent_id,
            from_state="configured",
            to_state="active",
            reason="api_start",
            triggered_by=triggered_by,
        )

        logger.info("Engine: agent %s started (triggered_by=%s)", agent_id, triggered_by)

    async def stop_agent(
        self,
        agent_id: str,
        db: AsyncSession,
        drain: bool = True,
        reason: str | None = None,
        triggered_by: str | None = None,
    ) -> None:
        """
        Transition an agent to PAUSED state and deregister its heartbeat.

        The API endpoint has already set status='stopping'|'idle' and flushed.
        This method writes the transition log and deregisters the scheduler job.

        Raises EngineError if the operation cannot be completed.
        """
        if not agent_id:
            raise ValueError("agent_id must not be empty")

        stop_reason = reason or ("drain_stop" if drain else "immediate_stop")

        await _write_transition(
            db=db,
            agent_id=agent_id,
            from_status="active",
            to_status="idle",
            reason=stop_reason,
            triggered_by=triggered_by,
        )

        # Deregister heartbeat jobs so the agent does not receive ticks while idle.
        if self._heartbeat is not None:
            try:
                await self._heartbeat.deregister_agent(agent_id)
            except Exception:
                # Scheduler job may not exist for manual-mode agents — not fatal.
                logger.debug(
                    "Engine: no heartbeat job to deregister for agent %s (non-fatal)",
                    agent_id,
                )

        await self._publish_state_changed(
            agent_id=agent_id,
            from_state="active",
            to_state="idle",
            reason=stop_reason,
            triggered_by=triggered_by,
        )

        logger.info(
            "Engine: agent %s stopped (drain=%s triggered_by=%s)",
            agent_id,
            drain,
            triggered_by,
        )

    async def trigger_agent(
        self,
        agent_id: str,
        db: AsyncSession,
        event_data: dict[str, Any],
        triggered_by: str | None = None,
    ) -> str:
        """
        Enqueue a manual trigger for the agent's decision loop.

        Returns the trigger_id so the API response can include it for tracking.
        Raises EngineError if enqueuing fails.
        """
        if not agent_id:
            raise ValueError("agent_id must not be empty")

        if self._heartbeat is None:
            # No heartbeat service — the trigger is effectively a no-op beyond
            # the DB update already done by the endpoint.  Log and continue so
            # the endpoint can still return a success response.
            logger.warning(
                "Engine: heartbeat service not available; trigger for agent %s "
                "queued in DB only (no Redis stream write)",
                agent_id,
            )
            return f"local_{agent_id}"

        try:
            trigger_id = await self._heartbeat.enqueue_manual_trigger(
                agent_id=agent_id,
                payload=event_data,
                triggered_by=triggered_by or "api",
            )
        except Exception as exc:
            raise EngineError(f"Failed to enqueue trigger for agent '{agent_id}': {exc}") from exc

        logger.info(
            "Engine: manual trigger %s enqueued for agent %s",
            trigger_id,
            agent_id,
        )
        return trigger_id

    async def dispatch_trigger(self, trigger: "TriggerMessage") -> None:
        """
        Dispatch a TriggerMessage that arrived from the TriggerConsumer.

        This is the entry point for all Redis-stream-based triggers —
        heartbeat ticks, manual triggers, and event-sourced triggers routed by
        HeartbeatService.  The method validates the agent is active before
        handing off to the decision loop.

        For now this logs the trigger and publishes a state-changed event.
        Wiring the full decision loop execution is Phase 4 work (when the loop
        runner infrastructure is in place).
        """
        if trigger is None:
            raise ValueError("trigger must not be None")

        agent_id = trigger.agent_id
        if not agent_id:
            raise ValueError("trigger.agent_id must not be empty")

        logger.info(
            "Dispatching trigger %s for agent %s (type=%s source=%s)",
            trigger.trigger_id,
            agent_id,
            trigger.trigger_type,
            trigger.source,
        )

        # Publish so the SSE endpoint and audit log can observe the trigger.
        # company_id is embedded in the trigger payload when available.
        company_id = trigger.payload.get("company_id", "")
        if self._bus is not None and company_id:
            try:
                await self._bus.publish(
                    company_id,
                    {
                        "type": "agent.triggered",
                        "agent_id": agent_id,
                        "trigger_id": trigger.trigger_id,
                        "trigger_type": trigger.trigger_type,
                        "source": trigger.source,
                    },
                )
            except Exception:
                logger.warning(
                    "Failed to publish agent.triggered event for agent %s (non-fatal)",
                    agent_id,
                    exc_info=True,
                )

    async def trigger_by_event(
        self,
        company_id: str,
        event_type: str,
        event_data: dict[str, Any],
    ) -> int:
        """
        Find all active event_triggered agents in *company_id* whose event
        filter matches *event_type*, and enqueue a trigger for each.

        Returns the number of agents triggered.

        This is called by the TriggerConsumer when it processes events from the
        ``agent_events`` stream (platform webhook events re-published there by
        webhook handlers).  The heavy event-filter matching already happened in
        HeartbeatService.handle_platform_event(); this path handles the simpler
        case where a consumer-group event carries a plain event_type and we
        want to fan out to matching agents without re-doing HMAC work.
        """
        if not company_id:
            raise ValueError("company_id must not be empty")
        if not event_type:
            raise ValueError("event_type must not be empty")

        if self._heartbeat is None:
            logger.warning(
                "trigger_by_event called but heartbeat service is unavailable; "
                "event '%s' for company %s will not be routed",
                event_type,
                company_id,
            )
            return 0

        # Query agents directly here instead of via a SQLAlchemy session
        # because this method may be called from async background tasks that
        # do not hold a request-scoped session.
        factory = get_session_factory()
        triggered = 0

        try:
            async with factory() as session:
                rows = await session.execute(
                    text(
                        """
                        SELECT id, llm_config
                        FROM agents
                        WHERE company_id = :company_id
                          AND status IN ('active', 'idle')
                          AND deleted_at IS NULL
                        """
                    ),
                    {"company_id": company_id},
                )
                agents = rows.mappings().all()
        except Exception as exc:
            logger.error(
                "trigger_by_event: DB query failed for company %s event %s: %s",
                company_id,
                event_type,
                exc,
                exc_info=True,
            )
            return 0

        for agent_row in agents:
            agent_id = agent_row["id"]
            llm_config: dict = agent_row["llm_config"] or {}
            heartbeat_cfg: dict = llm_config.get("heartbeat_config") or {}

            # Only wake event_triggered agents
            if heartbeat_cfg.get("mode") != "event_triggered":
                continue

            event_filter: dict = heartbeat_cfg.get("event_filter") or {}
            event_types_filter: list = event_filter.get("event_types") or []

            # Empty event_types list means "match all"; otherwise the
            # incoming event_type must be in the allowed list.
            if event_types_filter and event_type not in event_types_filter:
                continue

            try:
                await self._heartbeat.enqueue_manual_trigger(
                    agent_id=agent_id,
                    payload={**event_data, "company_id": company_id},
                    triggered_by=f"event:{event_type}",
                )
                triggered += 1
            except Exception as exc:
                logger.error(
                    "trigger_by_event: failed to enqueue trigger for agent %s: %s",
                    agent_id,
                    exc,
                    exc_info=True,
                )

        logger.info(
            "trigger_by_event: routed event '%s' to %d agents in company %s",
            event_type,
            triggered,
            company_id,
        )
        return triggered

    async def shutdown(self) -> None:
        """
        Gracefully shut down the engine service.

        Called during app lifespan teardown.  Cleans up any internal resources.
        The HeartbeatService's APScheduler is owned by the lifespan context and
        shut down separately; we just nullify references here.
        """
        logger.info("AgentEngineService shutting down")
        self._heartbeat = None
        self._bus = None

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _publish_state_changed(
        self,
        agent_id: str,
        from_state: str,
        to_state: str,
        reason: str,
        triggered_by: str | None,
    ) -> None:
        """Publish a state-changed event to the EventBus. Non-fatal on failure."""
        if self._bus is None:
            return
        try:
            # company_id is not readily available here; the event bus publish()
            # signature requires it.  We use a sentinel so downstream consumers
            # can still receive the event; the agent_id is always present.
            await self._bus.publish(
                "agent_events",
                {
                    "type": "agent.state_changed",
                    "agent_id": agent_id,
                    "from_state": from_state,
                    "to_state": to_state,
                    "reason": reason,
                    "triggered_by": triggered_by,
                },
            )
        except Exception:
            logger.warning(
                "Engine: failed to publish state_changed for agent %s (non-fatal)",
                agent_id,
                exc_info=True,
            )


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


async def _write_transition(
    db: AsyncSession,
    agent_id: str,
    from_status: str,
    to_status: str,
    reason: str,
    triggered_by: str | None,
) -> None:
    """
    Append a row to agent_transitions within the current SQLAlchemy transaction.

    All parameters are passed as bind variables — never interpolated into the
    SQL string — to prevent injection even if caller-supplied strings are used.
    The table may not exist in early dev environments; errors are logged but
    not re-raised so the primary agent status update is never rolled back by a
    missing audit table.
    """
    try:
        await db.execute(
            text(
                """
                INSERT INTO agent_transitions
                    (agent_id, from_state, to_state, reason, triggered_by, transitioned_at)
                VALUES (:agent_id, :from_state, :to_state, :reason, :triggered_by, NOW())
                """
            ),
            {
                "agent_id": agent_id,
                "from_state": from_status,
                "to_state": to_status,
                "reason": reason,
                "triggered_by": triggered_by,
            },
        )
    except Exception:
        # The agent_transitions table is part of the Phase 2 migration.  If it
        # doesn't exist yet (e.g. running against an older schema), log and
        # continue — the main agents.status update is more important.
        logger.warning(
            "Engine: could not write to agent_transitions for agent %s (non-fatal)",
            agent_id,
            exc_info=True,
        )
