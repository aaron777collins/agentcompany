# AgentCompany Security Audit — Phase 3

**Date:** 2026-04-18
**Scope:** Full codebase review — 40+ files across backend, frontend, infrastructure, and configuration
**Auditor:** Automated security review agent
**Files reviewed:** `app/core/security.py`, `app/api/search.py`, `app/api/metrics.py`, `app/api/agents.py`, `app/api/tasks.py`, `app/api/approvals.py`, `app/api/events.py`, `app/api/webhooks.py`, `app/dependencies.py`, `app/main.py`, `app/config.py`, `app/engine/agent_loop.py`, `app/engine/engine_service.py`, `app/engine/cost_tracker.py`, `app/engine/memory.py`, `app/engine/tool_registry.py`, `app/engine/llm/anthropic.py`, `app/adapters/meilisearch_adapter.py`, `app/adapters/base.py`, `app/adapters/registry.py`, `app/models/agent.py`, `app/models/base.py`, `alembic/versions/001_initial.py`, `services/web-ui/src/lib/auth.ts`, `services/web-ui/src/lib/api.ts`, `services/web-ui/src/middleware.ts`, `services/web-ui/src/components/layout/AuthGuard.tsx`, `services/web-ui/src/app/search/page.tsx`, `services/web-ui/src/components/agents/AgentLogs.tsx`, `services/web-ui/src/components/layout/CommandPalette.tsx`, `services/web-ui/next.config.js`, `docker-compose.yml`, `docker/traefik/traefik.yml`, `docker/traefik/dynamic.yml`, `configs/keycloak/realm-export.json`, `configs/mattermost/config.json`, `configs/outline/outline.env`, `.env.example`, `.gitignore`, `services/agent-runtime/Dockerfile`, `services/web-ui/Dockerfile`, `services/agent-runtime/requirements.txt`, `services/web-ui/package.json`

---

## Executive Summary

AgentCompany has a well-structured security foundation for an early-stage multi-tenant agent platform. The JWT validation pipeline is sound (RS256, issuer + audience verification, JWKS caching), database RLS policies are in place, the Meilisearch filter injection fix is properly implemented, and secrets are consistently sourced from environment variables rather than hardcoded. PKCE is correctly implemented for the browser OIDC flow, and all SQL is parameterized throughout.

However, several high-severity gaps remain before public exposure: three services (Ollama, Traefik dashboard, Meilisearch) are exposed on host ports with no authentication; the Keycloak realm export ships committed placeholder client secrets; the search API does not validate that the caller-supplied `company_id` in the request body matches the JWT's org identity (enabling cross-tenant reads); `org_id` is written as `NULL` to the metrics table; and the agent-runtime container runs as root. These issues must be resolved before this service handles real customer data.

---

## Findings

### Critical (Must Fix Before Deploy)

---

**C-1: Ollama exposed on host network with no authentication**

- **File/Line:** `docker-compose.yml:384` — `ports: - "${OLLAMA_PORT:-11434}:11434"`
- **Risk:** Ollama has no built-in authentication. Any process on the host (or any peer on the same network segment in cloud deployments) can send arbitrary inference requests, extract loaded model weights, or consume GPU resources. An attacker can also use Ollama as an oracle to reconstruct confidential system prompts and agent memories.
- **Remediation:** Remove the `ports` mapping from the `ollama` service — it only needs to be on the `internal` network, reachable by `agent-runtime`. Access from outside Docker should be blocked at the network layer. If external access is truly needed, add an authenticating reverse-proxy in front.

---

**C-2: Search endpoint accepts caller-supplied `company_id` without validating it against JWT claims**

- **File/Line:** `services/agent-runtime/app/api/search.py:62,80-99`
- **Risk:** The `SearchRequest` body contains a `company_id` field that is taken directly from the caller and used to build the Meilisearch filter. An authenticated user belonging to org `A` can set `company_id` to a company in org `B` and receive that company's search results. The anti-injection measures on the filter value are correct, but the *semantic* validation (does this company_id belong to the caller's org?) is entirely absent. This is a multi-tenant data isolation failure.
- **Remediation:** After extracting `claims`, verify that `body.company_id` belongs to `claims.org_id` — either by querying the DB or by embedding the allowed company IDs in the JWT. At minimum, the `/search` handler must reject any request where the caller cannot prove membership in the target company.

