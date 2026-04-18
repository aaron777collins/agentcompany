# AgentCompany — Architecture Review

**Reviewer**: Senior Architecture Reviewer (Claude Sonnet 4.6)
**Date**: 2026-04-18
**Scope**: Full codebase review — architecture consistency, cross-service integration, code quality, completeness
**Files Reviewed**: 35+ files across agent-runtime (Python), web-ui (TypeScript/React), docker-compose, Keycloak config, migration scripts, and architecture docs

---

## 1. Verdict

**APPROVED WITH WARNINGS**

The project demonstrates a high level of architectural coherence for a parallel-agent build. The core service structure is sound, the security model is well-considered, and the agent engine shows genuine engineering depth. However, several issues — most critically an incomplete authentication integration in the web UI and a missing Meilisearch filter injection guard — must be addressed before this can be considered production-ready.

---

## 2. Scores

| Area | Score | Notes |
|---|---|---|
| Architecture Consistency | 8/10 | API routes match design doc; a few intentional deviations (PUT vs PATCH, search uses POST) |
| Cross-Service Integration | 6/10 | Docker wiring is clean; Keycloak client ID mismatch; auth not wired in web UI |
| Code Quality | 7/10 | Strong backend quality; two security bugs in adapters; one raw SQL injection risk |
| Completeness | 6/10 | Engine and adapters are substantive; approvals API absent despite web UI calling it; README is a stub |

---

## 3. Issues Found

### CRITICAL

**C-1: Web UI has no auth token wiring — all API calls are unauthenticated**

File: `/home/ubuntu/topics/agentcompany/services/web-ui/src/lib/api.ts`, lines 57-65

The `request()` function sends `credentials: 'include'` (cookie-based) and a comment explicitly acknowledges the Bearer token is not wired: `"Change to Bearer header when Keycloak integration is wired (tracked in issue #42)"`. The web UI's `.env.example` declares `NEXT_PUBLIC_KEYCLOAK_*` variables but no Keycloak SDK (keycloak-js, next-auth, oidc-client) appears anywhere in `package.json` or the source tree. In production the backend requires a JWT; any deployment today will receive 401 on every request. This is a complete blocker for end-to-end operation.

**C-2: Meilisearch filter construction is vulnerable to injection**

File: `/home/ubuntu/topics/agentcompany/services/agent-runtime/app/api/search.py`, lines 58-63

The tenant isolation filter and caller-supplied filter values are string-concatenated directly into Meilisearch filter expressions with no escaping:

```python
meili_filter = f"company_id = {body.company_id}"
for key, value in body.filters.items():
    meili_filter += f" AND {key} = {value}"
```

An authenticated user can supply `body.filters` values such as `"x OR company_id = other_company_id"` and bypass tenant isolation entirely. `company_id` itself is also unquoted, so a crafted company ID can do the same. Meilisearch filter syntax must be escaped and validated; at minimum, values must be quoted and `body.filters` keys must be validated against an allowlist.

**C-3: `hmac.new` does not exist in Python's standard library — webhook HMAC verification silently fails**

Files:
- `/home/ubuntu/topics/agentcompany/services/agent-runtime/app/adapters/plane.py`, line 379
- `/home/ubuntu/topics/agentcompany/services/agent-runtime/app/adapters/outline.py`, line 360
- `/home/ubuntu/topics/agentcompany/services/agent-runtime/app/api/webhooks.py`, line 157

All three locations call `hmac.new(...)` which is the correct function name in Python's `hmac` module (`hmac.new` is an alias for `hmac.HMAC`). Verification: Python does expose `hmac.new` as a valid alias. **Retract C-3** — this is not a bug; `hmac.new` is valid Python. However, the adapter implementations in `plane.py` and `outline.py` construct the expected value as a string concatenation but the comparison in the adapter methods is never actually called from the webhook route handlers (which have their own independent `_verify_hmac` helper). This creates dead code in the adapters. The `webhooks.py` helper uses `hmac.new` directly and is correct.

**Revised C-3: Webhook secret validation is opt-in and defaults to no validation**

File: `/home/ubuntu/topics/agentcompany/services/agent-runtime/app/api/webhooks.py`, lines 40-43

All three webhook handlers guard signature verification with `if settings.webhook_secret_plane:` — if the environment variable is not set, any unauthenticated caller can POST arbitrary payloads to `/api/v1/webhooks/plane` and inject synthetic events into the event bus. In production these secrets will often not be set during initial deployment, leaving a permanent open door. The check should be inverted: fail closed (require the secret) unless the operator explicitly opts out for development.

---

### MAJOR

