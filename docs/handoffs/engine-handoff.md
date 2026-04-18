# Agent Engine Handoff

**Date**: 2026-04-18
**Author**: Staff Engineer (implementation)
**Status**: Implementation complete
**Recipient**: Engineering team integrating the engine into the runtime service

---

## What Was Built

The agent engine at `services/agent-runtime/app/engine/`. This is the decision-making
core of the system — the code that runs AI agents.

| File | Purpose |
|---|---|
| `__init__.py` | Public API surface — imports all key classes |
| `agent_loop.py` | Observe-Think-Act-Reflect decision loop |
| `agent_manager.py` | Agent lifecycle (create / configure / activate / pause / terminate) |
| `heartbeat.py` | Trigger modes, event routing, Redis Stream enqueueing |
| `state_machine.py` | State machine with validated transitions and audit records |
| `context_manager.py` | Context window compaction at 80% threshold |
| `memory.py` | Long-term memory via pgvector + entity facts via asyncpg |
| `cost_tracker.py` | Per-agent token budgets with Redis counters + DB persistence |
| `llm/__init__.py` | LLM package exports |
| `llm/types.py` | Shared types: LLMResponse, ToolCall, ToolDefinition, pricing tables |
| `llm/base.py` | BaseLLMAdapter ABC — the contract all adapters must fulfill |
| `llm/anthropic.py` | Anthropic Claude adapter (primary) |
| `llm/openai.py` | OpenAI GPT adapter |
| `llm/ollama.py` | Ollama local model adapter |
| `prompts/__init__.py` | Prompt package exports |
| `prompts/system_prompts.py` | Role-specific system prompts (CEO, CTO, CFO, PM, Developer, Designer, QA) |
| `prompts/templates.py` | Action templates (task analysis, delegation, escalation, status update, code review, standup) |

---

## Architecture Decisions Implemented

### State Machine (state_machine.py)

Implemented the full transition graph from `agent-framework.md`, plus an ERROR state
for recoverable failures:

```
CREATED -> CONFIGURED -> ACTIVE <-> RUNNING
                           |           |
                           v           v
                         PAUSED     ERROR
                           |           |
                           v           v
                       TERMINATED  TERMINATED
```

`VALID_TRANSITIONS` is a `frozenset` — the authoritative rule set. `AgentStateMachine`
validates before applying; `AgentManager` owns the side effects (DB write + event publish).
Every transition is appended to `agent_transitions` (event-sourced, never updated).

### Decision Loop (agent_loop.py)

Implements the spec's Observe -> Think -> Act -> Reflect cycle exactly.
Key invariants enforced in code:

1. **Budget check before every LLM call** — inside the loop, not just at run start.
   A run that starts under budget can exceed it by step 3 if token spend is heavy.
2. **Context compaction before every LLM call** — `maybe_compact()` is called each
   iteration; it's a no-op below 80% so the overhead is minimal.
3. **Tool results appended before looping back** — the LLM sees tool outputs on the
   next Think step, not the same step.
4. **Reflect on all exits** — both clean completion and max_steps store a memory summary.
   This ensures long-term memory accumulates even from incomplete runs.

### Context Window Management (context_manager.py)

Compacts at 80% of the model's context window. Target after compaction: 50%.
Always preserves the last 4 messages (MIN_MESSAGES_TO_KEEP) for conversational
coherence. Archives original messages to long-term memory before discarding them
so nothing is truly lost.

Archiving failure is non-fatal — compaction proceeds regardless. A crash between
archiving and compaction would result in the original messages being lost without
archival, but this is acceptable given the rarity and the presence of the Redis
key for the run in long-term memory.

### LLM Adapters (llm/)

All three adapters (Anthropic, OpenAI, Ollama) inherit from `BaseLLMAdapter`.
The decision loop only holds a `BaseLLMAdapter` reference — providers are swappable.

Key design detail: Anthropic's tool result format differs from OpenAI's.
`AnthropicAdapter._normalize_messages()` handles the conversion:
- Internal "tool" role messages become `user` role with `tool_result` content blocks
- Consecutive user messages are merged (Anthropic rejects alternating same-role messages)
`OpenAIAdapter._normalize_messages()` passes "tool" role messages through unchanged.

Cost calculation lives in each adapter (it has the pricing table) and is returned
in every `LLMResponse.cost_usd`. The budget tracker consumes this directly.