---

**C-3: Keycloak realm export commits real-looking client secrets**

- **File/Line:** `configs/keycloak/realm-export.json:113,144,228` — values `CHANGE_ME_AGENT_API_SECRET`, `CHANGE_ME_AGENT_SERVICE_SECRET`, `CHANGE_ME_OUTLINE_SECRET`
- **Risk:** This file is in version control. Even though the values are placeholder strings, any automated import of `realm-export.json` (e.g., in a CI Keycloak provisioning step) will create Keycloak clients with these predictable secrets. If an operator imports the file without replacing the values, all OIDC clients are compromised. Additionally the file demonstrates the import path works, making it easier for a future accidental commit of real secrets to go unnoticed.
- **Remediation:** Replace placeholder literal strings with environment variable references or use a Keycloak provisioning script that injects secrets from a secrets manager at import time. Add a pre-commit hook that rejects commits matching `CHANGE_ME` in JSON config files.

---

**C-4: Agent-runtime container runs as root**

- **File/Line:** `services/agent-runtime/Dockerfile` — no `USER` instruction after the `runtime` stage
- **Risk:** If any vulnerability in FastAPI, uvicorn, a dependency, or agent-generated code leads to a container escape, the attacker lands as root. This also violates least-privilege in shared container environments. The web-ui Dockerfile correctly creates and uses a non-root `nextjs` user (uid 1001); the agent-runtime must follow the same pattern.
- **Remediation:** Add to the `runtime` stage:
  ```dockerfile
  RUN addgroup --system --gid 1001 appgroup && \
      adduser --system --uid 1001 --ingroup appgroup appuser
  USER appuser
  ```

---

### High (Fix Before Public Beta)

---

**H-1: Traefik dashboard is unauthenticated and exposed on a host port**

- **File/Line:** `docker/traefik/traefik.yml:22-23` — `api: { dashboard: true, insecure: true }`, `docker-compose.yml:54` — `"${TRAEFIK_DASHBOARD_PORT:-8080}:8080"`
- **Risk:** The Traefik dashboard reveals the full routing table, middleware configuration, backend service addresses, and certificate status. An attacker with access to port 8080 can enumerate every internal service URL. `insecure: true` explicitly disables authentication. In a cloud deployment, port 8080 may be reachable from the public internet.
- **Remediation:** Set `insecure: false`, attach BasicAuth or forward-auth middleware to the dashboard router, and remove the host-port mapping. Restrict dashboard access to `127.0.0.1` if it must be kept for operator use.

---

**H-2: Meilisearch is accessible via Traefik without authentication**

- **File/Line:** `docker-compose.yml:369-373` — Meilisearch is routed at `/search` with no authentication middleware; `MEILI_ENV=development` default
- **Risk:** The `/search` path is exposed through Traefik without any auth middleware in the label chain. An external user can directly POST to `/search/indexes/*/search` with arbitrary filters, bypassing the `company_id` injection in the FastAPI layer entirely. In development mode (`MEILI_ENV=development`), the Meilisearch web UI is also exposed at that path.
- **Remediation:** Add a `traefik.http.routers.meilisearch.middlewares` label that applies at minimum an IP allowlist restricting Meilisearch to internal traffic. Alternatively move Meilisearch off the `external` network entirely — only `agent-runtime` needs to reach it directly. Set `MEILISEARCH_ENV=production` in `.env.example` defaults.

---

**H-3: Tokens stored in localStorage — XSS risk**

- **File/Line:** `services/web-ui/src/lib/auth.ts:88-93` — `saveTokens()` writes access_token, refresh_token, and id_token to `localStorage`
- **Risk:** Any XSS vulnerability in the Next.js app, a third-party dependency, or a Mattermost/Outline iframe would expose all three tokens to exfiltration. A stolen refresh token grants long-lived access (up to 30 days per `offlineSessionIdleTimeout` in Keycloak). The code itself acknowledges this: *"Production deployments should consider httpOnly cookies via a BFF instead"*.
- **Remediation:** Implement a Backend-for-Frontend (BFF) pattern where the Next.js server-side route handles the token exchange and stores tokens in `HttpOnly; Secure; SameSite=Strict` cookies. The browser never sees the raw token values.