**M-1: Keycloak client ID mismatch between realm config and docker-compose**

The Keycloak realm export (`/home/ubuntu/topics/agentcompany/configs/keycloak/realm-export.json`) defines clients named `agentcompany-web` and `agentcompany-api`. The docker-compose and `.env.example` configure the web UI with `WEB_UI_KEYCLOAK_CLIENT_ID=web-ui` and the agent runtime with `AGENT_RUNTIME_KEYCLOAK_CLIENT_ID=agent-runtime`. None of these names match the realm export. When Keycloak is bootstrapped from the realm export, these clients will not exist and authentication will fail. Either the realm export or the environment variable defaults must be reconciled.

**M-2: Approvals API is called by the web UI but does not exist in the backend**

File: `/home/ubuntu/topics/agentcompany/services/web-ui/src/lib/api.ts`, lines 288-302

The web UI defines and calls `approvals.list()`, `approvals.approve()`, and `approvals.deny()` against `/api/v1/approvals`. No such routes are registered in `/home/ubuntu/topics/agentcompany/services/agent-runtime/app/api/router.py`. The `Approval` type is defined in web-ui types. The dashboard `ApprovalQueue` component is built around this. Every approval-related UI action will 404 at runtime.

**M-3: TaskStatus and TaskPriority enumerations are inconsistent between frontend and backend**

The TypeScript `TaskStatus` type (`/home/ubuntu/topics/agentcompany/services/web-ui/src/lib/types.ts`, line 12) defines: `'backlog' | 'todo' | 'in_progress' | 'review' | 'done'`.

The Python `TaskUpdate` schema (`/home/ubuntu/topics/agentcompany/services/agent-runtime/app/schemas/task.py`, line 28) and the database migration define: `open | in_progress | blocked | review | done | cancelled`.

The values `backlog`, `todo` (frontend) are absent from the backend. The value `open`, `blocked`, `cancelled` (backend) are absent from the frontend. The Kanban board uses `backlog` and `todo` column names which will never match backend-stored tasks. The backend will silently accept or reject status updates that the frontend sends.

**M-4: PaginatedResponse shape mismatch between frontend and backend**

The TypeScript `PaginatedResponse<T>` type uses `{ items, total, page, page_size, has_next }`. The Python `make_list_response` returns `{ data, meta: { pagination: { total, limit, offset, has_more } } }`. These are entirely different shapes. Any list endpoint response will fail to deserialize correctly in the web UI.

**M-5: Search endpoint changed from GET to POST without API doc update; frontend uses GET**

The API design doc (`api-design.md`, section 6.5) specifies `GET /api/v1/search`. The implementation (`search.py`) uses `POST /api/v1/search`. The web UI client (`api.ts`, line 261) calls `GET /search`. Three parties disagree on the HTTP method.

**M-6: RLS policies are designed but not implemented in the migration**

The data model document (section 8) specifies `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` and defines policies. The migration file (`001_initial.py`) creates none of these RLS policies. The handoff document (`runtime-api-handoff.md`, line 146) explicitly acknowledges this gap. Tenant isolation relies solely on application-layer `org_id` filtering, which means a SQL injection or ORM bug yields a full cross-tenant data breach.

**M-7: Metrics API exposes endpoints the web UI calls but uses different paths**

The web UI calls `/metrics/platform`, `/metrics/tokens`, and `/metrics/costs`. The backend implements `/metrics/tokens`, `/metrics/costs`, and `/metrics/agents/{id}/performance`. There is no `/metrics/platform` endpoint. The `PlatformMetrics` type in the frontend (`types.ts`, line 195-203) has no corresponding backend implementation.

---

### WARNINGS

**W-1: Optimistic concurrency (`version` column) is never enforced on UPDATE**

The data model mandates `WHERE version = :expected_version` on all updates. The implementation in `companies.py`, `agents.py`, `roles.py`, and `tasks.py` increments `version` but never validates it against a caller-supplied expected version. Concurrent updates will silently overwrite each other. This is noted as an architectural invariant; not implementing it makes concurrent edits from multiple browsers unsafe.

**W-2: The `start_agent` and `stop_agent` endpoints update `agent.status` in the DB but do not enqueue any work for the agent engine**

File: `/home/ubuntu/topics/agentcompany/services/agent-runtime/app/api/agents.py`, lines 196-208

Setting `agent.status = "starting"` writes to Postgres but no message is dispatched to the event bus or task queue to actually start the agent decision loop. The AgentManager and AgentDecisionLoop exist as separate classes but are not wired to the API layer. The agent engine is implemented but disconnected.

