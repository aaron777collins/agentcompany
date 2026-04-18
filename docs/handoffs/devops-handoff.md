# DevOps Handoff — AgentCompany

**Date:** 2026-04-18
**Author:** DevOps Engineer
**Recipient:** Next engineer (backend / platform / release management)

---

## What was built

This handoff covers all DevOps and CI/CD artefacts added to the AgentCompany
repository in this pass. Every file listed below was written from scratch unless
noted otherwise.

---

## Files delivered

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | CI pipeline: lint, test, and Docker build on push/PR |
| `.github/workflows/docker-publish.yml` | Release pipeline: multi-arch publish to ghcr.io on `v*` tag |
| `.github/ISSUE_TEMPLATE/bug_report.md` | Standard bug report template |
| `.github/ISSUE_TEMPLATE/feature_request.md` | Standard feature request template |
| `configs/keycloak/realm-export.json` | Keycloak realm with clients, roles, and a seed admin user |
| `configs/mattermost/config.json` | Mattermost dev baseline config with bots and webhooks enabled |
| `configs/outline/outline.env` | Documented Outline environment variable reference |
| `scripts/dev.sh` | Hot-reload dev mode (uvicorn + next dev + infra containers) |
| `scripts/seed-data.sh` | Sample company, roles, agents, project, wiki doc, chat channel |
| `LICENSE` | MIT license, copyright 2024-2026 Aaron Collins |
| `CONTRIBUTING.md` | Dev environment setup, project structure, adapter guide, PR process |
| `docs/handoffs/devops-handoff.md` | This file |

The following files were verified to already exist (DO NOT overwrite):

| File | Written by |
|------|-----------|
| `docker-compose.yml` | Infrastructure engineer |
| `.env.example` | Infrastructure engineer |
| `docker/traefik/traefik.yml` | Infrastructure engineer |
| `docker/traefik/dynamic.yml` | Infrastructure engineer |
| `docker/init-scripts/init-databases.sql` | Infrastructure engineer |
| `scripts/setup.sh` | Infrastructure engineer |
| `scripts/teardown.sh` | Infrastructure engineer |
| `services/agent-runtime/Dockerfile` | Backend engineer |
| `services/web-ui/Dockerfile` | Frontend engineer |

---

## CI pipeline (`.github/workflows/ci.yml`)

### Triggers

- Push to `main`
- Pull requests targeting `main`
- Concurrent runs for the same branch are cancelled; a force-push does not
  queue up N builds.

### Jobs (all parallel)

| Job | Runner | What it does |
|-----|--------|-------------|
| `lint-backend` | ubuntu-24.04 | `ruff check` + `ruff format --check` |
| `lint-frontend` | ubuntu-24.04 | `npm run lint` + `npm run type-check` |
| `test-backend` | ubuntu-24.04 | `pytest` with Postgres and Redis service containers |
| `test-frontend` | ubuntu-24.04 | `next build` (catches TypeScript and build errors) |
| `docker-build` | ubuntu-24.04 (x2) | Builds `agent-runtime` and `web-ui` images; does NOT push |

### Caching

- Python: `~/.cache/pip`, keyed on `requirements.txt` + `pyproject.toml`
- Node: `npm` cache via `setup-node` action, keyed on `package-lock.json`
- Docker layers: GitHub Actions cache backend (`type=gha`), scoped per service

### Test service containers

`test-backend` spins up real Postgres 16 and Redis 7 containers via the
`services:` block. Tests connect at `localhost:5432` and `localhost:6379`.
The test environment injects `DATABASE_URL`, `REDIS_URL`, `APP_ENV=test`,
and a placeholder `SECRET_KEY`.

When `app/tests/` is empty (service not yet scaffolded), pytest exits 0 with
no tests collected — CI still passes.

---

## Release pipeline (`.github/workflows/docker-publish.yml`)

### Trigger

Tag push matching `v*` (e.g. `v1.0.0`, `v2.3.1-rc.1`).

### What it does

1. Sets up QEMU for cross-compilation (needed for arm64 on an amd64 runner)
2. Logs in to `ghcr.io` using `GITHUB_TOKEN` (no additional secrets required)
3. Derives tags from the semver: `1.2.3`, `1.2`, `1`, `latest`
4. Builds and pushes both images as multi-arch manifests (`linux/amd64,linux/arm64`)
5. After both matrix jobs complete, creates a GitHub Release with generated
   release notes and the published image pull commands

### Publishing a release

```bash
git tag v1.0.0
git push origin v1.0.0
```

The pipeline fires automatically. Images will be available at:

```
ghcr.io/<owner>/agentcompany-agent-runtime:1.0.0
ghcr.io/<owner>/agentcompany-web-ui:1.0.0
```

