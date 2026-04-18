"""
Agent Engine — the brain of AgentCompany.

This package contains everything needed to run AI agents:

  agent_loop.py        Main observe-think-act-reflect decision loop
  agent_manager.py     Agent lifecycle management (create/configure/activate/terminate)
  heartbeat.py         Heartbeat modes, event routing, trigger enqueueing
  state_machine.py     State machine with validated transitions
  context_manager.py   Context window management and compaction
  memory.py            Long-term memory backed by pgvector
  cost_tracker.py      Token budget tracking and cost recording
  llm/                 LLM provider adapters (Anthropic, OpenAI, Ollama)
  prompts/             Role-specific system prompts and action templates

Entry points for the runtime layer:
  AgentDecisionLoop   — run one agent invocation
  AgentManager        — manage the agent lifecycle
  HeartbeatService    — route events and ticks to the right agents
  CostTracker         — track spend per agent
  AgentMemory         — store and retrieve long-term memories
  ContextWindowManager — compact context when approaching token limits
"""

from .agent_loop import AgentContext, AgentDecisionLoop, LoopResult
from .agent_manager import AgentManager, AgentRecord
from .context_manager import ContextWindowManager
from .cost_tracker import BudgetStatus, CostTracker
from .heartbeat import (
    EventFilter,
    HeartbeatConfig,
    HeartbeatMode,
    HeartbeatService,
    TriggerMessage,
)
from .memory import AgentMemory, MemoryEntry
from .state_machine import (
    AgentState,
    AgentStateMachine,
    InvalidTransitionError,
    StateTransition,
    VALID_TRANSITIONS,
)

__all__ = [
    # Decision loop
    "AgentDecisionLoop",
    "AgentContext",
    "LoopResult",
    # Agent lifecycle
    "AgentManager",
    "AgentRecord",
    # State machine
    "AgentState",
    "AgentStateMachine",
    "InvalidTransitionError",
    "StateTransition",
    "VALID_TRANSITIONS",
    # Heartbeat / triggers
    "HeartbeatService",
    "HeartbeatMode",
    "HeartbeatConfig",
    "EventFilter",
    "TriggerMessage",
    # Memory
    "AgentMemory",
    "MemoryEntry",
    # Cost tracking
    "CostTracker",
    "BudgetStatus",
    # Context management
    "ContextWindowManager",
]