---

**H-4: No Content Security Policy header**

- **File/Line:** `services/web-ui/src/middleware.ts` and `services/web-ui/next.config.js` — neither sets a `Content-Security-Policy` header
- **Risk:** The absence of CSP removes the browser's last line of defense against XSS. Given that tokens are in localStorage (H-3) and the app renders agent-generated content (log messages, task descriptions), CSP is essential to limit exfiltration to attacker-controlled origins.
- **Remediation:** Add a `Content-Security-Policy` header in `next.config.js`. At minimum: `default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'`. Avoid `'unsafe-inline'` and `'unsafe-eval'`.

---

**H-5: `org_id` is persisted as NULL in metrics.token_usage**

- **File/Line:** `services/agent-runtime/app/engine/cost_tracker.py:263` — `None,  # org_id — filled in by caller if available`
- **Risk:** Every row in `metrics.token_usage` has `org_id = NULL`. The `platform_stats` endpoint in `metrics.py` filters on `org_id = :org_id`, so it will return zero results for all queries (all token usage data is invisible). More dangerously, if a policy relying on `org_id` is later added to the metrics schema, NULL rows will either bypass or break it. This is both a data integrity failure and a hidden business-logic bug.
- **Remediation:** `CostTracker.__init__` already receives `company_id`; add an `org_id` parameter and pass it through. The `AgentDecisionLoop` has access to the agent's org_id from the trigger context or the agent record.

---

**H-6: Keycloak runs in `start-dev` mode in docker-compose**

- **File/Line:** `docker-compose.yml:189` — `command: start-dev`
- **Risk:** `start-dev` disables TLS, uses an in-memory H2 database (though here it is overridden to Postgres), enables verbose error output, and enables the insecure admin REST API without mTLS. Running this in any environment accessible beyond localhost is insecure.
- **Remediation:** Switch to `start` with proper TLS certificates for production. For development environments where `start-dev` is acceptable, document this clearly and ensure the `APP_ENV=development` guard prevents accidental production use.

---

**H-7: Approvals accessible to any org member, not just admins**

- **File/Line:** `services/agent-runtime/app/api/approvals.py:70,105` — `approve` and `deny` handlers accept `OrgMember` not `OrgAdmin`
- **Risk:** Any authenticated user (including agents via their `agent` role which satisfies `OrgMember`) can approve their own pending actions. This undermines the human-in-the-loop control: an agent could theoretically approve its own sensitive action request.
- **Remediation:** Restrict `approve` and `deny` to `OrgAdmin`. Additionally, verify that the approving user (`claims.sub`) is not the same entity that requested the approval (`approval.agent_id`).

---

### Medium (Fix Before GA)

---

**M-1: API docs (`/docs`, `/redoc`, `/openapi.json`) exposed without authentication in production**

- **File/Line:** `services/agent-runtime/app/main.py:181-183`
- **Risk:** The Swagger UI and OpenAPI spec enumerate all endpoints, schemas, and example payloads. This aids attackers in crafting targeted requests and reveals internal data models. FastAPI exposes these unconditionally regardless of `APP_ENV`.
- **Remediation:** Conditionally disable docs in production:
  ```python
  docs_url="/docs" if settings.app_env == "development" else None,
  redoc_url="/redoc" if settings.app_env == "development" else None,
  openapi_url="/openapi.json" if settings.app_env == "development" else None,
  ```

---

**M-2: CORS allows all methods and headers from configured origins**

- **File/Line:** `services/agent-runtime/app/main.py:190-195` — `allow_methods=["*"]`, `allow_headers=["*"]`
- **Risk:** Allowing all HTTP methods and headers unnecessarily enlarges the CORS attack surface. If a future API endpoint accepts a dangerous method (DELETE, PATCH) that should be protected, the permissive CORS policy means browser-originated cross-origin requests can reach it.
- **Remediation:** Restrict to the methods and headers the API actually uses: `allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"]`, `allow_headers=["Authorization", "Content-Type", "Accept"]`.

---

