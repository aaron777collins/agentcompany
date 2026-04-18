# Agent Runtime API — Handoff

**Date**: 2026-04-18  
**Author**: Staff Engineer (agent)  
**Service**: `services/agent-runtime/`  
**Status**: Implementation complete — ready for integration testing

---

## What Was Built

The core Agent Runtime service: a FastAPI application that exposes the full management and event API described in `docs/architecture/agent-runtime.md` and `docs/architecture/api-design.md`.

### Files Written

```
services/agent-runtime/
├── pyproject.toml               Python project metadata and dependency list
├── requirements.txt             Flat requirements file for Docker builds
├── Dockerfile                   Multi-stage build (builder + runtime)
├── alembic.ini                  Alembic config (DATABASE_URL injected at runtime)
├── alembic/
│   ├── env.py                   Async Alembic env (asyncpg, reads Settings)
│   └── versions/001_initial.py  Creates all core tables + metrics schema
├── app/
│   ├── __init__.py
│   ├── main.py                  FastAPI factory, lifespan, health endpoint
│   ├── config.py                pydantic-settings Settings, get_settings()
│   ├── dependencies.py          Shared Depends() callables (auth, db, pagination)
│   ├── logging_config.py        Structured JSON formatter
│   ├── core/
│   │   ├── database.py          SQLAlchemy 2.0 async engine + get_db()
│   │   ├── security.py          Keycloak JWT validation, JWKS caching
│   │   └── events.py            Redis pub/sub event bus (publish + SSE subscribe)
│   ├── models/
│   │   ├── base.py              DeclarativeBase, TimestampMixin, ULID helper
│   │   ├── company.py           Company ORM model
│   │   ├── agent.py             Agent ORM model
│   │   ├── role.py              Role ORM model (self-referential reports_to)
│   │   ├── task.py              Task ORM model (subtasks, soft-delete)
│   │   ├── event.py             Immutable event log model
│   │   └── token_usage.py       Append-only token usage in metrics schema
│   ├── schemas/
│   │   ├── common.py            DataResponse[T], ListResponse[T], ErrorResponse
│   │   ├── company.py           CompanyCreate / CompanyUpdate / CompanyRead
│   │   ├── agent.py             AgentCreate / AgentUpdate / AgentRead + LLMConfig
│   │   ├── role.py              RoleCreate / RoleUpdate / RoleRead
│   │   └── task.py              TaskCreate / TaskUpdate / TaskRead / TaskAssign
│   └── api/
│       ├── router.py            Aggregates all sub-routers
│       ├── companies.py         POST/GET/PUT/DELETE /api/v1/companies
│       ├── agents.py            CRUD + start/stop/trigger /api/v1/agents
│       ├── roles.py             CRUD /api/v1/roles
│       ├── tasks.py             CRUD + assign /api/v1/tasks
│       ├── search.py            POST /api/v1/search (proxies to Meilisearch)
│       ├── events.py            GET /api/v1/events + SSE /api/v1/events/stream
│       ├── metrics.py           GET /api/v1/metrics/tokens, costs, performance
│       └── webhooks.py          POST /api/v1/webhooks/plane|outline|mattermost
```

**Not written** (owned by other agents):
- `app/engine/` — decision loop, state machine, heartbeat, cost tracker
- `app/adapters/` — Plane, Outline, Mattermost, Meilisearch adapters

---

## Key Design Choices

### Authentication
- All API routes (except `/health` and `/api/v1/webhooks/*`) require `Authorization: Bearer <jwt>`.
- `app/core/security.py` fetches Keycloak's JWKS once at startup and caches for 1 hour. No Keycloak call on the hot path.
- `TokenClaims` dataclass carries `sub`, `org_id`, `is_agent`, `roles`, etc. for downstream checks.
- Two dependency shortcuts: `OrgMember` (read access) and `OrgAdmin` (write/delete access).

### Webhook Authentication
- Plane and Outline use HMAC-SHA256 (`X-Plane-Signature`, `X-Outline-Signature`).
- Mattermost uses a shared token in the request body (`token` field).
- All verification uses `hmac.compare_digest()` — constant-time to prevent timing attacks.
- Webhook endpoints are exempt from JWT auth by design (tools cannot send JWTs).

