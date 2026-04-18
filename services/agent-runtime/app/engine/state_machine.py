"""
Agent state machine.

Defines valid states, valid transitions between them, and the runtime
enforcement of those transitions. Every state change is validated here
before any side effects (DB writes, event emissions) occur.

States (from the architecture spec):
  CREATED -> CONFIGURING -> IDLE -> RUNNING -> PAUSED -> ERROR -> TERMINATED

The architecture doc also uses CONFIGURED/ACTIVE/IDLE interchangeably across
different diagrams. We implement the full set from both docs to be explicit:
  CREATED -> CONFIGURED -> ACTIVE (IDLE) -> RUNNING -> PAUSED -> TERMINATED

ERROR is a recoverable state that allows retry back to ACTIVE.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    """All possible lifecycle states for an agent."""

    CREATED = "created"
    CONFIGURED = "configured"
    ACTIVE = "active"       # "IDLE" in some architecture diagrams — ready for triggers
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"         # Recoverable error, can resume to ACTIVE
    TERMINATED = "terminated"


# Each entry is (from_state, to_state).
# This set is the single source of truth for allowed transitions.
# Consult agent-framework.md before adding new transitions — the graph must
# remain a DAG except for the RUNNING <-> ACTIVE loop.
VALID_TRANSITIONS: frozenset[tuple[AgentState, AgentState]] = frozenset(
    {
        (AgentState.CREATED, AgentState.CONFIGURED),
        (AgentState.CONFIGURED, AgentState.ACTIVE),
        (AgentState.ACTIVE, AgentState.RUNNING),
        (AgentState.ACTIVE, AgentState.PAUSED),
        (AgentState.ACTIVE, AgentState.TERMINATED),
        # Task complete — return to ready
        (AgentState.RUNNING, AgentState.ACTIVE),
        # Budget exceeded mid-run
        (AgentState.RUNNING, AgentState.PAUSED),
        # Unrecoverable failure during a run
        (AgentState.RUNNING, AgentState.TERMINATED),
        # Recoverable error — moves to ERROR for inspection, not immediate termination
        (AgentState.RUNNING, AgentState.ERROR),
        # Budget refilled or admin resume
        (AgentState.PAUSED, AgentState.ACTIVE),
        (AgentState.PAUSED, AgentState.TERMINATED),
        # Error resolved — resume
        (AgentState.ERROR, AgentState.ACTIVE),
        (AgentState.ERROR, AgentState.TERMINATED),
        # Config update while active (e.g. system prompt change)
        (AgentState.ACTIVE, AgentState.CONFIGURED),
    }
)


class InvalidTransitionError(Exception):
    """Raised when a state transition is not in VALID_TRANSITIONS."""

    def __init__(
        self,
        agent_id: str,
        from_state: AgentState,
        to_state: AgentState,
    ) -> None:
        self.agent_id = agent_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Agent {agent_id}: invalid transition {from_state.value} -> {to_state.value}. "
            f"Valid transitions from {from_state.value}: "
            f"{[t.value for _, t in VALID_TRANSITIONS if _ == from_state]}"
        )


@dataclass
class StateTransition:
    """
    Immutable record of a single state transition.

    Appended to the agent_transitions table — never updated.
    This is the audit trail for why an agent is in its current state.
    """

    agent_id: str
    from_state: AgentState
    to_state: AgentState
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    triggered_by: Optional[str] = None  # user_id, "system", or run_id


class AgentStateMachine:
    """
    Validates and records agent state transitions.

    This class does NOT perform DB writes or event emission — those are
    side effects owned by AgentManager. This class only enforces the rules.
    """

    def __init__(self, agent_id: str, current_state: AgentState) -> None:
        if not agent_id:
            raise ValueError("agent_id must not be empty")
        self._agent_id = agent_id
        self._state = current_state

    @property
    def state(self) -> AgentState:
        return self._state

    def transition(
        self,
        to_state: AgentState,
        reason: str,
        triggered_by: Optional[str] = None,
    ) -> StateTransition:
        """
        Validate and apply a transition.

        Returns a StateTransition record that the caller must persist.
        Raises InvalidTransitionError if the transition is not allowed.
        """
        if not reason:
            raise ValueError("A reason must be provided for all state transitions")

        if (self._state, to_state) not in VALID_TRANSITIONS:
            raise InvalidTransitionError(self._agent_id, self._state, to_state)

        transition = StateTransition(
            agent_id=self._agent_id,
            from_state=self._state,
            to_state=to_state,
            reason=reason,
            triggered_by=triggered_by,
        )

        logger.info(
            "Agent %s: %s -> %s (reason=%s triggered_by=%s)",
            self._agent_id,
            self._state.value,
            to_state.value,
            reason,
            triggered_by or "system",
        )

        self._state = to_state
        return transition

    def can_transition_to(self, to_state: AgentState) -> bool:
        """Return True if the transition from current state to to_state is valid."""
        return (self._state, to_state) in VALID_TRANSITIONS

    def is_runnable(self) -> bool:
        """True if the agent can accept a new trigger right now."""
        return self._state == AgentState.ACTIVE

    def is_terminal(self) -> bool:
        """True if the agent has reached a final, non-resumable state."""
        return self._state == AgentState.TERMINATED