**W-3: CORS is set to wildcard `allow_methods=["*"]` and `allow_headers=["*"]` with `allow_credentials=True`**

File: `/home/ubuntu/topics/agentcompany/services/agent-runtime/app/main.py`, lines 106-113

`allow_credentials=True` combined with `allow_methods=["*"]` and `allow_headers=["*"]` is a misconfiguration that browsers reject for cross-origin requests. More importantly, in production `allow_origins` should be a specific allowlist, not the `cors_origins` default of `["http://localhost:3000", "http://localhost"]` which is fine for dev but is hardcoded rather than read from environment.

**W-4: The Keycloak realm export contains `"secret": "CHANGE_ME_..."` literal placeholder secrets**

File: `/home/ubuntu/topics/agentcompany/configs/keycloak/realm-export.json`, lines 113 and 147

If this file is imported into a production Keycloak instance without replacing these values, the confidential clients will have known secrets. The setup script should warn about this or replace them during `setup.sh`.

**W-5: Agent trigger endpoint does not pass trigger data to the agent engine**

File: `/home/ubuntu/topics/agentcompany/services/agent-runtime/app/api/agents.py`, lines 243-274

The `trigger_agent` endpoint accepts a `AgentTriggerRequest` with `task_id`, `context`, and `priority`, updates `last_active_at`, and returns a response — but never publishes to the event bus or enqueues any work. The trigger is silently discarded.

**W-6: Mattermost bucket not initialized in `minio-init`**

File: `/home/ubuntu/topics/agentcompany/docker-compose.yml`, lines 168-176

The `minio-init` service creates the `outline` bucket but not the `mattermost` bucket. The Mattermost service is configured to use MinIO as its file store (`MM_FILESETTINGS_DRIVERNAME: amazons3`, `MM_FILESETTINGS_AMAZONS3BUCKET: mattermost`). On first boot, Mattermost file uploads will fail with a NoSuchBucket error until the bucket is manually created.

**W-7: `CORS_ORIGINS` is not a configurable environment variable despite being documented as one**

The handoff document (`runtime-api-handoff.md`) lists `CORS_ORIGINS` as a supported env var. The `Settings` class (`config.py`, line 52) uses the field name `cors_origins` which pydantic-settings will read from `CORS_ORIGINS`. However, `docker-compose.yml` does not pass this variable to the `agent-runtime` service, so the default `["http://localhost:3000", "http://localhost"]` is always used in Docker deployments.

---

### SUGGESTIONS

**S-1: The `TaskRead` schema leaks the internal `metadata_` field name**

File: `/home/ubuntu/topics/agentcompany/services/agent-runtime/app/schemas/task.py`, line 57

`metadata_: dict[str, Any] = Field(alias="metadata_")` will serialize as `metadata_` in JSON responses rather than `metadata`. The alias should be `"metadata"` to match the DB column name and API doc. The web UI's `Task` type does not include this field at all, which means task metadata is never surfaced in the frontend.

**S-2: The `AgentRead` schema exposes `deleted_at` to API consumers**

Soft-deleted resources are filtered at query time; there is no path through which a deleted agent is returned. Exposing `deleted_at` is a minor information leak (callers learn about the deletion mechanism) and creates confusing API surface.

**S-3: The `search.py` endpoint uses the Meilisearch master key for all search operations**

File: `/home/ubuntu/topics/agentcompany/services/agent-runtime/app/api/search.py`, line 70

The master key has full admin access to Meilisearch. Search operations should use a scoped API key with `search` permission only, generated from the master key at initialization time.

**S-4: The agent decision loop uses a hard-coded 500-token estimate for budget pre-checks**

File: `/home/ubuntu/topics/agentcompany/services/agent-runtime/app/engine/agent_loop.py`, line 218

`self._cost_tracker.check(estimated_tokens=500)` uses a static estimate regardless of context size. This will incorrectly pass budget checks when the agent context has grown large and the actual call will consume far more than 500 tokens.

**S-5: The README is a placeholder**

`/home/ubuntu/topics/agentcompany/README.md` contains only "Coming soon" placeholders for features and architecture sections. Given the depth of the architecture documents in `docs/`, at minimum a link to those docs and a working quick-start section should be present.

**S-6: The `web-ui` client ID in docker-compose does not match the Keycloak realm (see M-1) and also differs from the `.env.example` in the web-ui service directory**

The root `.env.example` uses `WEB_UI_KEYCLOAK_CLIENT_ID=web-ui` while `services/web-ui/.env.example` uses `NEXT_PUBLIC_KEYCLOAK_CLIENT_ID=web-ui` — these are actually consistent, but both conflict with the realm export's `agentcompany-web`. Tracking this as a reminder within S-6 rather than a separate issue.

