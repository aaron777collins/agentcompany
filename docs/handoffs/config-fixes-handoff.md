# Config Fixes Handoff

Date: 2026-04-18
Engineer: Staff SWE (config-fixes pass)

---

## What was fixed

### M-1: Keycloak client ID alignment

**Problem:** The realm-export.json defined `agentcompany-web` and `agentcompany-api` as client IDs, but environment files and docker-compose used inconsistent values (`web-ui`, `agent-runtime`). The backend `security.py` was correct — it already validated the JWT audience as `agentcompany-api` — but the env defaults pointed to different client names, meaning the runtime's service account would request tokens from a non-existent Keycloak client.

**Canonical client IDs (now consistent everywhere):**
- Frontend: `agentcompany-web` (public PKCE client)
- Backend service account (M2M): `agentcompany-api` (confidential, `serviceAccountsEnabled: true`)

**Files changed:**

| File | Change |
|------|--------|
| `docker-compose.yml` | `WEB_UI_KEYCLOAK_CLIENT_ID` default: `web-ui` → `agentcompany-web` |
| `docker-compose.yml` | `AGENT_RUNTIME_KEYCLOAK_CLIENT_ID` default: `agent-runtime` → `agentcompany-api` |
| `.env.example` | `WEB_UI_KEYCLOAK_CLIENT_ID=web-ui` → `agentcompany-web` |
| `.env.example` | `AGENT_RUNTIME_KEYCLOAK_CLIENT_ID=agent-runtime` → `agentcompany-api` |
| `services/web-ui/.env.example` | `NEXT_PUBLIC_KEYCLOAK_CLIENT_ID=web-ui` → `agentcompany-web` |
| `services/agent-runtime/app/config.py` | `keycloak_client_id` default: `"agent-runtime"` → `"agentcompany-api"` |

**Files NOT changed:**
- `configs/keycloak/realm-export.json` — already correct; `agentcompany-web` and `agentcompany-api` were the right values. No rename needed.
- `services/agent-runtime/app/core/security.py` — already correct; `audience="agentcompany-api"` matches the realm-export client.

**Action required on existing deployments:** If you have an existing `.env` file derived from the old `.env.example`, update the two client ID values before restarting services. Any Keycloak realm imported before this fix will still work because the realm-export client IDs were already correct.

---

### M-6: RLS policies and `approvals` table in Alembic migration

**Problem:** The initial migration created tables but did not enable Row-Level Security, leaving tenant isolation to the application layer only. The `approvals` table (needed by the backend approval endpoints) was also missing.

**File changed:** `services/agent-runtime/alembic/versions/001_initial.py`

**What was added to `upgrade()`:**

1. **`approvals` table** — stores human-in-the-loop approval requests. Columns match the architecture spec:
   - `id`, `company_id` (FK → companies), `agent_id` (nullable FK → agents)
   - `action_type`, `action_description`, `status` (default `pending`)
   - `requested_at`, `resolved_at`, `resolved_by`, `metadata` (JSONB)
   - Indexes on `(company_id, status)` and `agent_id`

2. **RLS enabled** on: `companies`, `roles`, `agents`, `tasks`, `approvals`

3. **`company_isolation` policy** on each table. The predicate is:
   ```sql
   USING (company_id = current_setting('app.current_company_id', true)::text)
   ```
   (`companies` uses `id =` instead of `company_id =`.)

   The second argument `true` to `current_setting` means the function returns NULL rather than raising an error when the setting is not set. This prevents Alembic and superuser migrations from breaking, but note: **unset sessions will see zero rows**, which is the safe default.

**What was added to `downgrade()`:**
- `DROP POLICY IF EXISTS company_isolation ON <table>` for each RLS table (in reverse order)
- `DISABLE ROW LEVEL SECURITY` for each table
- `DROP TABLE approvals` (before the existing table drops)

**Application layer requirement:** Before executing any query, the connection must run:
```sql
SET LOCAL app.current_company_id = '<company_id>';
```
This is not yet implemented in the agent-runtime DB session middleware — a follow-up task must add it. Until then, RLS policies evaluate against a NULL setting and silently return empty result sets, which is safe but will break normal reads. Do not run this migration against a live production database until the session middleware is in place.

---

## Files changed (full list)

- `/home/ubuntu/topics/agentcompany/docker-compose.yml`
- `/home/ubuntu/topics/agentcompany/.env.example`
- `/home/ubuntu/topics/agentcompany/services/web-ui/.env.example`
- `/home/ubuntu/topics/agentcompany/services/agent-runtime/app/config.py`
- `/home/ubuntu/topics/agentcompany/services/agent-runtime/alembic/versions/001_initial.py`

## Follow-up required

1. **DB session middleware** (no ticket yet): The agent-runtime must call `SET LOCAL app.current_company_id = ...` at the start of every request context. Until this is done, RLS will block all reads in development. Recommend gating the migration behind a feature flag or deferring to a `002_enable_rls.py` migration that runs after the middleware ships.

2. **Application DB role**: The PostgreSQL role used by the application should NOT have `BYPASSRLS`. The Alembic/migration role (superuser or a role with `BYPASSRLS`) must remain separate so migrations can run without being blocked.

3. **`approvals` API endpoints**: The backend-fix agent is adding approval endpoints. Confirm they set `app.current_company_id` on the connection before querying the new table.
