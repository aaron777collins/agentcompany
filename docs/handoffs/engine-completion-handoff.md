# Engine Completion Handoff

**Date:** 2026-04-18
**Phase:** Engine wiring — Phase 3 completion

## What was done

This session wired the remaining pieces that allow agents to actually run.
All changes are in `services/agent-runtime/`.

### Files created

| File | Purpose |
|---|---|
| `app/engine/trigger_consumer.py` | Consumes `triggers:all` Redis Stream and dispatches to engine |
| `app/engine/tool_registry.py` | `AgentTool`, `ToolRegistry`, `RegistryToolExecutor`, `ToolExecutionResult` |
| `app/engine/tool_definitions.py` | Maps adapter methods to LLM-callable tool descriptions per company |

### Files modified

| File | Change |
|---|---|
| `app/main.py` | Wires APScheduler, HeartbeatService, TriggerConsumer into lifespan |
| `app/engine/engine_service.py` | Added `set_heartbeat_service`, `dispatch_trigger`, `trigger_by_event` |
| `app/engine/agent_loop.py` | Added `from_registry()` classmethod; `run()` now accepts `AgentTool` list |
| `app/engine/__init__.py` | Exports new public symbols |
| `requirements.txt` | Added `apscheduler>=3.10` |

## Architecture decisions

### Startup order in lifespan (main.py)

The startup sequence is: DB → Redis → EventBus → AgentEngineService →
APScheduler → HeartbeatService → TriggerConsumer → inject heartbeat into engine.

This order matters because:
- HeartbeatService needs a running APScheduler to register jobs.
- TriggerConsumer needs the engine to have its heartbeat injected so
  `dispatch_trigger` can publish to the event bus.
- The engine is constructed before the heartbeat service so the
  `_StubAgentRepo` comment is accurate — it cannot query agents yet.

`set_heartbeat_service()` was added to allow late injection without
reconstructing the engine (which is already stored on `app.state`).

### _StubAgentRepo

`HeartbeatService.handle_platform_event()` calls
`agent_repo.list_active_event_triggered()` to fan out webhook events to
matching agents. The existing implementation was designed for an asyncpg repo,
but the API layer uses SQLAlchemy. Rather than bridging two ORMs inside
HeartbeatService, the stub returns an empty list and webhook-driven event
routing goes through `engine_service.trigger_by_event()` instead.

This is correct behaviour for Phase 3 — the HeartbeatService scheduler path
(always_on / scheduled) is fully functional; the webhook event path uses the
engine service route.

### trigger_by_event vs handle_platform_event

There are now two event routing paths:
1. **Webhook path** (`app/api/webhooks.py` → `HeartbeatService.handle_platform_event`):
   Full HMAC-verified, filter-matched routing. Currently uses the stub repo so
   it does nothing with event_triggered agents.
2. **Stream path** (`TriggerConsumer._handle_event` → `engine_service.trigger_by_event`):
   Reads from `agent_events` stream (where the spec's TriggerConsumer was
   intended to operate). Queries the DB directly using the session factory.

Phase 4 should consolidate these. The recommended path is to have webhook
handlers publish to `agent_events` stream and have the TriggerConsumer call
`trigger_by_event` — which is exactly what the spec's TriggerConsumer skeleton
intended.

### ToolRegistry and tool_definitions.py

`build_registry_for_company(adapter_registry, company_id)` is the entry point.
It skips tools whose adapter is not registered — the LLM prompt only shows tools
that actually exist, preventing confusing "tool not found" errors.

Role filtering is case-insensitive. An empty `required_roles` list means
the tool is available to all roles (used for communication and search tools).

### AgentTool → ToolDefinition conversion

`ToolDefinition` is the LLM-layer type; `AgentTool` is the registry-layer type
that also carries the handler and role permissions. Two conversion paths:
1. `ToolRegistry.to_llm_definitions(role)` — explicit conversion at call site.
2. `AgentDecisionLoop.run()` — accepts either type and auto-converts when it
   detects the `handler` attribute.

The auto-conversion in `run()` allows callers to pass the output of
`registry.get_tools_for_role(role)` directly without extra ceremony.

## What is NOT done (Phase 4 work)

### Full decision loop execution from trigger

`dispatch_trigger()` currently logs and publishes an SSE event but does not
actually start a decision loop run. Completing this requires:
1. Loading the agent's full config (LLM adapter, system prompt, role) from DB.
2. Constructing a `BaseLLMAdapter` for the agent's configured provider.
3. Building a `ToolRegistry` via `build_registry_for_company`.
4. Constructing an `AgentDecisionLoop.from_registry(...)`.
5. Calling `loop.run(agent_id, company_id, system_prompt, tools, trigger)`.
6. Persisting the `LoopResult` to `agent_runs` table.

### Real AgentRepository for HeartbeatService

Replace `_StubAgentRepo` in `main.py` with a real async repo that queries
`agents WHERE status IN ('active', 'idle') AND trigger_mode = 'event_triggered'`.
This enables the webhook → HeartbeatService → trigger stream path to work for
event_triggered agents.

### agent_runs table

The `agent_runs` table is needed to persist `LoopResult`. It was referenced
in the architecture spec but not yet in the migrations. Add it before wiring
decision loop execution.

### TriggerConsumer stream key mismatch

The spec's TriggerConsumer example used `agent_events` as the stream key,
but `HeartbeatService` writes to `triggers:all`. The implementation uses
`triggers:all` (matching HeartbeatService) for agent trigger dispatch.

If the intent is to also consume from a separate `agent_events` stream for
webhook-sourced events, a second consumer or a merged stream should be
introduced in Phase 4.

## Testing

No automated tests were added in this session. Before Phase 4 execution, add:

- `test_trigger_consumer.py` — mock Redis xreadgroup, verify dispatch_trigger is called
- `test_tool_registry.py` — verify role filtering, executor error handling
- `test_tool_definitions.py` — verify tools registered per adapter availability
- `test_engine_service_trigger_by_event.py` — mock session factory, verify trigger fan-out

## How to verify startup

With Redis and Postgres running:

```
uvicorn app.main:app --reload
```

Expected log sequence:
```
Database connection pool initialised
Redis client initialised
Event bus initialised
Agent engine service initialised
APScheduler started
HeartbeatService initialised
TriggerConsumer started (stream=triggers:all group=agent_triggers ...)
```

GET /health should return `{"status": "ok", "redis": "ok"}`.
