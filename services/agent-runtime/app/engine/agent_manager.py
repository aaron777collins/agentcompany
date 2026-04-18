"""
Agent lifecycle manager.

Manages the full lifecycle of an agent — from creation through termination.
Owns the side effects of state transitions: DB writes, event bus publications,
heartbeat registration/deregistration.

The AgentStateMachine validates that transitions are allowed; AgentManager
carries out the consequences.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .heartbeat import HeartbeatConfig, HeartbeatService
from .state_machine import AgentState, AgentStateMachine, InvalidTransitionError, StateTransition

logger = logging.getLogger(__name__)


@dataclass
class AgentRecord:
    """
    Minimal in-memory representation of an agent.

    Full agent config lives in the DB; this holds what the manager needs
    to make lifecycle decisions.
    """

    agent_id: str
    company_id: str
    role: str
    display_name: str
    platform_user_id: str
    state: AgentState
    heartbeat_config: HeartbeatConfig
    llm_adapter_id: str
    system_prompt: str
    token_budget_daily: int = 100_000
    token_budget_monthly: int = 2_000_000
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentManager:
    """
    Creates, configures, transitions, and terminates agents.

    All public methods are async. Callers are the API layer (agent CRUD
    endpoints) and the decision loop (state transitions during a run).
    """

    def __init__(
        self,
        agent_repo: Any,       # AgentRepository (asyncpg-based)
        heartbeat_service: HeartbeatService,
        event_bus: Any,        # EventBus or compatible publisher
        db_pool: Any,          # asyncpg Pool (for transition log writes)
    ) -> None:
        self._repo = agent_repo
        self._heartbeat = heartbeat_service
        self._bus = event_bus
        self._db = db_pool

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create(
        self,
        company_id: str,
        role: str,
        display_name: str,
        platform_user_id: str,
        heartbeat_config: HeartbeatConfig,
        llm_adapter_id: str,
        system_prompt: str,
        token_budget_daily: int = 100_000,
        token_budget_monthly: int = 2_000_000,
        metadata: Optional[dict] = None,
    ) -> AgentRecord:
        """
        Create a new agent record in CREATED state.

        The agent is not active yet — call configure() then activate() to
        make it ready to receive triggers.
        """
        if not company_id:
            raise ValueError("company_id must not be empty")
        if not role:
            raise ValueError("role must not be empty")
        if not display_name:
            raise ValueError("display_name must not be empty")
        if token_budget_daily < 0:
            raise ValueError("token_budget_daily must be >= 0")
        if token_budget_monthly < 0:
            raise ValueError("token_budget_monthly must be >= 0")

        agent_id = f"agt_{uuid.uuid4().hex[:12]}"

        agent = AgentRecord(
            agent_id=agent_id,
            company_id=company_id,
            role=role,
            display_name=display_name,
            platform_user_id=platform_user_id,
            state=AgentState.CREATED,
            heartbeat_config=heartbeat_config,
            llm_adapter_id=llm_adapter_id,
            system_prompt=system_prompt,
            token_budget_daily=token_budget_daily,
            token_budget_monthly=token_budget_monthly,
            metadata=metadata or {},
        )

        await self._repo.create(agent)
        logger.info("Created agent %s (role=%s company=%s)", agent_id, role, company_id)
        return agent

    async def configure(self, agent_id: str, triggered_by: Optional[str] = None) -> None:
        """
        Transition CREATED -> CONFIGURED.

        Called after the agent record is created and its config is validated
        (LLM adapter reachable, tools exist, budget allocated).
        """
        await self._transition(
            agent_id=agent_id,
            to_state=AgentState.CONFIGURED,
            reason="configuration_complete",
            triggered_by=triggered_by,
        )

    async def activate(self, agent_id: str, triggered_by: Optional[str] = None) -> None:
        """
        Transition CONFIGURED -> ACTIVE.

        Registers the agent with the heartbeat service so it can receive
        triggers. After this call the agent is live.
        """
        agent = await self._repo.get(agent_id)
        await self._transition(
            agent_id=agent_id,
            to_state=AgentState.ACTIVE,
            reason="activation",
            triggered_by=triggered_by,
        )
        # Side effect: register heartbeat/schedule
        await self._heartbeat.register_agent(agent_id, agent.heartbeat_config)
        logger.info("Agent %s is now ACTIVE", agent_id)

    async def pause(self, agent_id: str, reason: str, triggered_by: Optional[str] = None) -> None:
        """
        Transition ACTIVE or RUNNING -> PAUSED.

        Deregisters heartbeat jobs. Incoming triggers will queue but not
        execute until the agent is resumed.
        """
        if not reason:
            raise ValueError("A reason must be provided when pausing an agent")

        await self._transition(
            agent_id=agent_id,
            to_state=AgentState.PAUSED,
            reason=reason,
            triggered_by=triggered_by,
        )
        await self._heartbeat.deregister_agent(agent_id)
        logger.info("Agent %s PAUSED: %s", agent_id, reason)

    async def resume(self, agent_id: str, triggered_by: Optional[str] = None) -> None:
        """
        Transition PAUSED -> ACTIVE.

        Re-registers heartbeat. The agent will process queued triggers.
        """
        agent = await self._repo.get(agent_id)
        await self._transition(
            agent_id=agent_id,
            to_state=AgentState.ACTIVE,
            reason="resumed",
            triggered_by=triggered_by,
        )
        await self._heartbeat.register_agent(agent_id, agent.heartbeat_config)
        logger.info("Agent %s RESUMED", agent_id)

    async def mark_running(self, agent_id: str, run_id: str) -> None:
        """
        Transition ACTIVE -> RUNNING at the start of a decision loop.

        Called by the dispatcher before launching a run.
        """
        await self._transition(
            agent_id=agent_id,
            to_state=AgentState.RUNNING,
            reason="run_start",
            triggered_by=run_id,
        )

    async def mark_complete(self, agent_id: str, run_id: str) -> None:
        """
        Transition RUNNING -> ACTIVE after a successful run.
        """
        await self._transition(
            agent_id=agent_id,
            to_state=AgentState.ACTIVE,
            reason="task_complete",
            triggered_by=run_id,
        )

    async def mark_error(
        self,
        agent_id: str,
        run_id: str,
        error_message: str,
        fatal: bool = False,
    ) -> None:
        """
        Handle a run that ended in error.

        If fatal=True, transitions to TERMINATED.
        Otherwise transitions to ERROR, from which the agent can be resumed.
        """
        to_state = AgentState.TERMINATED if fatal else AgentState.ERROR
        await self._transition(
            agent_id=agent_id,
            to_state=to_state,
            reason=f"error:{error_message[:200]}",
            triggered_by=run_id,
        )
        if not fatal:
            # Deregister so we don't keep triggering a broken agent
            await self._heartbeat.deregister_agent(agent_id)

    async def terminate(self, agent_id: str, reason: str, triggered_by: Optional[str] = None) -> None:
        """
        Permanently terminate an agent.

        Deregisters heartbeat. State is TERMINATED — no further runs can start.
        """
        if not reason:
            raise ValueError("A reason must be provided when terminating an agent")

        await self._heartbeat.deregister_agent(agent_id)
        await self._transition(
            agent_id=agent_id,
            to_state=AgentState.TERMINATED,
            reason=reason,
            triggered_by=triggered_by,
        )
        logger.info("Agent %s TERMINATED: %s", agent_id, reason)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _transition(
        self,
        agent_id: str,
        to_state: AgentState,
        reason: str,
        triggered_by: Optional[str] = None,
    ) -> StateTransition:
        """
        Load agent, validate and apply state transition, persist record,
        and publish event.
        """
        agent = await self._repo.get(agent_id)
        if agent is None:
            raise ValueError(f"Agent {agent_id} not found")

        sm = AgentStateMachine(agent_id=agent_id, current_state=agent.state)
        transition = sm.transition(
            to_state=to_state,
            reason=reason,
            triggered_by=triggered_by,
        )

        # Persist the new state and the transition record atomically
        async with self._db.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE public.agents SET status = $1, updated_at = NOW() WHERE id = $2",
                    to_state.value,
                    agent_id,
                )
                await conn.execute(
                    """
                    INSERT INTO agent_transitions
                        (agent_id, from_state, to_state, reason, triggered_by, transitioned_at)
                    VALUES ($1, $2, $3, $4, $5, NOW())
                    """,
                    agent_id,
                    transition.from_state.value,
                    transition.to_state.value,
                    transition.reason,
                    transition.triggered_by,
                )

        # Publish event for downstream consumers (web UI, audit log, etc.)
        try:
            await self._bus.publish(
                "agent.state_changed",
                {
                    "agent_id": agent_id,
                    "company_id": agent.company_id,
                    "from_state": transition.from_state.value,
                    "to_state": transition.to_state.value,
                    "reason": transition.reason,
                    "triggered_by": transition.triggered_by,
                    "timestamp": transition.timestamp.isoformat(),
                },
            )
        except Exception:
            # Event publication failure must not roll back the state change
            logger.warning(
                "Failed to publish state_changed event for agent %s (non-fatal)",
                agent_id,
                exc_info=True,
            )

        return transition