**M-3: `period` parameter in `cost_breakdown` is not validated; uses only `_resolve_period` defaults**

- **File/Line:** `services/agent-runtime/app/api/metrics.py:183-188` — `cost_breakdown` passes `period` to `_resolve_period` with `start_at=None, end_at=None`, but the valid periods list is `{1h, 24h, 7d, 30d, custom}`. The comment says `default="30d"` but a caller passing `period=custom` with no dates will get an HTTP 400; a caller passing `period=1000d` would also get a 400. Low impact but worth fixing.
- **Risk:** No functional security issue, but inconsistent validation creates an uneven API surface.
- **Remediation:** Add a `period: Literal["7d","30d","90d"]` type annotation to `cost_breakdown`, matching the frontend's type in `api.ts` line 302.

---

**M-4: Agent trigger cross-company check missing**

- **File/Line:** `services/agent-runtime/app/api/agents.py:291-342` — `trigger_agent` endpoint; `_get_or_404` only checks `org_id`, not `company_id`
- **Risk:** A user who is an `OrgMember` can trigger any agent in their org, even agents belonging to a different company within that org. While the `org_id` check prevents cross-org access, the company-level isolation is enforced only by RLS (which only applies once the company_id GUC is set), not by an explicit check in the endpoint logic. The concern is ordering: RLS is set from `claims.company_id` but the agent may belong to a different company than the caller.
- **Remediation:** In `_get_or_404`, also filter by `Agent.company_id == claims.company_id` (if the JWT carries one) or add explicit company membership validation before allowing trigger.

---

**M-5: JWKS stale-cache fallback allows use of revoked signing keys indefinitely**

- **File/Line:** `services/agent-runtime/app/core/security.py:62-67` — stale JWKS cache used when Keycloak is unreachable
- **Risk:** If Keycloak rotates its signing key (e.g., after a key compromise), the agent-runtime will continue accepting tokens signed with the old key for up to one hour (TTL) even if Keycloak is reachable, and indefinitely if Keycloak remains down. While this is an intentional availability trade-off, it should be bounded.
- **Remediation:** Add a maximum stale-cache lifetime (e.g., 4 hours). After that, fail closed rather than accepting potentially revoked signing keys. Log a `CRITICAL` alert when the stale cache age exceeds 1 hour.

---

**M-6: Mattermost config: MFA disabled, email verification not required, open signup**

- **File/Line:** `configs/mattermost/config.json:16-18,47` — `EnableMultifactorAuthentication: false`, `EnforceMultifactorAuthentication: false`, `RequireEmailVerification: false`, `EnableUserCreation: true`
- **Risk:** Any user can self-register a Mattermost account without email verification. Agents with access to the chat adapter can post as any channel member. Without MFA enforcement, credential-stuffing attacks are easier.
- **Remediation:** Set `RequireEmailVerification: true`. Evaluate enabling MFA at minimum for admin accounts. Consider setting `EnableUserCreation: false` and provisioning users via Keycloak SSO only.

---

**M-7: Mattermost `AtRestEncryptKey` is empty — database at rest is unencrypted**

- **File/Line:** `configs/mattermost/config.json:85` — `"AtRestEncryptKey": ""`
- **Risk:** Mattermost encrypts certain sensitive fields (OAuth tokens, incoming webhook data) using this key. With an empty key, those fields are stored in plaintext in the database.
- **Remediation:** Generate a 32-character random string and set it before first boot. This key cannot be changed after data is written without re-encrypting stored values.

---

**M-8: Docker `minio-init` uses root MinIO credentials for bucket creation**

- **File/Line:** `docker-compose.yml:172-176` — `minio-init` uses `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` directly
- **Risk:** Running bucket initialization with root credentials means the initialization script has superuser access to MinIO. If the script is compromised or the environment variables are logged, all MinIO data is at risk.
- **Remediation:** Create a dedicated MinIO service account with only `s3:CreateBucket` and `s3:PutObject` permissions scoped to the `outline` bucket. Use those credentials for `minio-init`.

---

### Low / Informational

---

**L-1: `isAuthenticated()` returns `true` when `AUTH_ENABLED=false`**