### Database
- SQLAlchemy 2.0 async with asyncpg driver.
- `DATABASE_URL` is normalised from `postgres://` to `postgresql+asyncpg://` automatically.
- Sessions are per-request, committed on success, rolled back on exception (via `get_db()`).
- All business entities use ULID primary keys with entity prefix (`cmp_`, `agt_`, `rol_`, etc.).
- Soft deletes: `deleted_at` timestamp; queries always filter `deleted_at IS NULL`.

### Pagination
- Resource lists (`/companies`, `/agents`, etc.): offset-based with `limit` (max 100) and `offset`.
- Event log (`/events`): cursor-based using the last event's `id` as the cursor.
- `make_list_response()` in `schemas/common.py` builds the standard list envelope.

### Event Bus
- `EventBus` in `app/core/events.py` wraps Redis pub/sub.
- Channel naming: `events:{company_id}`.
- SSE `/api/v1/events/stream` subscribes to the bus and streams events to clients.
- Bus failures are non-fatal — events are already persisted to Postgres before publishing.

### Alembic
- `alembic/env.py` reads `DATABASE_URL` from `Settings` — no hard-coded credentials.
- Migration `001_initial.py` creates all public-schema tables and the `metrics` schema.
- Run `alembic upgrade head` before starting the service (or at startup via a one-time job).

---

## Environment Variables Required

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | `postgres://...` or `postgresql+asyncpg://...` |
| `REDIS_URL` | Yes | `redis://:password@host:port` |
| `SECRET_KEY` | Yes | 32-byte hex; used for internal HMAC |
| `KEYCLOAK_URL` | Yes | e.g. `http://keycloak:8080/auth` |
| `KEYCLOAK_REALM` | Yes | e.g. `agentcompany` |
| `KEYCLOAK_CLIENT_ID` | No | default `agent-runtime` |
| `MEILISEARCH_URL` | No | default `http://meilisearch:7700` |
| `MEILISEARCH_MASTER_KEY` | No | required if Meilisearch is secured |
| `WEBHOOK_SECRET_PLANE` | No | HMAC secret for Plane webhooks |
| `WEBHOOK_SECRET_MATTERMOST` | No | Token for Mattermost outgoing webhooks |
| `WEBHOOK_SECRET_OUTLINE` | No | HMAC secret for Outline webhooks |
| `CORS_ORIGINS` | No | JSON array, default `["http://localhost:3000"]` |
| `LOG_LEVEL` | No | default `INFO` |
| `APP_ENV` | No | `development` or `production` |

---

## What the Next Agent Should Do

### If you are the integration-testing agent:
1. `docker compose up -d postgres redis` then `alembic upgrade head`.
2. Start the service: `uvicorn app.main:app --reload`.
3. Hit `GET /health` — should return `{"status": "ok", "redis": "ok"}`.
4. Register a test Keycloak realm and create a test token; call `POST /api/v1/companies`.
5. Verify the SSE stream at `GET /api/v1/events/stream` receives events after mutations.

### If you are the engine agent integrating with the API layer:
- The `app.state.event_bus` (`EventBus`) is available on the `Request` object.
- Call `event_bus.publish(company_id, event_dict)` after any state-changing run.
- The `DBSession` dependency is `AsyncSession` from SQLAlchemy — import from `app.dependencies`.
- Models are in `app.models`; schemas in `app.schemas`.

### Remaining gaps:
- Metrics SSE / real-time dashboard feed is not yet wired — the event bus handles it but a metrics-specific SSE endpoint may be needed for the web-ui charting library.
- Token usage records are written by the engine (cost_tracker.py) — no write endpoint is exposed intentionally (append-only from the engine layer only).
- Idempotency-Key header caching is not yet implemented — described in api-design.md §8 as a Redis-backed cache; a middleware or per-endpoint decorator is the right approach.
- RLS (`SET LOCAL app.current_org_id`) for defence-in-depth tenant isolation is not yet wired to every session — the application-layer `org_id` filter is the current guard.
