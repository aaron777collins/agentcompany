# Docker Hardening Handoff — AgentCompany

**Date:** 2026-04-18  
**Author:** Staff Software Engineer  
**Recipient:** Next platform / DevOps engineer

---

## Summary

This pass hardened the Docker setup and wired in Plane as an optional sidecar. Six deliverables were produced:

| # | Deliverable | Path |
|---|-------------|------|
| 1 | agent-runtime entrypoint | `docker/agent-runtime/entrypoint.sh` |
| 2 | web-ui entrypoint | `docker/web-ui/entrypoint.sh` |
| 3 | Plane sidecar compose | `docker-compose.plane.yml` |
| 4 | Traefik labels (Plane services) | `docker-compose.plane.yml` labels |
| 5 | Health check script | `scripts/healthcheck.sh` |
| 6 | Backup / restore scripts | `scripts/backup.sh`, `scripts/restore.sh` |

Supporting changes:
- `docker-compose.yml` — added `entrypoint:` to `agent-runtime` and `web-ui`; removed the busybox `plane-proxy` placeholder
- `docker/init-scripts/init-databases.sql` — added `plane` database creation and extension grants
- `docker/traefik/dynamic.yml` — removed the stale file-based Plane router (replaced by Docker labels)

---

## Task 1 & 2: Entrypoints

### Why entrypoints instead of depends_on alone

`depends_on: condition: service_healthy` only blocks until the container reports healthy. It does not wait for the application inside to finish initialising. In practice:

- PostgreSQL's healthcheck reports healthy as soon as `pg_isready` succeeds, but the database may not yet accept connections from `asyncpg` (SSL negotiation, init scripts still running).
- The web-ui can fail its first few requests if agent-runtime is still running migrations.

The entrypoints add an application-level readiness check on top of Docker's health gate.

### agent-runtime (`docker/agent-runtime/entrypoint.sh`)

1. Polls `asyncpg.connect(DATABASE_URL)` — same connection the app uses, so auth failures are caught early.
2. Runs `alembic upgrade head` — idempotent; safe to run on every startup.
3. Execs `uvicorn` — `exec` replaces the shell so PID 1 is uvicorn (clean signal handling).

The script must be present inside the built image. The `agent-runtime` Dockerfile (in `services/agent-runtime/`) needs to `COPY` the script:

```dockerfile
COPY docker/agent-runtime/entrypoint.sh /app/docker/agent-runtime/entrypoint.sh
RUN chmod +x /app/docker/agent-runtime/entrypoint.sh
```

If the build context is `./services/agent-runtime/` the entrypoint will need to be referenced relative to that context or the Dockerfile must use a multi-stage build that copies from the repo root. The simplest fix is to change the build context in `docker-compose.yml`:

```yaml
agent-runtime:
  build:
    context: .            # repo root
    dockerfile: services/agent-runtime/Dockerfile
```

Or copy the entrypoint file into `services/agent-runtime/docker/` and update the path.

### web-ui (`docker/web-ui/entrypoint.sh`)

Polls `http://agent-runtime:8000/health` before starting `node server.js`. The same Dockerfile copy requirement applies.

---

## Task 3: Plane sidecar (`docker-compose.plane.yml`)

### How to start

```bash
# Full stack including Plane
docker compose -f docker-compose.yml -f docker-compose.plane.yml up -d

# Base stack only (no Plane)
docker compose up -d
```

### Shared infrastructure

| Resource | Used as |
|----------|---------|
| `postgres` | Plane's Django database (`plane` DB — created by init-databases.sql) |
| `redis` | Plane's Redis cache and Celery result backend |
| `minio` | Plane's file storage (`plane-uploads` bucket — created by `plane-minio-init`) |

Plane still needs its own RabbitMQ because its Celery configuration requires an AMQP broker. The `plane-mq` service is included in the compose file.

### Services

| Service | Image | Role |
|---------|-------|------|
| `plane-migrator` | `makeplane/plane-backend:stable` | Runs Django migrations, exits |
| `plane-api` | `makeplane/plane-backend:stable` | Gunicorn/Django backend on :8000 |
| `plane-worker` | `makeplane/plane-backend:stable` | Celery worker |
| `plane-beat` | `makeplane/plane-backend:stable` | Celery beat scheduler |
| `plane-web` | `makeplane/plane-frontend:stable` | Next.js frontend on :3000 |
| `plane-space` | `makeplane/plane-space:stable` | Public board viewer on :3002 |
| `plane-admin` | `makeplane/plane-admin:stable` | God-mode admin on :3001 |
| `plane-mq` | `rabbitmq:3.13-management-alpine` | RabbitMQ task broker |
| `plane-minio-init` | `minio/mc` | Creates the `plane-uploads` bucket, exits |

### New environment variables required

Add these to `.env` (and `.env.example`) before starting Plane:

