# Backend Fixes Handoff

**Date:** 2026-04-18
**Scope:** `services/agent-runtime/` — critical security fixes and major API alignment fixes from the architecture review.

---

## What Was Fixed

### C-2 — Meilisearch filter injection (SECURITY)
**File:** `app/api/search.py`

The previous code string-concatenated caller-supplied filter key/value pairs directly into Meilisearch filter expressions, enabling cross-tenant data access via payloads like `"x OR company_id = victim_company"`.

**Fix:**
- Added `_ALLOWED_FILTER_KEYS = frozenset({"status", "priority", "source", "assignee"})` — any other key is rejected with 400.
- Added `_FORBIDDEN_VALUE_PATTERN` regex that rejects values containing `OR`, `AND`, `NOT`, `TO`, `=`, `!=`, `>`, `<`, `(`, `)`, `"`.
- Both `_validate_filter_key()` and `_validate_filter_value()` raise `HTTP 400` with a specific message on violation.
- The `company_id` tenant anchor filter is also passed through `_validate_filter_value()` and is now double-quoted in the expression.
- User-supplied filter values are now quoted: `key = "value"` instead of bare `key = value`.

---

### C-3 — Webhook secrets must be required
**File:** `app/api/webhooks.py`

All three handlers (`plane_webhook`, `outline_webhook`, `mattermost_webhook`) previously only validated signatures *if* the corresponding env var was set. If the var was absent, any caller could inject events.

**Fix:** Each handler now checks for a non-empty secret **before** doing anything else. If the secret is not configured, it raises `HTTP 503 Service Unavailable` with an explicit message. The condition was changed from `if secret: verify()` to `if not secret: raise 503` followed by unconditional `verify()`.

---

### M-2 — /approvals endpoints
**New files:**
- `app/models/approval.py` — SQLAlchemy `Approval` model (`id`, `org_id`, `company_id`, `agent_id`, `task_id`, `action_summary`, `action_payload`, `status`, `decided_by`, `decided_at`, `decision_note`)
- `app/schemas/approval.py` — `ApprovalRead` (response) and `ApprovalDecision` (request body for approve/deny)
- `app/api/approvals.py` — three endpoints:
  - `GET /api/v1/approvals` — paginated list, filterable by `company_id`, `status`, `agent_id`
  - `POST /api/v1/approvals/{id}/approve` — marks pending approval approved; 409 if already decided
  - `POST /api/v1/approvals/{id}/deny` — marks pending approval denied; 409 if already decided

**Modified:** `app/api/router.py` — imports `approvals` and registers `approvals.router` at `/approvals`.

**Note:** A database migration is needed to create the `approvals` table. The model uses standard `TimestampMixin` columns and foreign keys to `companies`, `agents`, and `tasks`.

---

### M-3 — TaskStatus enum aligned to frontend
**Files:** `app/models/task.py`, `app/schemas/task.py`, `app/api/tasks.py`

The backend used `open|in_progress|blocked|review|done|cancelled`; the frontend kanban board expects `backlog|todo|in_progress|review|done|cancelled`.

**Fix:**
- `app/models/task.py`: comment and default changed from `"open"` to `"backlog"`.
- `app/schemas/task.py`: `TaskUpdate.status` Literal updated to `"backlog", "todo", "in_progress", "review", "done", "cancelled"`.
- `app/api/tasks.py`: `create_task` initial status changed from `"open"` to `"backlog"`.

**Migration note:** Existing rows with `status = 'open'` or `status = 'blocked'` need a data migration. Suggested mapping: `open -> backlog`, `blocked -> in_progress` (or leave as-is and accept that old rows won't match kanban columns until manually re-triaged).

---

### M-4 — Pagination response shape aligned to frontend
**File:** `app/schemas/common.py`

The frontend expects `{items, total, page, page_size, has_next}` at the response top level. The backend was returning `{data: [...], meta: {pagination: {total, limit, offset, has_more}}}`.

**Fix:**
- `ListResponse` generic class fields changed: `data` renamed to `items`; nested `meta.pagination` flattened to top-level `total`, `page`, `page_size`, `has_next`.
- `make_list_response()` helper updated to return the new shape. `page` is 1-based, derived from `offset // limit + 1`.
- All routes that call `make_list_response()` (agents, tasks, approvals, companies, roles) inherit the fix automatically — they return `dict` and delegate to this helper.

**Breaking change:** Any existing client that parsed the old `{data, meta.pagination}` envelope will need to update. The internal `ListMeta` / `PaginationMeta` Pydantic classes are retained for potential internal use but are no longer referenced by `ListResponse`.

---

### M-5 — Search endpoint method (no change needed)
**File:** `app/api/search.py`

The spec asks to verify the frontend sends POST. The implementation already uses `POST /api/v1/search/`. No code change was made. A comment noting this is correct as-is is implicit in the existing docstring.

---

### M-7 — /metrics/platform endpoint
**File:** `app/api/metrics.py`

The frontend called `/api/v1/metrics/platform` but the endpoint did not exist.

**Fix:** Added `GET /metrics/platform` handler (`platform_stats`). It requires `OrgAdmin` (dashboards showing cross-company stats should be restricted to admins). It runs a single CTE query that aggregates:
- `total_companies` — non-deleted companies in org
- `total_agents` / `active_agents` — agents where `status IN ('active', 'starting')`
- `total_tasks` — non-deleted tasks in org
- `total_tokens` / `total_cost_usd` — from `metrics.token_usage`

Response shape: `{ data: { total_companies, total_agents, active_agents, total_tasks, total_tokens, total_cost_usd } }`.

---

### Wire-up: Agent engine dispatch TODOs
**File:** `app/api/agents.py`

The `start_agent` and `trigger_agent` handlers updated DB status but did not call the engine. Detailed TODO comments were added at both call sites explaining:
- The exact import path: `from app.engine.agent_manager import AgentManager`
- How to retrieve the manager from `request.app.state.agent_manager`
- Which `AgentManager` methods to call (`activate()` for start, `mark_running()` + event bus publish for trigger)
- Ticket reference: `AC-ENGINE-01`

---

## Files Changed

| File | Change |
|------|--------|
| `app/api/search.py` | C-2: filter injection fix |
| `app/api/webhooks.py` | C-3: required webhook secrets |
| `app/api/approvals.py` | M-2: new file |
| `app/models/approval.py` | M-2: new file |
| `app/schemas/approval.py` | M-2: new file |
| `app/api/router.py` | M-2: register approvals router |
| `app/models/task.py` | M-3: status default |
| `app/schemas/task.py` | M-3: status Literal |
| `app/api/tasks.py` | M-3: status default in create |
| `app/schemas/common.py` | M-4: ListResponse shape, make_list_response |
| `app/api/metrics.py` | M-7: platform endpoint |
| `app/api/agents.py` | Engine dispatch TODOs |

---

## Outstanding Work

1. **Database migration** — create `approvals` table (M-2) and migrate task `status` values `open -> backlog`, `blocked -> in_progress` (M-3).
2. **AC-ENGINE-01** — replace the TODO comments in `agents.py` with real `AgentManager` calls once the engine is wired into `app.state` during lifespan startup.
3. **M-5 confirmation** — verify the frontend `api.ts` search client sends POST (not GET) before closing the issue.
4. **ListResponse consumers** — audit any code that directly constructs `ListResponse(data=..., meta=...)` rather than using `make_list_response()` and update the field names to `items=`.
