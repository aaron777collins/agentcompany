# Frontend Bug-Fix Handoff — Web UI

**Date:** 2026-04-18
**Engineer:** Staff Software Engineer (Claude)
**Branch context:** Applied directly to working tree at `/home/ubuntu/topics/agentcompany/services/web-ui/`

---

## Summary of changes

Four issues resolved across three fix tickets. All changes are surgical — no new runtime dependencies were added.

---

## C-1: Keycloak OIDC auth wiring

### New file: `src/lib/auth.ts`

Implements a lightweight PKCE (S256) authorization code flow against Keycloak using native `fetch` and `crypto.subtle`. No third-party auth library was introduced; `keycloak-js` adds ~50 KB of implicit-flow code we don't need.

Key design decisions:
- `AUTH_ENABLED` is derived at module load time from the three `NEXT_PUBLIC_KEYCLOAK_*` env vars. When all three are absent the module is a no-op, so the app runs unauthenticated in bare dev.
- Tokens are stored in `localStorage` under `ac_*` keys. A production deployment with stricter XSS posture should route tokens through a BFF with httpOnly cookies instead.
- `getToken()` is async and handles token refresh automatically. A module-level `refreshPromise` guard prevents parallel refresh races (two concurrent API calls expiring at the same time will share one refresh request).
- `login()` stores the PKCE verifier and a random state nonce in localStorage before redirecting so `handleCallback()` can verify both on return. The state check guards against CSRF.
- `logout()` calls the Keycloak end-session endpoint with `id_token_hint` so Keycloak invalidates the server-side session, not just the local tokens.

Public API exported:
```
getToken(): Promise<string | null>
isAuthenticated(): boolean
login(): Promise<void>
logout(): void
handleCallback(searchParams: URLSearchParams): Promise<void>
AUTH_ENABLED: boolean
```

**Still needed by another engineer:**
The `/auth/callback` route does not exist yet. A new file `src/app/auth/callback/page.tsx` must call `handleCallback(new URLSearchParams(window.location.search))` and redirect to `/` on success. The callback redirect URI registered in Keycloak must be `<origin>/auth/callback`.

### Updated file: `src/lib/api.ts`

- Imports `getToken`, `login`, `AUTH_ENABLED` from `./auth`.
- `request()` now awaits `getToken()` before each fetch and injects `Authorization: Bearer <token>` when a token is available.
- HTTP 401 responses (when `AUTH_ENABLED`) trigger `login()` which redirects the browser to Keycloak. The unreachable throw after it satisfies TypeScript's control-flow analysis.
- When `AUTH_ENABLED` is false (dev mode) the auth header is skipped entirely — no Keycloak required locally.
- `credentials: 'include'` is retained for any cookie-based dev proxy fallback.

### Updated file: `.env.example`

Keycloak vars were already present but labelled "future use". Comments updated to reflect they are now active and explain the dev-mode behaviour. `NEXT_PUBLIC_KEYCLOAK_CLIENT_ID` value corrected from `agentcompany-web` to `web-ui` to match the Keycloak realm config documented in the architecture spec.

---

## M-3: `cancelled` task status

### Updated file: `src/lib/types.ts`

```typescript
// Before
export type TaskStatus = 'backlog' | 'todo' | 'in_progress' | 'review' | 'done';

// After
export type TaskStatus = 'backlog' | 'todo' | 'in_progress' | 'review' | 'done' | 'cancelled';
```

### Updated file: `src/lib/utils.ts`

Added `cancelled: 'Cancelled'` to `taskStatusLabels`.

### Updated file: `src/components/tasks/KanbanBoard.tsx`

`cancelled` tasks are **hidden from the board** rather than shown in a new column. Rationale: cancelled tasks are a terminal state; surfacing them alongside active work columns adds noise without workflow value. They remain queryable via the API with `?status=cancelled`.

Implementation: `initialTasks` are filtered through `BOARD_STATUSES` (a Set of the five active statuses) on `useState` initialization. Tasks that arrive as `cancelled` from the API are silently excluded.

### Updated file: `src/components/tasks/KanbanColumn.tsx`

Added `cancelled` entry to `columnColors` to satisfy the exhaustive `Record<TaskStatus, ...>` type. It will never render but TypeScript requires all union members to be present.

---

## M-4: Pagination response type

**No code change required.** The `PaginatedResponse<T>` interface in `src/lib/types.ts` already matches the spec exactly:

```typescript
interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}
```

The `request()` wrapper returns `res.json()` directly without transformation, so the parsed JSON shape flows through unchanged to callers. Verified that all paginated endpoints (`companies.list`, `agents.list`, `roles.list`, `tasks.list`) type their return as `Promise<PaginatedResponse<T>>` and access `.items` correctly.

---

## M-7: Metrics endpoint path and response type

### Updated file: `src/lib/types.ts`

The old `PlatformMetrics` shape did not match the backend contract. Updated to:

```typescript
interface PlatformMetrics {
  total_companies: number;
  total_agents: number;
  active_agents: number;
  total_tasks: number;
  total_token_usage: number;
  total_cost_usd: number;
}
```

Removed fields: `tasks_completed_today`, `total_tasks_in_progress`, `token_usage_today`, `monthly_cost_usd`, `monthly_budget_usd`.

The API path `GET /api/v1/metrics/platform` is already correct in `api.ts` (`/metrics/platform` appended to `API_BASE` which includes `/api/v1`).

### Updated file: `src/components/dashboard/StatsCards.tsx`

Cards updated to use the new field names:
- "Active Agents" — `active_agents` / `total_agents` (unchanged semantics)
- "Total Tasks" — `total_tasks` with `total_companies` as subtext (replaced "Tasks Completed Today")
- "Token Usage" — `total_token_usage` (replaced `token_usage_today`)
- "Total Cost" — `total_cost_usd` with static subtext (replaced budget-percentage calculation)

The budget percentage display (`monthly_cost_usd / monthly_budget_usd`) was removed because those fields no longer exist in the backend response. If per-company budget tracking is re-added later it should come from a separate `/metrics/budget` endpoint rather than embedding it in the platform aggregate.

Unused `formatPercent` import removed.

---

## Files changed

| File | Type | Ticket |
|------|------|--------|
| `src/lib/auth.ts` | Created | C-1 |
| `src/lib/api.ts` | Modified | C-1 |
| `.env.example` | Modified | C-1 |
| `src/lib/types.ts` | Modified | M-3, M-7 |
| `src/lib/utils.ts` | Modified | M-3 |
| `src/components/tasks/KanbanBoard.tsx` | Modified | M-3 |
| `src/components/tasks/KanbanColumn.tsx` | Modified | M-3 |
| `src/components/dashboard/StatsCards.tsx` | Modified | M-7 |

---

## Remaining work (not in scope of this fix)

1. **Auth callback route** — `src/app/auth/callback/page.tsx` must be created to handle the OIDC redirect. It calls `handleCallback()` from `auth.ts` and redirects to `/`.
2. **Route guard** — A layout-level or middleware check using `isAuthenticated()` that redirects unauthenticated users to `login()` before any protected page renders.
3. **SSE auth** — `events.streamUrl()` returns a URL string. `EventSource` does not support custom headers, so authenticated SSE requires either a short-lived token query parameter from Keycloak or routing the stream through the BFF. Tracked in architecture backlog.
4. **Budget metrics** — The monthly budget display was removed because the backend no longer returns those fields in `PlatformMetrics`. If needed, add a `/metrics/budget` endpoint and a separate card.
