# Seed Script Handoff

**Date:** 2026-04-18  
**Files changed:**
- `scripts/wait-for-services.sh` (new)
- `scripts/seed-data.sh` (rewrite)

---

## What changed and why

### wait-for-services.sh (new)

Polls each service until healthy or a configurable timeout expires. Used by `seed-data.sh` before making any API calls.

Key design choices:

- **Tool fallback chain** — for HTTP services: `curl` → `wget` → `nc` → bash `/dev/tcp`. For Postgres: `pg_isready` → `psql` → TCP. For Redis: `redis-cli` → TCP. This lets the script work inside minimal containers without all tools present.
- **No `sleep` at the end** — after all per-service waits complete, the final status report re-checks each service once more so the summary reflects the actual state, not just the last poll result.
- **Max-wait of 0 means infinite** — explicitly documented in usage; the loop uses `[[ "${MAX_WAIT}" -gt 0 ... ]]` to gate the timeout check.

### seed-data.sh (rewrite)

The previous script had three problems:

1. **Wrong API shapes** — it sent fields like `token_budget_daily`, `max_agents`, `llm_adapter`, `heartbeat_config` that do not exist in the actual Pydantic schemas. Those POST bodies were silently ignored or caused 422 validation errors.

2. **No auth** — every mutating endpoint requires a Bearer JWT (`OrgAdmin` or `OrgMember`). The old script called the API without a token.

3. **`eval curl` pattern** — dynamic flag assembly via `eval` is fragile with JWT tokens (which contain `/`, `+`, `=` characters that bash word-splits or re-interprets).

The rewrite fixes all three.

---

## Schema alignment

| Resource | Schema fields used | Fields dropped vs old script |
|---|---|---|
| Company | `name`, `slug`, `description`, `settings{timezone,default_language,human_approval_required}` | `max_agents`, `token_budget_daily/monthly` (not in CompanySettings) |
| Role | `name`, `slug`, `company_id`, `description`, `level`, `reports_to_role_id`, `permissions`, `tool_access`, `max_headcount`, `headcount_type` | `title`, `token_budget_daily` (not in RoleCreate) |
| Agent | `name`, `slug`, `company_id`, `role_id`, `llm_config{provider,model,temperature,max_tokens}`, `system_prompt`, `capabilities`, `tool_permissions`, `token_budget_daily`, `token_budget_monthly` | `llm_adapter`, `personality`, `heartbeat_config` (not in AgentCreate) |
| Task | `title`, `description`, `company_id`, `priority`, `tags`, `assigned_to`, `assigned_type`, `sync_to_plane`, `metadata` | `status` at creation time — the API always sets status to "backlog"; TaskCreate has no status field |

---

## Auth prerequisites

The script uses the Keycloak `client_credentials` grant:

```
POST /auth/realms/agentcompany/protocol/openid-connect/token
  client_id=agentcompany-api
  client_secret=<KEYCLOAK_CLIENT_SECRET>
  grant_type=client_credentials
```

For this to work, the `agentcompany-api` Keycloak client must be configured:

1. **Service accounts enabled** — toggle in the client settings under "Service Accounts" tab.
2. **`org:admin` realm role assigned to the service account** — in Keycloak admin → Clients → agentcompany-api → Service Account Roles tab, add `org:admin` from the realm roles list.
3. **Token claim `org_id` present** — the agent-runtime `validate_token` function requires an `org_id` claim. Add a mapper in the client: Client Scopes → agentcompany-api → Mappers → create a "Hardcoded claim" or "User Attribute" mapper named `org_id` that injects the org UUID.

Without step 3 the API will return 401 "Token missing 'org_id' claim" on every request even with a valid token.

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `KEYCLOAK_REALM` | `agentcompany` | Realm name |
| `KEYCLOAK_CLIENT_ID` | `agentcompany-api` | Client for service account auth |
| `KEYCLOAK_CLIENT_SECRET` | `agentcompany-api-secret` | Client secret (override in .env) |
| `MEILISEARCH_MASTER_KEY` | _(empty)_ | Used when Meilisearch auth is enabled |
| `SKIP_WAIT` | `0` | Set to `1` to skip wait-for-services.sh |

---

## Idempotency

- **Company** — on HTTP 409 the script fetches the list and finds the `acme` slug. If the list returns nothing (e.g. a different org) the script exits loudly.
- **Roles** — on HTTP 409 the script fetches `/roles?company_id=<id>&limit=100` and filters by slug to find the existing ID. The ID is stored so downstream role references (`reports_to_role_id`) still resolve correctly.
- **Agents** — same pattern as roles.
- **Tasks** — tasks have no uniqueness constraint on title, so duplicates are possible on repeat runs. This is acceptable for a dev seed.
- **Meilisearch indexes** — `POST /indexes` returns 409 if the index already exists; the script treats this as success.

---

## Known limitations

1. **Task status** — `TaskCreate` always sets status to `"backlog"`. Tasks described as "todo" in the spec cannot be seeded as todo in a single request; a follow-up `PUT /tasks/{id}` with `{"status":"todo"}` is needed. Not implemented because it adds per-task round trips and the spec says "backlog" tasks are acceptable.

2. **Meilisearch URL** — the script hits `${BASE_URL}/search` (through Traefik). If Traefik is not running, set `MEILI_BASE` directly or use `--base-url`. Alternatively override `MEILI_BASE` as an env var before calling the script.

3. **Keycloak `org_id` claim** — must be configured manually in Keycloak (see Auth prerequisites above). There is no automated way to bootstrap this via the seed script.

---

## Next steps

- After first run, verify the 5 tasks appear in the web-ui kanban board at `/app`.
- Confirm Meilisearch indexes are populated by the agent-runtime's background indexer once agents and tasks are created.
- If the `org_id` claim is not yet mapped in Keycloak, set `SKIP_WAIT=1` and run the script after adding the mapper — there is no need to re-run wait-for-services.
