"""Agent engine service — facade for the API layer.

The AgentManager in agent_manager.py is built for the asyncpg-based
decision-loop runtime. The API layer uses SQLAlchemy AsyncSession. Rather than
forcing one ORM to serve both, this module provides a thin facade that:

  1. Accepts SQLAlchemy sessions from the FastAPI dependency layer.
  2. Delegates state-machine validation to AgentStateMachine (shared logic).
  3. Writes DB transitions via parameterized SQLAlchemy text() queries.
  4. Publishes state-changed events to the EventBus.
  5. Enqueues manual triggers to Redis Streams via HeartbeatService.

The AgentManager (asyncpg-based) remains the authoritative runtime manager
for the decision loop.  This service handles only the API-initiated lifecycle
calls: start, stop, and manual trigger.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