- **File/Line:** `services/web-ui/src/lib/auth.ts:192`
- **Risk:** When `NEXT_PUBLIC_KEYCLOAK_URL` is not set, the client-side auth guard treats all sessions as authenticated. This is the documented development mode behavior but could allow accidental deployment without auth configured. The backend correctly requires a JWT on every request regardless, so the practical impact is limited to the frontend UI appearing functional without a session.
- **Note:** Document clearly that `AUTH_ENABLED=false` is development-only and add a runtime check that warns if `APP_ENV=production` but `AUTH_ENABLED=false`.

---

**L-2: Agent-performance metrics endpoint leaks cross-company agent IDs**

- **File/Line:** `services/agent-runtime/app/api/metrics.py:236-286` — `GET /metrics/agents/{agent_id}/performance` filters only on `org_id`, not `company_id`
- **Risk:** A caller can supply any `agent_id` from their org (even from a different company) and retrieve its token usage profile. This leaks which agents exist in sibling companies and their activity patterns, though not their content.
- **Remediation:** Add `company_id = :company_id` to the WHERE clause and require the caller to supply their company_id (consistent with the `/metrics/tokens` endpoint).

---

**L-3: `docker-compose.override.yml` is in `.gitignore`**

- **File/Line:** `.gitignore:66`
- **Risk:** The override file exists at the project root but is excluded from version control. If it contains security-relevant customizations (port removals, CPU-only Ollama config), those changes are invisible to reviewers and will not be applied in clean deployments.
- **Note:** Document that the override file must be generated by `scripts/setup.sh` and describe its expected security-relevant contents.

---

**L-4: Token budget check uses estimated 500 tokens, not actual**

- **File/Line:** `services/agent-runtime/app/engine/agent_loop.py:218` — `await self._cost_tracker.check(estimated_tokens=500)`
- **Risk:** A single LLM call may use significantly more than 500 tokens (e.g., large context windows with tool results). An agent approaching its budget ceiling can overshoot it by a full call's worth of tokens before the budget is enforced.
- **Note:** Consider passing the estimated context size from `ContextWindowManager` to the budget check, or capping the maximum overshoot by recording usage before allowing the next step.

---

**L-5: Outline `FORCE_HTTPS=false` and Mattermost `ConnectionSecurity=""` in committed configs**

- **File/Line:** `configs/outline/outline.env:128`, `configs/mattermost/config.json:5`
- **Risk:** Both services default to plain HTTP. If these config files are imported as-is into a production deployment, traffic to Outline and Mattermost is unencrypted between the browser and Traefik, and between Traefik and the backend container.
- **Note:** These are intentional for local development but must be flagged for the operations checklist. Add comments and a setup script check.

---

**L-6: `python-jose` is used for JWT validation rather than `PyJWT` or `authlib`**

- **File/Line:** `services/agent-runtime/requirements.txt:8` — `python-jose[cryptography]>=3.3`
- **Risk:** `python-jose` has had CVEs in the past (e.g., CVE-2024-33664 — algorithm confusion in RS256 validation in some versions). The `[cryptography]` extra mitigates the most critical issues, but the library is less actively maintained than alternatives.
- **Note:** Consider migrating to `PyJWT>=2.8` with `cryptography` or `authlib`, both of which have better CVE response histories. Validate that the installed version is not in the affected range.

---

**L-7: `MEILI_HTTP_ADDR=0.0.0.0:7700` — Meilisearch listens on all interfaces inside container**

- **File/Line:** `docker-compose.yml:353`
- **Risk:** This is Docker-standard but means if any other container on the `internal` network is compromised, it can reach Meilisearch directly without going through the `agent-runtime` proxy layer. The `company_id` filter in the search proxy would be bypassed.
- **Note:** Acceptable for the current architecture. Mitigated if Meilisearch is moved off the `external` network (see H-2).

---

**L-8: `next.config.js` image remote pattern allows all paths from localhost:8000**

- **File/Line:** `services/web-ui/next.config.js:8-14` — `pathname: '/**'`
- **Risk:** Next.js Image Optimization will proxy and cache any URL on localhost:8000. If the agent-runtime ever serves user-controlled content at arbitrary paths, this could be abused.
- **Note:** Restrict `pathname` to the specific agent avatar/logo paths when those are defined.

---

