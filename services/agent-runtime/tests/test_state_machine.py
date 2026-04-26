"""
Unit tests for the AgentStateMachine.

Based on app/engine/state_machine.py.
Tests every valid transition in VALID_TRANSITIONS and a representative
set of invalid transitions. Also tests terminal state enforcement,
error recovery, and the guard conditions on the constructor.
"""

from __future__ import annotations

import pytest

from app.engine.state_machine import (
    AgentState,
    AgentStateMachine,
    InvalidTransitionError,
    StateTransition,
    VALID_TRANSITIONS,
)


# ---------------------------------------------------------------------------
# Constructor guards
# ---------------------------------------------------------------------------


def test_empty_agent_id_raises_value_error():
    with pytest.raises(ValueError, match="agent_id"):
        AgentStateMachine(agent_id="", current_state=AgentState.CREATED)


def test_initial_state_is_accessible():
    sm = AgentStateMachine(agent_id="agt-001", current_state=AgentState.CREATED)
    assert sm.state == AgentState.CREATED


# ---------------------------------------------------------------------------
# Valid transitions — exhaustive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "from_state, to_state",
    list(VALID_TRANSITIONS),
    ids=[f"{f.value}->{t.value}" for f, t in VALID_TRANSITIONS],
)
def test_valid_transition_succeeds(from_state: AgentState, to_state: AgentState):
    sm = AgentStateMachine(agent_id="agt-param", current_state=from_state)
    result = sm.transition(to_state=to_state, reason="test")
    assert isinstance(result, StateTransition)
    assert result.from_state == from_state
    assert result.to_state == to_state
    assert sm.state == to_state


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------


def test_invalid_transition_raises_invalid_transition_error():
    sm = AgentStateMachine(agent_id="agt-002", current_state=AgentState.CREATED)
    with pytest.raises(InvalidTransitionError):
        sm.transition(to_state=AgentState.RUNNING, reason="skip to running")


def test_invalid_transition_error_message_includes_states():
    sm = AgentStateMachine(agent_id="agt-003", current_state=AgentState.TERMINATED)
    with pytest.raises(InvalidTransitionError) as exc_info:
        sm.transition(to_state=AgentState.ACTIVE, reason="impossible")
    error_msg = str(exc_info.value)
    assert "terminated" in error_msg
    assert "active" in error_msg


def test_state_not_changed_after_invalid_transition():
    sm = AgentStateMachine(agent_id="agt-004", current_state=AgentState.CREATED)
    try:
        sm.transition(to_state=AgentState.RUNNING, reason="illegal")
    except InvalidTransitionError:
        pass
    assert sm.state == AgentState.CREATED


# ---------------------------------------------------------------------------
# Empty reason guard
# ---------------------------------------------------------------------------


def test_transition_without_reason_raises_value_error():
    sm = AgentStateMachine(agent_id="agt-005", current_state=AgentState.CREATED)
    with pytest.raises(ValueError, match="reason"):
        sm.transition(to_state=AgentState.CONFIGURED, reason="")


# ---------------------------------------------------------------------------
# Terminal state
# ---------------------------------------------------------------------------


def test_terminal_state_cannot_transition_to_any_state():
    sm = AgentStateMachine(agent_id="agt-006", current_state=AgentState.TERMINATED)
    for state in AgentState:
        if state == AgentState.TERMINATED:
            continue
        with pytest.raises(InvalidTransitionError):
            sm.transition(to_state=state, reason="after termination")


def test_is_terminal_returns_true_for_terminated():
    sm = AgentStateMachine(agent_id="agt-007", current_state=AgentState.TERMINATED)
    assert sm.is_terminal() is True


def test_is_terminal_returns_false_for_non_terminal():
    for state in [AgentState.CREATED, AgentState.ACTIVE, AgentState.RUNNING, AgentState.ERROR]:
        sm = AgentStateMachine(agent_id="agt-nt", current_state=state)
        assert sm.is_terminal() is False


# ---------------------------------------------------------------------------
# Runnable check
# ---------------------------------------------------------------------------


def test_is_runnable_only_in_active_state():
    runnable_sm = AgentStateMachine(agent_id="agt-008", current_state=AgentState.ACTIVE)
    assert runnable_sm.is_runnable() is True

    for state in AgentState:
        if state == AgentState.ACTIVE:
            continue
        non_runnable = AgentStateMachine(agent_id="agt-nr", current_state=state)
        assert non_runnable.is_runnable() is False


# ---------------------------------------------------------------------------
# Error recovery
# ---------------------------------------------------------------------------


def test_error_recovery_error_to_active():
    sm = AgentStateMachine(agent_id="agt-009", current_state=AgentState.ERROR)
    result = sm.transition(to_state=AgentState.ACTIVE, reason="error resolved")
    assert sm.state == AgentState.ACTIVE
    assert result.to_state == AgentState.ACTIVE


def test_error_state_can_terminate():
    sm = AgentStateMachine(agent_id="agt-010", current_state=AgentState.ERROR)
    result = sm.transition(to_state=AgentState.TERMINATED, reason="unrecoverable error")
    assert sm.state == AgentState.TERMINATED


# ---------------------------------------------------------------------------
# Full happy path: CREATED -> CONFIGURED -> ACTIVE -> RUNNING -> ACTIVE
# ---------------------------------------------------------------------------


def test_full_lifecycle_happy_path():
    sm = AgentStateMachine(agent_id="agt-full", current_state=AgentState.CREATED)

    sm.transition(AgentState.CONFIGURED, reason="config applied")
    sm.transition(AgentState.ACTIVE, reason="agent started")
    sm.transition(AgentState.RUNNING, reason="task received")
    sm.transition(AgentState.ACTIVE, reason="task complete")

    assert sm.state == AgentState.ACTIVE
    assert sm.is_runnable() is True


# ---------------------------------------------------------------------------
# Paused -> Active (budget refilled)
# ---------------------------------------------------------------------------


def test_paused_to_active_transition():
    sm = AgentStateMachine(agent_id="agt-pause", current_state=AgentState.PAUSED)
    sm.transition(AgentState.ACTIVE, reason="budget refilled")
    assert sm.state == AgentState.ACTIVE


# ---------------------------------------------------------------------------
# StateTransition record includes triggered_by
# ---------------------------------------------------------------------------


def test_transition_record_includes_triggered_by():
    sm = AgentStateMachine(agent_id="agt-trigger", current_state=AgentState.ACTIVE)
    record = sm.transition(
        AgentState.RUNNING, reason="task received", triggered_by="user-abc"
    )
    assert record.triggered_by == "user-abc"
    assert record.agent_id == "agt-trigger"


def test_transition_record_timestamp_is_set():
    sm = AgentStateMachine(agent_id="agt-ts", current_state=AgentState.CREATED)
    record = sm.transition(AgentState.CONFIGURED, reason="initial config")
    assert record.timestamp is not None


# ---------------------------------------------------------------------------
# can_transition_to helper
# ---------------------------------------------------------------------------


def test_can_transition_to_returns_true_for_valid():
    sm = AgentStateMachine(agent_id="agt-can", current_state=AgentState.ACTIVE)
    assert sm.can_transition_to(AgentState.RUNNING) is True
    assert sm.can_transition_to(AgentState.PAUSED) is True


def test_can_transition_to_returns_false_for_invalid():
    sm = AgentStateMachine(agent_id="agt-cannot", current_state=AgentState.CREATED)
    assert sm.can_transition_to(AgentState.RUNNING) is False
    assert sm.can_transition_to(AgentState.TERMINATED) is False