```dotenv
# Plane project management
PLANE_SECRET_KEY=CHANGE_ME          # Django SECRET_KEY — generate with: openssl rand -hex 32
PLANE_RABBITMQ_PASSWORD=CHANGE_ME   # RabbitMQ password
PLANE_RABBITMQ_USER=plane           # optional, default: plane
PLANE_RABBITMQ_VHOST=plane          # optional, default: plane
PLANE_S3_BUCKET=plane-uploads       # optional, default: plane-uploads
PLANE_BASE_URL=http://localhost      # public base URL for cross-service redirects
PLANE_WEB_URL=http://localhost/plane # used by Plane API for email links
PLANE_CORS_ORIGINS=http://localhost  # comma-separated allowed CORS origins
PLANE_GUNICORN_WORKERS=2            # optional, tunable
```

### Traefik routing

All Plane services are exposed through Traefik on the following paths:

| Path | Service |
|------|---------|
| `/plane` | plane-web (Next.js) |
| `/plane/api`, `/plane/auth` | plane-api (Django) |
| `/plane/spaces` | plane-space |
| `/plane/god-mode` | plane-admin |

The routes use `stripprefix` middlewares defined inline in the Docker labels so that each service receives requests at its expected root path.

---

## Task 5: Health check (`scripts/healthcheck.sh`)

```bash
# Check core services
./scripts/healthcheck.sh

# Check core + Plane sidecar
./scripts/healthcheck.sh --plane
```

Exit code is 0 if all checked services are healthy, 1 otherwise. Safe to use in CI or a monitoring cron job.

---

## Task 6: Backup and restore

### Backup

```bash
./scripts/backup.sh
```

Produces `backups/agentcompany-backup-<timestamp>.tar.gz` containing:

```
postgres/
  agentcompany_core.sql.gz
  outline.sql.gz
  mattermost.sql.gz
  keycloak.sql.gz
  plane.sql.gz          # only present if the plane DB exists
minio/
  outline/              # bucket contents mirrored from MinIO
  mattermost/
  plane-uploads/
MANIFEST.txt
```

The stack must be running when the backup runs. pg_dump and mc run inside Docker containers (no host-side Postgres or mc installation required).

### Restore

```bash
./scripts/restore.sh backups/agentcompany-backup-<timestamp>.tar.gz
```

The restore script prompts for confirmation because it overwrites all existing data. The stack must be running and the databases must exist (run `./scripts/setup.sh` first if restoring to a fresh host).

### Automation

For scheduled backups, add a cron entry on the host:

```cron
0 2 * * * /home/ubuntu/topics/agentcompany/scripts/backup.sh >> /var/log/agentcompany-backup.log 2>&1
```

Rotate old backups with a find + delete or use an external tool like logrotate.

---

## Known gaps and follow-up items

| Item | Priority | Notes |
|------|----------|-------|
| Dockerfile COPY for entrypoints | High | Both Dockerfiles must COPY their entrypoint script at the path `docker-compose.yml` specifies. See Task 1 & 2 notes above for options. |
| Plane environment variables in `.env.example` | High | The six new `PLANE_*` variables must be added to `.env.example` with `CHANGE_ME` placeholders, and `setup.sh` must auto-generate `PLANE_SECRET_KEY` and `PLANE_RABBITMQ_PASSWORD`. |
| Plane image tag pinning | Medium | The compose file uses `:stable` tags for all Plane images. Pin to a specific version (e.g. `:v1.3.0`) for reproducible deployments once you confirm the stable tag works. |
| RabbitMQ management UI | Low | `plane-mq` uses the `management-alpine` image. The management UI is accessible at port 15672 inside the container but not exposed to the host. Expose it via Traefik or a port binding if needed for debugging. |
| Backup retention policy | Medium | `backup.sh` does not prune old backups. Add a `--keep N` flag or a separate cron job to remove backups older than N days. |
| MinIO restore network name | Medium | `restore.sh` assumes the Docker network is named `agentcompany_internal`. This is correct for the default project name. If compose project name is overridden, update the `--network` flag in the script. |
| Plane OIDC / Keycloak SSO | Low | Plane supports OIDC. Wire it to Keycloak after initial Plane setup by adding `OIDC_*` env vars to `plane-api` in the compose file. |
| Ollama not exposed on port 11434 | Low | `healthcheck.sh` checks `localhost:11434` but the Ollama service in `docker-compose.yml` uses `ports: ["${OLLAMA_PORT:-11434}:11434"]`. This works when using the default port. If `OLLAMA_PORT` is changed, update `healthcheck.sh` accordingly. |

---

## Files written in this pass

| File | Action |
|------|--------|
| `docker/agent-runtime/entrypoint.sh` | Created |
| `docker/web-ui/entrypoint.sh` | Created |
| `docker-compose.plane.yml` | Created |
| `scripts/healthcheck.sh` | Created |
| `scripts/backup.sh` | Created |
| `scripts/restore.sh` | Created |
| `docker-compose.yml` | Edited (entrypoints added, plane-proxy placeholder removed) |
| `docker/init-scripts/init-databases.sql` | Edited (plane database added) |
| `docker/traefik/dynamic.yml` | Edited (stale Plane router removed) |
| `docs/handoffs/docker-hardening-handoff.md` | Created (this file) |