### Required permissions

The workflow uses `GITHUB_TOKEN` with:
- `contents: write` (create GitHub Release)
- `packages: write` (push to ghcr.io)

No additional repository secrets are needed.

---

## Keycloak realm (`configs/keycloak/realm-export.json`)

### How to import

After Keycloak boots for the first time:

```bash
# Copy the realm export into the running container
docker compose cp configs/keycloak/realm-export.json \
    agentcompany-keycloak:/tmp/realm-export.json

# Import via Keycloak CLI
docker compose exec agentcompany-keycloak \
    /opt/keycloak/bin/kc.sh import \
    --file /tmp/realm-export.json \
    --override true
```

Alternatively, log in to the Keycloak Admin Console (`/auth/admin`) and use
Realm Settings > Import to upload the file via the UI.

### Clients registered

| Client ID | Type | Purpose |
|-----------|------|---------|
| `agentcompany-web` | Public, PKCE | Next.js frontend (browser PKCE flow) |
| `agentcompany-api` | Confidential, service account | agent-runtime machine-to-machine auth |
| `agent-service` | Confidential, UMA authz | Agent-to-tool fine-grained authorization |
| `outline` | Confidential, standard flow | Outline wiki OIDC login |

### Client secrets

The realm export ships placeholder secrets (`CHANGE_ME_*`). After importing:

1. Open each confidential client in the Keycloak Admin Console
2. Regenerate the client secret (Credentials tab > Regenerate)
3. Copy the new value into `.env`:
   - `agentcompany-api` secret → `AGENT_RUNTIME_KEYCLOAK_CLIENT_SECRET`
   - `agent-service` secret → `AGENT_SERVICE_KEYCLOAK_CLIENT_SECRET` (add to `.env.example` if missing)
   - `outline` secret → `OUTLINE_OIDC_CLIENT_SECRET`

### Default admin user

The export creates one user: `admin` / `admin` with the `temporary` flag set.
Keycloak will force a password change on first login. This user is for
**development only** — delete or disable it before any production deployment.

### Token lifetimes

- Access token: 15 minutes (`accessTokenLifespan: 900`)
- SSO/refresh session: 30 minutes (`ssoSessionMaxLifespan: 1800`)

---

## Mattermost config (`configs/mattermost/config.json`)

This file is a development baseline. It is NOT automatically mounted into the
Mattermost container by default — Mattermost manages its own config in the
`mattermost_config` Docker volume.

### How to use it

Two options:

**Option A: Volume mount (recommended for reproducible dev environments)**

Add to `docker-compose.yml` under the `mattermost` service:

```yaml
volumes:
  - ./configs/mattermost/config.json:/mattermost/config/config.json:ro
```

Note: Mattermost may overwrite this file on startup. Use `:ro` to prevent that,
but some settings that Mattermost manages internally may then fail to save.

**Option B: Manual configuration via Admin Console**

Start Mattermost, complete the initial setup wizard, then use the System Console
to configure the settings documented in `config.json`. This is safer because
Mattermost handles schema migrations between versions.

### Key settings enabled

- `EnableBotAccountCreation: true` — agents create bot accounts programmatically
- `EnableIncomingWebhooks: true` + `EnableOutgoingWebhooks: true` — integration hooks
- `EnableUserAccessTokens: true` — agents authenticate with long-lived tokens
- `EnableOAuthServiceProvider: true` — optional; for future Keycloak OIDC SSO integration
- `DriverName: postgres` + `DataSource` from environment — uses shared Postgres instance
- `DriverName: amazons3` for file storage — uses MinIO via environment variables

---

## Outline config (`configs/outline/outline.env`)

This file is a documented reference for every Outline environment variable used
by the platform. The actual values are injected by Docker Compose from the root
`.env` file — this file does not need to be mounted.

It is useful when:
- Debugging why an Outline env var is not being picked up
- Onboarding a new engineer who wants to understand what each variable does
- Migrating Outline to a managed hosting solution and needing to re-set variables

---

## `scripts/dev.sh`

Watch-mode development helper. Key design decisions:

- **Infrastructure stays in Docker** — postgres, redis, minio, keycloak, etc.
  continue to run via `docker compose up -d` so service-to-service networking
  works without modification.
- **agent-runtime runs natively** — `uvicorn --reload --reload-dir app` so
  Python changes take effect in under a second, without a Docker build.
- **web-ui runs natively** — `npm run dev` for Next.js HMR.
- **Exit trap** kills both background processes on Ctrl-C; infrastructure
  containers are left running intentionally (fast restart).
- **Graceful degradation** — if `app/main.py` or `package.json` are missing,
  the script warns and continues rather than crashing.