### Heartbeat System (heartbeat.py)

Four modes as specified. `HeartbeatService` is stateless with respect to the agents
it manages — it talks to the agent repo and Redis, not an in-memory registry.
This means the heartbeat service can restart without losing registration state
(APScheduler re-registers on startup from the DB).

`_matches()` evaluates: source, event_type, assigned_to (agent's platform_user_id),
priority rank, and content regex patterns (all conditions must pass, ORed across
regex patterns). Priority rank is ordered: low=0, medium=1, high=2, critical=3.

### Memory (memory.py)

`AgentMemory` handles both storage tiers:
- Vector store (pgvector): semantic similarity search via `search()`
- Relational store (asyncpg): structured entity facts via `store_entity()` / `get_entity()`

The embedder is injected as a callable. Both sync and async callables are supported
(sync embedders are dispatched to a thread pool via `run_in_executor`).

Memory namespace is enforced: `forget()` includes `agent_id` in the DELETE query so
an agent cannot delete another agent's memories, even if it learns another agent's
memory_id.

### Cost Tracker (cost_tracker.py)

Redis counters use `INCRBYFLOAT` for atomic updates. The pipeline batches 4 increments
+ 4 EXPIRE calls per LLM call. DB persistence is best-effort: a failed write logs a
warning and continues — Redis counters remain accurate for budget enforcement.

Budget check (`check()`) reads 4 Redis keys and returns immediately. It does not write.
Calling it before every LLM call adds ~4 Redis round trips per loop step — acceptable
given the LLM call latency (1-30s) that follows.

---

## What the Caller Must Provide

The engine components are dependency-injected. The runtime layer (dispatcher,
FastAPI app) must wire these up at startup.

### AgentDecisionLoop requires:
- `llm_adapter: BaseLLMAdapter` — from the LLM registry
- `tool_executor: Any` — implements `execute(agent_id, tool_name, arguments, call_id)` returning an object with `.output: str` and `.success: bool`
- `memory: AgentMemory` — constructed with a db_pool, vector_store, and embedder
- `cost_tracker: CostTracker` — constructed with agent_id, company_id, db_pool, redis
- `state_machine: AgentStateMachine` — constructed with agent_id and current state
- `context_manager: ContextWindowManager` — constructed with adapter and memory

### AgentManager requires:
- `agent_repo: Any` — must implement `get(agent_id)`, `create(agent)`, `list_active_event_triggered()`
- `heartbeat_service: HeartbeatService`
- `event_bus: Any` — must implement `publish(event_type, payload)` (async)
- `db_pool: Any` — asyncpg Pool

### HeartbeatService requires:
- `agent_repo: Any` — must implement `list_active_event_triggered()`
- `trigger_queue: Any` — Redis asyncio client (for XADD)
- `scheduler: Any` — APScheduler AsyncIOScheduler

### AgentMemory requires:
- `agent_id: str`
- `db_pool: Any` — asyncpg Pool
- `vector_store: Any` — must implement `upsert(table, id, agent_id, category, content, embedding, metadata)`, `search(table, agent_id, query_embedding, top_k, categories)`, `delete(table, id, agent_id)`
- `embedder: Callable[[str], list[float]]` — sync or async

### CostTracker requires:
- `agent_id: str`, `company_id: str`
- `db_pool: Any` — asyncpg Pool
- `redis: Any` — redis.asyncio client

---

## Database Tables Expected

The engine writes to these tables (must exist before the service starts):

```sql
-- State transition audit trail (append-only)
CREATE TABLE agent_transitions (
    id              BIGSERIAL PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    from_state      TEXT NOT NULL,
    to_state        TEXT NOT NULL,
    reason          TEXT NOT NULL,
    triggered_by    TEXT,
    transitioned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Long-term memory entries (requires pgvector extension)
CREATE TABLE agent_memories (
    id          TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    category    TEXT NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(1536),   -- adjust dimension to match your embedder
    metadata    JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON agent_memories USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX ON agent_memories (agent_id, category);

-- Entity facts (key-value store for structured agent knowledge)
CREATE TABLE agent_entities (
    agent_id    TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    facts       JSONB NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (agent_id, entity_type, entity_id)
);

-- Token usage (metrics schema, append-only)
-- See data-model.md for the full metrics.token_usage definition
```

---

## Things That Will Break If Not Followed

### 1. Budget check is inside the loop, not at run start

`CostTracker.check()` is called at the top of every loop iteration in
`AgentDecisionLoop._loop()`. Do not cache or hoist this check. A run that starts
under budget can exceed it if it runs many steps.

### 2. State machine transitions must go through AgentManager

`AgentStateMachine` is in-memory. `AgentManager._transition()` is the only code
path that writes to the DB and publishes the event. If you bypass `AgentManager`
(e.g. calling `AgentStateMachine.transition()` directly), the DB state diverges
from memory state.

### 3. Tool permission checks are NOT in the engine

The engine calls `tool_executor.execute()` without checking permissions. Permission
enforcement lives in the tool sandbox layer (outside this package). The sandbox must
check `agent.capabilities.allowed_tools` before every call. The engine trusts the
executor's result but does not grant permission.

### 4. Context window compaction is best-effort for archiving

If memory archiving fails during compaction, the compaction still proceeds. The
original messages are discarded. This is intentional — a broken memory store must
not block agent execution. Monitor `agent_memories` write errors separately.

### 5. Redis counters and DB usage records can diverge

If `_persist_usage()` fails (DB down), Redis counters still increment correctly.
Budget enforcement remains accurate. The `metrics.token_usage` table may be missing
records until the DB recovers. The mismatch resolves automatically once the DB is
available again, since Redis counters are the source of truth for budget decisions.

---

## Not Implemented Here (Out of Scope for This Package)

- **Tool implementations** — `ProjectManagementTool`, `ChatTool`, `DocumentationTool`,
  `CodeTool`, `AnalyticsTool`, `SearchTool`. These are in `app/adapters/tools/`.
- **pgvector store implementation** — The `AgentMemory` expects a duck-typed vector
  store. The concrete pgvector adapter lives in `app/adapters/memory/pgvector.py`.
- **LLM registry** — `build_registry(settings)` described in `llm-adapters.md` should
  live in the runtime startup code, not the engine package.
- **Webhook receivers** — Plane, Mattermost, Outline webhook handlers call
  `HeartbeatService.handle_platform_event()`. Those handlers live in `app/api/webhooks.py`.
- **TriggerConsumer / TaskDispatcher** — These workers consume the Redis streams that
  `HeartbeatService` writes to. They live in `app/workers/` and `app/core/`.
- **Prompt template rendering via Jinja2** — The prompts in `prompts/system_prompts.py`
  are plain Python functions. If per-company template customization is needed
  (overrides stored in DB), a `PromptTemplateManager` using Jinja2 should be built
  in the adapters layer and call `get_system_prompt()` for defaults.

---

## Recommended Integration Test (First PR)

Run an end-to-end agent loop with stub dependencies:

```python
from unittest.mock import AsyncMock, MagicMock
from app.engine import AgentDecisionLoop, AgentStateMachine, AgentState
from app.engine.llm.types import LLMResponse, StopReason

# Stub memory, cost tracker, state machine, context manager, tool executor
# Wire up AnthropicAdapter with a real API key
# Send trigger: {"type": "manual", "payload": {"title": "List today's tasks"}}
# Verify LoopResult.outcome == "completed"
```

This validates the full Observe->Think->Act->Reflect path before adding real tools.

---

## Open Questions for Next Team

1. **Vector dimension**: `agent_memories.embedding` uses `vector(1536)` as a placeholder.
   Confirm the dimension of the embedder you will use (e.g. `text-embedding-3-small` = 1536,
   `text-embedding-3-large` = 3072).

2. **Embedder selection**: `AgentMemory` accepts any callable. Which embedding model
   will be used in production? A cheap, fast embedder (e.g. `text-embedding-3-small`) is
   recommended for the high-volume memory writes that occur at the end of every run.

3. **Global trigger stream key**: `HeartbeatService.GLOBAL_STREAM = "triggers:all"`.
   The `TriggerConsumer` (in `app/workers/`) must use the same key. Ensure these are
   read from a shared config constant, not hardcoded independently.

4. **Company-level budget**: `CostTracker` enforces per-agent budgets only. The
   architecture doc specifies a company-wide budget check too. This is implemented
   via Redis keys scoped to `company_id` — the pattern is present in `cost_tracker.py`
   but the company-level limits are not plumbed from agent config. The caller of
   `CostTracker` should add a second check against company-wide limits using the
   same Redis counter approach.
