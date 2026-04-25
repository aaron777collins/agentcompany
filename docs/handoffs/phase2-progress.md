# Phase 2 Progress — Agent Runtime Integration

**Date:** 2026-04-18
**Session scope:** Engine wiring + RLS middleware

---

## What was done in this session

### Task 1 — Agent engine wired to API endpoints

**New file:** `services/agent-runtime/app/engine/engine_service.py`

The existing `AgentManager` in `app/engine/agent_manager.py` uses asyncpg
directly (`pool.acquire()`), but the API layer uses SQLAlchemy `AsyncSession`.
Rather than porting one or the other, a new `AgentEngineService` facade was
created that:

- Accepts `AsyncSession` from the FastAPI dependency layer.
- Reuses `AgentStateMachine` for transition validation (shared engine logic).
- Writes `agent_transitions` rows via parameterized `text()` queries.
- Publishes `agent.state_changed` events to the `EventBus`.
- Delegates manual triggers to `HeartbeatService.enqueue_manual_trigger()`.

The service is instantiated once during lifespan startup (after Redis and the
event bus) and stored on `app.state.agent_manager`. `HeartbeatService` is
passed as `None` for now; APScheduler wiring is Phase 3 work.

**Modified:** `services/agent-runtime/app/main.py`

- Imports `AgentEngineService`.
- Creates the service instance in the lifespan context manager after the event
  bus is ready.
- Stores it on `app.state.agent_manager`.
- Calls `agent_manager.shutdown()` during teardown.

**Modified:** `services/agent-runtime/app/dependencies.py`

- Added `_get_agent_manager` dependency function that reads
  `app.state.agent_manager` and returns 503 if absent.
- Added `EngineService = Annotated[AgentEngineService, Depends(_get_agent_manager)]`
  type alias for clean injection.

**Modified:** `services/agent-runtime/app/api/agents.py`

- `start_agent`: Calls `engine.start_agent()` after setting `status='starting'`.
  On `EngineError`, reverts status to `'idle'` before re-raising as HTTP 502.
- `stop_agent`: Calls `engine.stop_agent()` after updating status.
  On `EngineError`, reverts to the previous status.
- `trigger_agent`: Calls `engine.trigger_agent()` which enqueues to Redis
  Streams. Response now includes `trigger_id` for tracking.
- All three endpoints now accept `engine: EngineService` as a dependency.

### Task 2 — RLS middleware

**Modified:** `services/agent-runtime/app/dependencies.py`

- `get_db` was updated to accept `request: Request` and issue
  `SET LOCAL app.current_company_id = :cid` (parameterized) when JWT claims
  are present on `request.state.token_claims`.
- `_get_token_claims` was updated to also accept `request: Request` and store
  the validated `TokenClaims` on `request.state.token_claims` so `get_db`
  can read it without a hard Depends() coupling.

The `SET LOCAL` scopes the GUC to the current transaction only, preventing
cross-connection bleed under concurrent load.

---

## Current state of all integrations

| Component | State | Notes |
|---|---|---|
| FastAPI app | Working | Lifespan startup complete |
| PostgreSQL (SQLAlchemy) | Working | Pool initialised, sessions per-request |
| Redis | Working | `app.state.redis` |
| Event bus | Working | Redis pub/sub, `app.state.event_bus` |
| Agent engine service | Wired | `app.state.agent_manager`; heartbeat disabled |
| RLS middleware | Wired | `SET LOCAL` per request; requires JWT with `company_id` |
| APScheduler / HeartbeatService | Not started | Phase 3 |
| Decision loop / TriggerConsumer | Not started | Phase 3 |
| Keycloak token validation | Working (code) | Requires Keycloak reachable at startup for JWKS |

---

## What works

- **Create agent** — creates DB row with `status='idle'`.
- **Start agent** — sets `status='starting'`, engine transitions to `'active'`,
  writes `agent_transitions` row (if table exists), publishes event.
- **Stop agent** — sets `status='stopping'`/`'idle'`, engine deregisters
  heartbeat (no-op without scheduler), writes transition row.
- **Trigger agent** — updates `last_active_at`, engine enqueues manual trigger
  to Redis Streams (`triggers:all` key). Returns `trigger_id`.
- **RLS context** — `SET LOCAL app.current_company_id` is set for every
  authenticated request that carries a `company_id` claim.
- **Error recovery** — all three lifecycle endpoints revert DB status on
  `EngineError` before returning HTTP 502.

## What does not yet work

- **Heartbeat ticking** — `HeartbeatService` with APScheduler is `None`.
  `always_on` and `scheduled` agents will not fire. `manual` and
  `event_triggered` modes work via the trigger endpoint.
- **Decision loop execution** — triggers are enqueued to Redis Streams but no
  consumer is running to dequeue them and invoke `AgentDecisionLoop`.
- **Heartbeat registration on start** — `register_agent()` is skipped while
  `HeartbeatService` is `None`.
- **RLS for unauthenticated paths** — health check and webhook endpoints do not
  set the company GUC; RLS policies allow this by design (those paths use
  service-account credentials or skip RLS entirely).
- **`agent_transitions` table** — the insert is wrapped in a non-fatal try/except.
  If the Alembic migration adding this table has not been run, transitions are
  logged but not persisted.

---

## Remaining tasks with estimates

| Task | Estimate | Notes |
|---|---|---|
| APScheduler lifespan wiring | 2 h | Add `AsyncIOScheduler` to `main.py`; pass to `HeartbeatService` and `AgentEngineService` |
| TriggerConsumer (Redis Streams reader) | 4 h | Background asyncio task; reads `triggers:all`, dispatches to `AgentDecisionLoop` |
| `AgentDecisionLoop` end-to-end | 1–2 days | Requires LLM adapters, tool permissions, cost tracking |
| Alembic migration — `agent_transitions` table | 1 h | Already partially written; need to verify columns match what `engine_service.py` inserts |
| RLS policy testing | 2 h | Integration test with real Postgres + `SET LOCAL` assertions |
| Keycloak integration test | 2 h | Validate JWKS fetch and `company_id` claim propagation |
| Auth middleware (optional) | 3 h | Move `_get_token_claims` into Starlette middleware so RLS works even on endpoints with no auth dependency |