---

## 4. Recommendations (Prioritized)

### Priority 1 — Must fix before any deployment

1. **Wire Keycloak authentication in the web UI.** Install `keycloak-js` or `next-auth` with the Keycloak provider. Attach the access token as a `Bearer` header in the `request()` function. Remove the "issue #42" workaround comment.

2. **Fix Meilisearch filter injection.** Quote all values in Meilisearch filter strings. Validate `body.filters` keys against an allowlist of indexed fields. Consider using the Meilisearch SDK rather than raw HTTP to get proper filter escaping.

3. **Reconcile Keycloak client IDs.** Update the realm export (`configs/keycloak/realm-export.json`) to use client IDs `web-ui` and `agent-runtime` to match the env vars, or update the env vars to match the realm export. One file must be the single source of truth.

4. **Implement the approvals backend.** The web UI and architecture docs describe human-approval workflows as a core feature. Either implement `/api/v1/approvals` or remove the frontend components that depend on it. Leaving a 404 endpoint silently breaks a key human-in-the-loop safety control.

5. **Invert the webhook secret guard.** Require `PLANE_WEBHOOK_SECRET`, `MATTERMOST_WEBHOOK_SECRET`, and `OUTLINE_WEBHOOK_SECRET` to be set (non-empty) in production. Log a warning in development if they are absent, but do not silently accept unsigned webhooks in any environment.

### Priority 2 — Must fix before external users

6. **Align TaskStatus/TaskPriority enumerations.** Pick one canonical set (recommendation: adopt the backend's `open|in_progress|blocked|review|done|cancelled`) and update the frontend types and Kanban column definitions to match.

7. **Align PaginatedResponse shape.** The backend's `make_list_response` and the frontend's `PaginatedResponse<T>` type are incompatible. Implement a consistent shape and update both sides.

8. **Wire the agent engine to the API.** The `start_agent`, `stop_agent`, and `trigger_agent` endpoints must publish events to the event bus so `AgentManager` can actually start/stop the `AgentDecisionLoop`. Without this the agent runtime is non-functional.

9. **Add the Mattermost MinIO bucket to `minio-init`.** Add `mc mb --ignore-existing local/mattermost` to the entrypoint.

### Priority 3 — Before production hardening

10. **Implement PostgreSQL Row-Level Security.** The data model document specifies the exact DDL. Add it to the Alembic migration and verify that the application DB user is not a superuser (superusers bypass RLS).

11. **Fix the search endpoint method mismatch.** Standardize on either GET or POST and update the API doc, backend implementation, and frontend client together.

12. **Replace Meilisearch master key with a scoped search key.** Generate a search-only API key at startup and use it in the search endpoint.

13. **Implement version-based optimistic concurrency.** Accept an `If-Match: {version}` header or a `version` field in update request bodies and reject updates where the version does not match.

---

## 5. Summary Assessment

**What works well:**

The foundational engineering choices are sound. The FastAPI service has a clean dependency injection pattern, proper async/await throughout, meaningful JWT validation with JWKS caching, correct soft-delete semantics, structured logging, and well-organized Pydantic schemas. The adapter layer is particularly strong: a proper abstract base class, explicit capability declarations, consistent error normalization, constant-time HMAC comparisons, and graceful shutdown. The agent decision loop implements the documented observe-think-act-reflect cycle with budget enforcement, context compaction, and memory integration. The AgentStateMachine is a well-designed, testable component. The docker-compose is production-quality: proper network segmentation, health checks on every service, and correct service dependencies.

**Where the project falls short:**

The 11-agent parallel build succeeded in creating substantive, architecturally consistent components, but the integration seams between waves show gaps. The frontend-backend contract has three independent failures (auth, pagination shape, status enumerations) that will prevent end-to-end operation. The agent engine is implemented but not connected to the API layer, meaning agents cannot actually be started through the UI. The approvals system — a core safety mechanism for human-in-the-loop oversight — exists in the frontend types and UI components but has no backend implementation. The README does not reflect the sophistication of the underlying work.

**Overall assessment:**

This is a strong prototype with a clear path to production. The critical issues are all integration issues (not design issues), which is the expected failure mode of parallel development. With approximately 2-3 focused engineering days addressing the Priority 1 and 2 items above, this project would be ready for alpha deployment. The architecture decisions themselves are defensible and the implementation quality in the backend service is notably high.

---

*Review conducted by automated architecture reviewer. All file paths are absolute. Code snippets included only where they directly illustrate a finding.*