### Prerequisites not handled by dev.sh

dev.sh does NOT install Python packages or npm dependencies from scratch. Run
`setup.sh` or manually install them if starting fresh:

```bash
cd services/agent-runtime && pip install -r requirements.txt
cd services/web-ui && npm install
```

---

## `scripts/seed-data.sh`

Seed script that populates the platform via the agent-runtime REST API and
directly calls the Mattermost and Outline APIs.

### Dependencies

- `curl` and `jq` must be installed
- All services must be running and healthy

### What it creates

| Resource | Details |
|----------|---------|
| Company | "Acme Corp" with default budget settings |
| Org roles | CEO, CTO, CFO, PM, Developer, Designer, QA (7 roles, levels 1-4) |
| Agents | CEO agent (Claude Opus, scheduled heartbeat), Developer agent (Claude Sonnet, event-triggered) |
| Project | "AgentCompany Platform v1" with 5 starter issues |
| Outline doc | "Welcome to AgentCompany" in a General collection |
| Mattermost | "agentcompany" team + Town Square welcome message |

### Idempotency

The script is not fully idempotent. Running it twice will create duplicate
resources where the API allows it. For a clean re-seed, run
`./scripts/teardown.sh --purge` then `./scripts/setup.sh` first.

---

## Known gaps and next steps

| Item | Priority | Notes |
|------|----------|-------|
| Keycloak import automation | High | The realm export must be imported manually after first boot. Consider adding a `keycloak-import` init container to `docker-compose.yml` that runs `kc.sh import` then exits. |
| Replace client secret placeholders | High | `realm-export.json` ships `CHANGE_ME_*` secrets. Document this in the first-run checklist or automate via Keycloak Admin REST API after import. |
| `package-lock.json` for web-ui | High | CI uses `npm ci` which requires `package-lock.json`. Scaffold the lockfile by running `npm install` once locally and committing it. |
| Agent-runtime test suite | High | `test-backend` job runs pytest but `services/agent-runtime/tests/` is empty. Write at minimum a smoke test for the health endpoint. |
| Mattermost OIDC integration | Medium | `config.json` has `EnableOAuthServiceProvider: true` but Keycloak SSO for Mattermost is not wired. Configure via System Console > Authentication > OpenID Connect, pointing at the Keycloak realm. |
| Minio bucket for Mattermost | Medium | `minio-init` in `docker-compose.yml` only creates the `outline` bucket. Add `mattermost` bucket creation to that script. |
| Outline API token bootstrapping | Medium | `seed-data.sh` attempts to fetch an Outline API token via `auth.info` with the utils secret. This is not a supported Outline endpoint in all versions. Replace with a pre-created service account token. |
| Branch protection rules | Low | After the first push, add branch protection to `main`: require CI to pass, require one review, disallow force-push. Do this in GitHub Settings > Branches. |
| Dependabot / Renovate | Low | Add `.github/dependabot.yml` or a Renovate config to keep GitHub Actions, Docker base images, Python packages, and npm packages updated. |
| SBOM and image signing | Low | For production, add `cosign` signing and SBOM generation to `docker-publish.yml` using the `anchore/sbom-action` and `sigstore/cosign-installer` actions. |

---

## Operational runbook

```bash
# Run CI locally before pushing (requires act: https://github.com/nektos/act)
act pull_request

# Trigger a release
git tag v0.1.0 && git push origin v0.1.0

# Pull the published images on another machine
docker pull ghcr.io/<owner>/agentcompany-agent-runtime:0.1.0
docker pull ghcr.io/<owner>/agentcompany-web-ui:0.1.0

# Import Keycloak realm after first boot
docker compose cp configs/keycloak/realm-export.json \
    agentcompany-keycloak:/tmp/realm-export.json
docker compose exec agentcompany-keycloak \
    /opt/keycloak/bin/kc.sh import \
    --file /tmp/realm-export.json \
    --override true

# Start dev mode with hot-reload
./scripts/dev.sh

# Seed sample data
./scripts/seed-data.sh

# Check CI job status
gh run list --workflow ci.yml

# Re-run a failed CI job
gh run rerun <run-id>
```

---

## Environment variables referenced by new files

All existing variables come from the root `.env` / `.env.example` written by
the infrastructure engineer. No new variables are required by the files
delivered in this pass, except:

| Variable | Used by | Notes |
|----------|---------|-------|
| `AGENT_SERVICE_KEYCLOAK_CLIENT_SECRET` | `agent-service` Keycloak client | Not yet in `.env.example` — add when the agent-service client is activated |

---

## GitHub repository

https://github.com/aaron777collins/agentcompany
