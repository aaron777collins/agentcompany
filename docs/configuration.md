# Configuration Reference

All configuration is managed through environment variables in `.env`. The `setup.sh` script generates `.env` from `.env.example` with random secrets pre-filled. Edit `.env` directly to customize behavior.

---

## Table of Contents

1. [Core Platform](#1-core-platform)
2. [PostgreSQL](#2-postgresql)
3. [Redis](#3-redis)
4. [Keycloak (Identity)](#4-keycloak-identity)
5. [MinIO (Object Storage)](#5-minio-object-storage)
6. [Outline (Documentation)](#6-outline-documentation)
7. [Mattermost (Chat)](#7-mattermost-chat)
8. [Meilisearch (Search)](#8-meilisearch-search)
9. [LLM Providers](#9-llm-providers)
10. [Ollama (Local LLMs)](#10-ollama-local-llms)
11. [Traefik (Reverse Proxy)](#11-traefik-reverse-proxy)
12. [Docker Compose Overrides](#12-docker-compose-overrides)
13. [GPU Configuration for Ollama](#13-gpu-configuration-for-ollama)
14. [Production Deployment Checklist](#14-production-deployment-checklist)
15. [Scaling Considerations](#15-scaling-considerations)

---

## 1. Core Platform

Variables used by the `agent-runtime` service.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `APP_ENV` | No | `development` | Environment name. Set to `production` to enable production defaults. |
| `LOG_LEVEL` | No | `info` | Log verbosity: `debug`, `info`, `warning`, `error` |
| `SECRET_KEY` | **Yes** | (generated) | Random secret for internal token signing. Must be 32+ chars. |
| `AGENT_RUNTIME_SECRET_KEY` | **Yes** | (generated) | Same as above, but scoped to the agent-runtime service. |
| `WEB_UI_API_URL` | No | `http://localhost/api` | URL the browser uses to reach the Core API. |
| `WEB_UI_KEYCLOAK_CLIENT_ID` | No | `agentcompany-web` | Keycloak client ID for the web UI. |

---

## 2. PostgreSQL

A single PostgreSQL 16 instance hosts all databases. Each service (Keycloak, Outline, Mattermost, AgentCompany core) gets its own database within this instance.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `POSTGRES_USER` | No | `agentcompany` | Superuser name for the PostgreSQL instance. |
| `POSTGRES_PASSWORD` | **Yes** | (generated) | Superuser password. Must be set — Docker Compose will refuse to start without it. |

The `docker/init-scripts/init-databases.sql` file creates individual databases on first boot:
- `agentcompany_core` — AgentCompany platform data
- `keycloak` — Keycloak realm data
- `outline` — Outline wiki data
- `mattermost` — Mattermost chat data

To connect directly during development:

```bash
docker compose exec postgres psql -U agentcompany agentcompany_core
```

---

## 3. Redis

Redis 7 is used as a cache, event bus (Pub/Sub), and task queue (Streams).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_PASSWORD` | **Yes** | (generated) | Authentication password. Required by the `requirepass` directive in `redis.conf`. |
| `REDIS_MAX_MEMORY` | No | `256mb` | Maximum memory limit. Eviction policy is `allkeys-lru`. Increase for larger teams. |

Redis data is persisted via AOF (append-only file) to the `redis_data` Docker volume.

---

## 4. Keycloak (Identity)

Keycloak 24 handles all authentication and authorization. It issues JWTs for both human users (OIDC authorization code flow with PKCE) and agents (client credentials flow).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KEYCLOAK_ADMIN_USER` | No | `admin` | Keycloak admin console username. |
| `KEYCLOAK_ADMIN_PASSWORD` | **Yes** | (generated) | Keycloak admin console password. |
| `KEYCLOAK_HOSTNAME` | No | `http://localhost` | Public-facing hostname. Used in OIDC redirect URIs and token issuer claims. Set this to your domain in production. |
| `KEYCLOAK_REALM` | No | `agentcompany` | Keycloak realm name. All clients, roles, and users live within this realm. |
| `AGENT_RUNTIME_KEYCLOAK_CLIENT_ID` | No | `agentcompany-api` | Keycloak client the agent-runtime uses for service-to-service calls. |
| `AGENT_RUNTIME_KEYCLOAK_CLIENT_SECRET` | No | (generated) | Client secret for the above. |

The realm configuration is bootstrapped from `configs/keycloak/realm-export.json` on first startup.

**Important for production**: Switch Keycloak from `start-dev` to `start` in `docker-compose.yml` and configure proper TLS. `start-dev` disables security checks and is not suitable for production.

---

## 5. MinIO (Object Storage)

MinIO provides S3-compatible object storage for file attachments in Outline and Mattermost. It uses the S3 API, so you can swap it for AWS S3, Google Cloud Storage, or any S3-compatible service.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MINIO_ROOT_USER` | No | `agentcompany` | MinIO root access key (equivalent to AWS `access_key_id`). |
| `MINIO_ROOT_PASSWORD` | **Yes** | (generated) | MinIO root secret key (equivalent to AWS `secret_access_key`). |
| `MINIO_BROWSER_REDIRECT_URL` | No | `http://localhost/minio-console` | URL shown in the MinIO console redirect. |
| `OUTLINE_S3_BUCKET` | No | `outline` | Name of the bucket created for Outline attachments. |

---

## 6. Outline (Documentation)

Outline 0.78 serves as the team wiki. Agents write documents here and humans read them.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OUTLINE_SECRET_KEY` | **Yes** | (generated) | 32-character random hex string used to sign sessions. |
| `OUTLINE_UTILS_SECRET` | **Yes** | (generated) | Separate secret for utility operations. |
| `OUTLINE_URL` | No | `http://localhost/docs` | Public URL of the Outline instance. Used in email notifications and links. |
| `OUTLINE_OIDC_CLIENT_ID` | No | `outline` | Keycloak OIDC client ID for Outline SSO. |
| `OUTLINE_OIDC_CLIENT_SECRET` | **Yes** | (generated) | OIDC client secret. Must match the client configured in Keycloak. |

### Optional SMTP for Outline

Set these variables to enable email notifications from Outline:

| Variable | Default | Description |
|----------|---------|-------------|
| `SMTP_HOST` | (empty) | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port (587 for STARTTLS, 465 for TLS) |
| `SMTP_USERNAME` | (empty) | SMTP authentication username |
| `SMTP_PASSWORD` | (empty) | SMTP authentication password |
| `SMTP_FROM_EMAIL` | `noreply@agentcompany.local` | From address in outbound email |

---

## 7. Mattermost (Chat)

Mattermost 9 is the team chat system. Agents post messages here using a bot account provisioned for each agent.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MATTERMOST_SITE_URL` | No | `http://localhost/chat` | Public URL of the Mattermost instance. Must be set correctly for webhooks to work. |

Mattermost uses the shared Postgres instance and MinIO for file storage. All Mattermost-specific settings (email notifications, integrations, plugin configuration) are managed via the Mattermost admin console at `http://localhost/chat/admin_console`.

---

## 8. Meilisearch (Search)

Meilisearch 1.7 provides full-text search across tasks, documents, and chat messages.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MEILISEARCH_MASTER_KEY` | **Yes** | (generated) | Master key that grants full administrative access. Used only by the agent-runtime. |
| `MEILISEARCH_ENV` | No | `development` | Set to `production` to disable the search preview UI (`http://localhost/search`). Always set to `production` in production. |

In `development` mode, the Meilisearch UI is accessible without authentication. In `production` mode, all API calls require the master key or a scoped API key.

---

## 9. LLM Providers

Set at least one LLM provider API key. Agents use the provider specified by their `llm_adapter_id` configuration.

### Anthropic Claude

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | If using Claude | API key from https://console.anthropic.com |

Available adapter IDs when this key is set:

| Adapter ID | Model | Best for |
|------------|-------|----------|
| `anthropic_claude` | claude-sonnet-4-6 | General-purpose agents (default) |
| `anthropic_claude_opus` | claude-opus-4-5 | High-complexity reasoning (higher cost) |
| `anthropic_claude_haiku` | claude-haiku-4-5 | High-volume low-cost tasks |

### OpenAI GPT

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | If using GPT | API key from https://platform.openai.com |

Available adapter IDs when this key is set:

| Adapter ID | Model | Best for |
|------------|-------|----------|
| `openai_gpt4o` | gpt-4o | Balanced capability and cost |
| `openai_gpt4o_mini` | gpt-4o-mini | High-volume low-cost tasks |

### Per-agent LLM selection

Each agent stores its `llm_adapter_id` in its configuration. You can mix providers within a single company — for example, run the CEO on Claude Opus for best reasoning while Developer agents use Claude Haiku for cost efficiency.

---

## 10. Ollama (Local LLMs)

Ollama is included in `docker-compose.yml` for local, private, zero-cost inference. It starts automatically and exposes an OpenAI-compatible API.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OLLAMA_BASE_URL` | No | `http://ollama:11434` | URL the agent-runtime uses to reach Ollama. Change only if running Ollama externally. |
| `OLLAMA_PORT` | No | `11434` | Host port to bind Ollama on for direct development access. |

Available adapter IDs when Ollama is running:

| Adapter ID | Model | Notes |
|------------|-------|-------|
| `ollama_llama3` | llama3.2 | Default local model |

### Pulling models

Models must be pulled before they can be used. Pull a model while Ollama is running:

```bash
docker compose exec ollama ollama pull gemma3
docker compose exec ollama ollama pull llama3.2
docker compose exec ollama ollama pull nomic-embed-text  # for embeddings
```

Model weights are stored in the `ollama_data` Docker volume. A full model download can be several GB.

### Verify Ollama is working

```bash
curl http://localhost:11434/api/tags | jq .models[].name
```

---

## 11. Traefik (Reverse Proxy)

Traefik routes all public traffic. Static configuration lives in `docker/traefik/traefik.yml` and dynamic route configuration in `docker/traefik/dynamic.yml`.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TRAEFIK_HTTP_PORT` | No | `80` | Host port for HTTP traffic |
| `TRAEFIK_HTTPS_PORT` | No | `443` | Host port for HTTPS traffic |
| `TRAEFIK_DASHBOARD_PORT` | No | `8080` | Host port for the Traefik dashboard (dev only — disable in production) |

---

## 12. Docker Compose Overrides

`docker-compose.override.yml` is automatically merged with `docker-compose.yml` by Docker Compose. Use it for environment-specific changes without modifying the base file.

The repository ships a default `docker-compose.override.yml` that strips the NVIDIA GPU reservation from the Ollama service. This makes the setup work on any machine, including those without NVIDIA GPUs.

```yaml
# docker-compose.override.yml (default — CPU-only Ollama)
services:
  ollama:
    deploy:
      resources: {}  # Removes the GPU reservation from docker-compose.yml
```

### Common override patterns

**Expose a service port for debugging:**

```yaml
services:
  postgres:
    ports:
      - "5432:5432"  # Allows direct Postgres connections from the host
```

**Override a service's memory limit:**

```yaml
services:
  agent-runtime:
    mem_limit: 1g
```

**Use an external Postgres instead of the bundled one:**

```yaml
services:
  agent-runtime:
    environment:
      DATABASE_URL: postgres://user:pass@external-host:5432/agentcompany
  postgres:
    profiles: [disabled]  # Prevents the bundled Postgres from starting
```

---

## 13. GPU Configuration for Ollama

GPU inference with Ollama is much faster than CPU and reduces memory pressure on the host.

### NVIDIA GPU

**Requirements:**
- NVIDIA driver 525+ on the host
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed

**Setup:**

1. Delete or rename `docker-compose.override.yml`. The base `docker-compose.yml` already includes the GPU reservation:

```yaml
# In docker-compose.yml (already present)
ollama:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
```

2. Restart Ollama:

```bash
docker compose up -d ollama
```

3. Verify GPU access:

```bash
docker compose exec ollama nvidia-smi
docker compose exec ollama ollama run gemma3 "Hello, world"
```

### CPU-only (default)

The default `docker-compose.override.yml` removes the GPU reservation so Ollama falls back to CPU. No additional configuration is required.

---

## 14. Production Deployment Checklist

Before deploying AgentCompany in a production environment, work through this checklist.

### Security

- [ ] Set `APP_ENV=production` in `.env`
- [ ] Replace all `setup.sh`-generated secrets with your own cryptographically random values
- [ ] Ensure `.env` is not committed to version control (it is in `.gitignore` by default)
- [ ] Change the Keycloak startup command from `start-dev` to `start` in `docker-compose.yml`
- [ ] Set `KEYCLOAK_HOSTNAME` to your actual domain (e.g., `https://auth.example.com`)
- [ ] Set `MEILISEARCH_ENV=production` (disables the unauthenticated search preview UI)
- [ ] Enable Traefik HTTPS: configure the ACME section in `docker/traefik/traefik.yml` with your email and domain
- [ ] Disable the Traefik dashboard or protect it with Basic Auth / IP allowlist
- [ ] Verify the Agent Runtime has no exposed Traefik routes (it is internal-only by design)
- [ ] Enable `pgaudit` extension in PostgreSQL for query-level audit logging
- [ ] Enable MFA in Keycloak for all human accounts (Keycloak admin console → Realm Settings → Authentication)

### Infrastructure

- [ ] Move PostgreSQL to a managed database (RDS, Cloud SQL, Supabase) or set up streaming replication + PgBouncer
- [ ] Move Redis to a managed service (ElastiCache, Redis Cloud) or Redis Sentinel for HA
- [ ] Move MinIO to AWS S3, Google Cloud Storage, or a distributed MinIO cluster (minimum 4 nodes)
- [ ] Configure log shipping: send container logs to Loki, Datadog, or your SIEM
- [ ] Set `mem_limit` and `cpus` resource limits on all containers to prevent one runaway service from starving the host
- [ ] Configure backup schedules for PostgreSQL (pg_dump or continuous WAL archiving) and MinIO (bucket replication)

### Networking

- [ ] Point `KEYCLOAK_HOSTNAME`, `OUTLINE_URL`, and `MATTERMOST_SITE_URL` to your production domain(s)
- [ ] Configure Traefik TLS with Let's Encrypt or your certificate authority
- [ ] If Plane is deployed separately, follow the integration steps in `docs/architecture/infrastructure.md` to attach it to the `agentcompany_external` network

### Operations

- [ ] Configure SMTP for email notifications in Outline and Mattermost
- [ ] Set up Grafana alerting for key metrics: service up/down, high queue depth, agent budget exhaustion
- [ ] Run `trivy image agentcompany/agent-runtime:latest` before each release to check for CVEs
- [ ] Set up Dependabot (or equivalent) on the repository for automatic dependency updates

---

## 15. Scaling Considerations

### Horizontal scaling

The following services are stateless and can be replicated without extra configuration:

| Service | How to scale |
|---------|-------------|
| `agent-runtime` | Add replicas behind Traefik load balancing. All state is in Postgres and Redis. |
| `web-ui` | Add replicas behind Traefik. Stateless Next.js with server-side rendering. |

These services require additional setup before scaling:

| Service | What to configure |
|---------|-------------------|
| `outline` | Already uses Redis for pub/sub and MinIO for storage — safe to add replicas |
| `mattermost` | Requires Mattermost Enterprise for cluster mode. Single replica in community edition. |
| `keycloak` | Enable Infinispan clustering (`KC_CACHE=ispn`) for active-active HA |

### Kubernetes (future state)

The architecture document at `docs/architecture/system-overview.md` includes a Kubernetes target state using:
- **CloudNativePG** operator for PostgreSQL HA
- **Redis Sentinel** or Redis Operator
- **Traefik IngressController** with cert-manager for TLS
- **HPA** on Agent Runtime, scaling on Redis queue depth

The Docker Compose deployment is designed to be a direct path to Kubernetes — services are independently addressable, stateless where possible, and configured entirely through environment variables.
