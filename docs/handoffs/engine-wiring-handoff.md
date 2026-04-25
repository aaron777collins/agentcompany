# Engine Wiring Handoff

**Date:** 2026-04-18
**Scope:** `services/agent-runtime/`

---

## What was built

### `app/engine/engine_service.py` (new)

`AgentEngineService` — SQLAlchemy-native facade for the API lifecycle calls.

The `AgentManager` in `agent_manager.py` talks to Postgres via asyncpg pool
(`pool.acquire()`). The FastAPI layer uses SQLAlchemy `AsyncSession`. Bridging
them in one object would require either running two connection pools per process
or patching the asyncpg pool out of `AgentManager`. Instead, `AgentEngineService`
owns the API-facing lifecycle operations and reuses only the pure-Python parts
of the engine (`AgentStateMachine`, `HeartbeatService`). The asyncpg-native
`AgentManager` remains intact for the decision loop runtime.

Public methods:
- `start_agent(agent_id, db, triggered_by)` — validates CONFIGURED → ACTIVE
  transition, writes `agents.status = 'active'`, appends `agent_transitions`,
  publishes event.
- `stop_agent(agent_id, db, drain, reason, triggered_by)` — writes transition
  log, calls `heartbeat.deregister_agent()` (no-op when scheduler is absent).
- `trigger_agent(agent_id, db, event_data, triggered_by)` — calls
  `heartbeat.enqueue_manual_trigger()` which writes to Redis Streams key
  `triggers:all`. Returns `trigger_id`.
- `shutdown()` — nullifies internal references; called during app teardown.

`EngineError` is a typed exception that endpoints catch and convert to HTTP 502.

### `app/main.py` changes

```python
from app.engine.engine_service import AgentEngineService

# inside lifespan, after event_bus is ready:
agent_manager = AgentEngineService(
    heartbeat_service=None,   # wired in Phase 3 when APScheduler is added
    event_bus=event_bus,
)
app.state.agent_manager = agent_manager

# shutdown:
await agent_manager.shutdown()
```

### `app/dependencies.py` changes

**`get_db`** now accepts `request: Request` and issues:
```python
await session.execute(
    text("SET LOCAL app.current_company_id = :cid"),
    {"cid": claims.company_id},
)
```
when `request.state.token_claims` is populated.

**`_get_token_claims`** stores the validated claims on `request.state`:
```python
request.state.token_claims = claims
```
This is what makes `get_db` able to read `company_id` without depending on the
auth dependency directly. FastAPI resolves both in parallel; the state write
happens-before any DB query because the auth dependency runs during parameter
injection, which completes before the first `await` in the endpoint body.

**`_get_agent_manager` / `EngineService`** — reads `app.state.agent_manager`,
returns 503 if absent.

### `app/api/agents.py` changes

All three lifecycle endpoints (`start_agent`, `stop_agent`, `trigger_agent`)
now accept `engine: EngineService` and call the corresponding method.

Error handling pattern used consistently:
```python
try:
    await engine.start_agent(...)
except EngineError as exc:
    agent.status = "idle"   # revert
    await db.flush()
    raise HTTPException(status_code=502, detail=f"Agent engine error: {exc}")
```

---

## How to wire HeartbeatService in Phase 3

1. Install `apscheduler>=3.10`: add to `requirements.txt`.
2. In `main.py` lifespan:
   ```python
   from apscheduler.schedulers.asyncio import AsyncIOScheduler
   from app.engine.heartbeat import HeartbeatService

   scheduler = AsyncIOScheduler()
   scheduler.start()
   heartbeat_service = HeartbeatService(
       agent_repo=<repo>,       # implement AgentRepository
       trigger_queue=redis_client,
       scheduler=scheduler,
   )
   agent_manager = AgentEngineService(
       heartbeat_service=heartbeat_service,
       event_bus=event_bus,
   )
   # shutdown:
   scheduler.shutdown(wait=False)
   ```
3. The `AgentRepository` must implement `get(agent_id)` returning an
   `AgentRecord`-compatible object, and `list_active_event_triggered()`.

---

## How to wire the TriggerConsumer in Phase 3

The trigger enqueue path (`triggers:all` Redis Stream) is ready. A consumer
needs to:
1. Run as a background asyncio task launched from lifespan.
2. Call `redis.xread({"triggers:all": "$"}, block=1000)` in a loop.
3. Deserialize each message with `TriggerMessage.from_redis_dict()`.
4. Call `AgentDecisionLoop.run(trigger)` in its own task.

---

## Known gaps

- `agent_transitions` insert is non-fatal. If the Alembic migration for that
  table has not run, transition records are silently dropped. Run all pending
  migrations before enabling in production.
- `SET LOCAL` only sets the GUC if the request carries a JWT with
  `company_id`. Service-to-service requests (no company scope) do not get RLS
  set. Ensure internal calls use the service account JWT or bypass RLS via
  a dedicated DB role.
- The `EventBus.publish()` call in `engine_service.py` uses `"agent_events"`
  as the company_id argument. The EventBus channels are namespaced by
  `company_id`; a proper value should be fetched from the agent row and passed
  through. This is a known simplification; fix before shipping SSE to the
  front-end.