## Positive Security Practices

1. **RS256 JWT validation is correctly implemented.** `security.py` verifies signature, expiry, issuer, audience, and required claims. Algorithms are explicitly constrained to `["RS256"]`. No `algorithms=None` footguns.

2. **All SQL is parameterized.** Every raw `text()` query in `metrics.py`, `engine_service.py`, `memory.py`, and `cost_tracker.py` uses bind variables. The comment in `dependencies.py` ("Parameterized to prevent injection — never use an f-string here") shows the team is aware of the risk.

3. **RLS is implemented at the database layer.** `001_initial.py` enables RLS on all tenant-facing tables and creates `company_isolation` policies. The `get_db` dependency sets the GUC via `SET LOCAL` (transaction-scoped, preventing bleed between concurrent requests).

4. **Meilisearch filter injection (C-2 from previous audit) is properly fixed.** `search.py` has a key whitelist (`_ALLOWED_FILTER_KEYS`), a forbidden-pattern regex (`_FORBIDDEN_VALUE_PATTERN`), and always injects `company_id` from the server-side validated body, not from user-supplied filter dicts.

5. **Webhook HMAC verification is correct.** All webhook handlers use `hmac.compare_digest` (constant-time), refuse requests when the secret is unconfigured, and verify before parsing the JSON body. This prevents timing attacks and SSRF via forged webhooks.

6. **PKCE is correctly implemented for the OIDC flow.** `auth.ts` uses S256 code challenge, stores the verifier in localStorage, validates state on callback (CSRF protection), and cleans up PKCE material after use.

7. **Secrets are consistently sourced from environment variables.** No hardcoded API keys, passwords, or tokens were found in Python or TypeScript source files. The adapter `BaseAdapter._secret()` pattern keeps secrets off instance attributes.

8. **Docker network topology is well designed.** Services that should not be internet-accessible (`postgres`, `redis`, `keycloak`, `mattermost` backend) are on the `internal` network. The `internal: true` flag prevents outbound internet traffic from those services.

9. **Soft delete is implemented uniformly.** All entities use `deleted_at` with `deleted_at IS NULL` guards in every query. The RLS policies operate on live rows; there is no visible shortcut around the soft-delete filter in any reviewed endpoint.

10. **Web-UI Dockerfile runs as a non-root user.** The `runner` stage creates uid 1001 `nextjs` and drops to it before starting the server.

11. **Token budget enforcement happens pre-LLM-call.** `CostTracker.check()` is called before every LLM call in the decision loop, not just at run start. This is the correct pattern for preventing budget overshoot.

---

## Recommendations (Prioritized)

1. **[Immediate]** Remove Ollama host port mapping (C-1). This is a one-line change with zero downside.

2. **[Immediate]** Validate `company_id` in the search request against the caller's JWT claims (C-2). Add a DB lookup or JWT claim check before constructing the Meilisearch filter.

3. **[Before any external access]** Replace Keycloak `CHANGE_ME` placeholder secrets with environment variable injection and add a CI check (C-3).

4. **[Before production]** Add `USER` instruction to agent-runtime Dockerfile to run as non-root (C-4).

5. **[Before production]** Restrict Meilisearch to the `internal` network only, removing its Traefik exposure (H-2).

6. **[Before public beta]** Implement a BFF layer to hold OIDC tokens in `HttpOnly` cookies, removing them from localStorage (H-3).

7. **[Before public beta]** Add a `Content-Security-Policy` header to the Next.js application (H-4).

8. **[Before public beta]** Pass `org_id` correctly to `CostTracker.record_usage` — it is currently always NULL in the database (H-5).

9. **[Before public beta]** Switch Keycloak to `start` mode with TLS (H-6).

10. **[Before public beta]** Restrict the `approve`/`deny` endpoints to `OrgAdmin` and prevent self-approval (H-7).

11. **[Before GA]** Disable FastAPI's `/docs`, `/redoc`, and `/openapi.json` in production environments (M-1).

12. **[Before GA]** Generate and configure Mattermost `AtRestEncryptKey` before first user data is written (M-7).

13. **[Ongoing]** Monitor `python-jose` for CVEs and evaluate migrating to `PyJWT` or `authlib` (L-6).
