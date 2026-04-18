# Infrastructure Handoff — AgentCompany

**Date:** 2026-04-18
**Author:** Infrastructure Engineer
**Recipient:** Next engineer (backend / DevOps)

---

## What was built

A complete Docker Compose infrastructure that runs the AgentCompany platform on
a single host.  Every file is production-aware but defaults to development mode
so the first `./scripts/setup.sh` just works.

---

## Files delivered

| File | Purpose |
|------|---------|
| `/docker-compose.yml` | Canonical service definitions for the full platform |
| `/.env.example` | All environment variables with descriptions and CHANGE_ME markers |
| `/docker/traefik/traefik.yml` | Traefik static config (entrypoints, providers, dashboard) |
| `/docker/traefik/dynamic.yml` | Traefik dynamic config (routes, middlewares, TLS) |
| `/docker/init-scripts/init-databases.sql` | Creates Postgres databases for Outline, Mattermost, Keycloak |
| `/scripts/setup.sh` | One-command bootstrap with secret generation |
| `/scripts/teardown.sh` | Graceful shutdown with optional `--purge` |
| `/docs/architecture/infrastructure.md` | Network diagram, port/volume tables, resource estimates |

---

## Getting started (for the next engineer)

```bash
cd /path/to/agentcompany
./scripts/setup.sh
```

That single command handles everything from secret generation to health checks.
Access URLs are printed at the end.

---

## Key architectural decisions and the reasoning behind them

### Single PostgreSQL instance, multiple databases

All four applications (agentcompany_core, outline, mattermost, keycloak) share
one Postgres container but each has its own database.  This keeps the compose
file simple and reduces RAM.  The `init-databases.sql` script creates them on
first boot.  When you need to upgrade Postgres or scale, you can split them
into separate containers without touching application configuration — just
update `DATABASE_URL` per service.

### Two Docker networks: `internal` and `external`

`internal` is a bridge network with `internal: true` (no outbound internet
access) — service-to-service traffic only.  `external` is where Traefik sits
and where it reaches the application containers.  Services that do not need to
be reached by Traefik (postgres, redis, mino-init) are on `internal` only.
This prevents Postgres and Redis from being accidentally exposed even if
someone adds an incorrect Traefik label.

### Plane excluded from docker-compose.yml

Plane's own docker-compose defines ~15 services with shared Postgres
connections, a custom nginx proxy, and Celery workers.  Including all of that
here would make upgrades fragile.  Instead a placeholder `plane-proxy` service
documents the integration pattern, and `dynamic.yml` has a commented-out Plane
router ready to enable.

### MinIO as shared object storage

Both Outline and Mattermost need S3-compatible storage.  MinIO fills that role
with separate buckets per service.  The `minio-init` container runs once at
startup to create buckets idempotently.

### Keycloak as the SSO hub

All user-facing services (Outline, future: Mattermost, Web UI) authenticate
via Keycloak OIDC.  Clients are pre-registered via the admin console after
first boot.  The agent-runtime validates tokens using Keycloak's public JWKS
endpoint — no shared secret needed between services.

---

## Known gaps / next steps

These are not defects; they are items deferred from this phase.

| Item | Priority | Notes |
|------|----------|-------|
| Keycloak realm + client setup | High | Must be done manually via admin UI after first boot; a future task should automate this with the Keycloak admin REST API or Terraform provider |
| Mattermost S3 bucket creation | High | `minio-init` creates the `outline` bucket; add `mattermost` bucket creation to that script |
| `services/agent-runtime/Dockerfile` | High | Placeholder directories exist; the Python service must be scaffolded before `setup.sh` will build it |
| `services/web-ui/Dockerfile` | High | Same as above for Next.js |
| HTTPS / TLS certs | Medium | Traefik ACME config is commented out in `traefik.yml`; uncomment and set email + domain |
| Mattermost OIDC | Medium | Not yet wired to Keycloak; configure via Mattermost admin panel under Authentication > OpenID Connect |
| Resource limits | Medium | No `mem_limit` or `cpus` set — add these before production to prevent a single runaway container from taking down the host |
| Log aggregation | Medium | Container logs currently go to Docker's default json-file driver; add a Loki + Grafana compose extension or ship to a managed service |
| Backup strategy | High | No automated backup exists yet; add a `pg_dump` cron container and MinIO bucket versioning before storing real data |
| Plane full integration | Low | See `docs/architecture/infrastructure.md` Plane integration section for step-by-step instructions |

---

## Operational runbook (quick reference)

```bash
# Start everything
./scripts/setup.sh

# View all service statuses
docker compose ps

# Follow logs for a specific service
docker compose logs -f keycloak

# Restart a single service
docker compose restart outline

# Apply a config change and roll the affected service
docker compose up -d --no-deps outline

# Open a Postgres shell
docker compose exec postgres psql -U agentcompany agentcompany_core

# Open a Redis shell
docker compose exec redis redis-cli -a "$REDIS_PASSWORD"

# Graceful stop (preserve data)
./scripts/teardown.sh

# Full wipe (destroy all data)
./scripts/teardown.sh --purge
```

---

## Environment variables that MUST be set before production

All of the following are auto-generated by `setup.sh` for development.  For
production, audit each one and store them in a secrets manager (HashiCorp Vault,
AWS Secrets Manager, etc.) rather than a plain `.env` file.

- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `KEYCLOAK_ADMIN_PASSWORD`
- `OUTLINE_SECRET_KEY`
- `OUTLINE_UTILS_SECRET`
- `OUTLINE_OIDC_CLIENT_SECRET`
- `MEILISEARCH_MASTER_KEY`
- `AGENT_RUNTIME_SECRET_KEY`
- `AGENT_RUNTIME_KEYCLOAK_CLIENT_SECRET`
