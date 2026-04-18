# AgentCompany — Infrastructure Architecture

## Overview

AgentCompany is deployed as a set of Docker Compose services behind a Traefik
reverse proxy.  All services communicate over a private Docker bridge network
(`internal`).  Only Traefik and services that need to receive routed traffic
are also attached to the `external` network.

---

## Network diagram

```mermaid
graph TD
    User([Browser / Client])
    Traefik["Traefik :80/:443\n(reverse proxy)"]

    subgraph external["Docker network: external"]
        Traefik
        WebUI["web-ui :3000\n(Next.js)"]
        AgentRuntime["agent-runtime :8000\n(FastAPI)"]
        Outline["outline :3000\n(wiki)"]
        Mattermost["mattermost :8065\n(chat)"]
        Keycloak["keycloak :8080\n(SSO)"]
        Meilisearch["meilisearch :7700\n(search)"]
        MinIO["minio :9000/:9001\n(object storage)"]
    end

    subgraph internal["Docker network: internal (no external internet)"]
        Postgres["postgres :5432"]
        Redis["redis :6379"]
        MinIO
        AgentRuntime
        Outline
        Mattermost
        Keycloak
        Meilisearch
        WebUI
    end

    User -->|HTTP/HTTPS| Traefik
    Traefik -->|/app| WebUI
    Traefik -->|/api| AgentRuntime
    Traefik -->|/docs| Outline
    Traefik -->|/chat| Mattermost
    Traefik -->|/auth| Keycloak
    Traefik -->|/search| Meilisearch
    Traefik -->|/plane| PlaneProxy["plane-web\n(external compose)"]

    WebUI --> AgentRuntime
    AgentRuntime --> Postgres
    AgentRuntime --> Redis
    AgentRuntime --> Meilisearch
    AgentRuntime --> Keycloak
    Outline --> Postgres
    Outline --> Redis
    Outline --> MinIO
    Outline --> Keycloak
    Mattermost --> Postgres
    Mattermost --> MinIO
    Keycloak --> Postgres
```

---

## Port mapping table

| Host port | Service | Container port | Protocol | Purpose |
|-----------|---------|----------------|----------|---------|
| 80 | traefik | 80 | HTTP | Public ingress |
| 443 | traefik | 443 | HTTPS | Public ingress (TLS) |
| 8080 | traefik | 8080 | HTTP | Traefik dashboard (dev only) |

All other service ports are bound only to the internal Docker network and are
not accessible from the host.  To inspect a service directly during development
you can temporarily add a `ports:` entry to docker-compose.yml or use:

```bash
docker compose exec postgres psql -U agentcompany agentcompany_core
```

---

## Volume mapping table

| Volume name | Container path | Contents |
|-------------|---------------|---------|
| `postgres_data` | `/var/lib/postgresql/data` | All PostgreSQL databases |
| `redis_data` | `/data` | Redis AOF journal and RDB snapshots |
| `minio_data` | `/data` | MinIO object buckets (Outline attachments, Mattermost files) |
| `meilisearch_data` | `/meili_data` | Search indexes |
| `mattermost_config` | `/mattermost/config` | Mattermost `config.json` |
| `mattermost_data` | `/mattermost/data` | Mattermost local file storage (fallback) |
| `mattermost_logs` | `/mattermost/logs` | Mattermost log files |
| `mattermost_plugins` | `/mattermost/plugins` | Mattermost server-side plugins |
| `mattermost_client_plugins` | `/mattermost/client/plugins` | Mattermost client-side plugins |
| `traefik_certs` | `/certs` | ACME certificate JSON (Let's Encrypt) |

---

## Service dependency graph

Services start in the order dictated by `depends_on` with `condition: service_healthy`.

```
postgres ──────────────────────────────┐
redis ─────────────────────────────────┤
minio ──────────┬──────────────────────┤
                │                      │
            minio-init             keycloak
                                       │
              ┌────────────────────────┤
              │            ┌───────────┘
           outline      mattermost
              │
          (keycloak, postgres, redis, minio)

meilisearch ───────────────────────────┐
postgres ──────────────────────────────┤──▶ agent-runtime ──▶ web-ui
redis ─────────────────────────────────┘
```

Traefik starts independently and begins routing immediately; it will return 502
for any service that is not yet healthy, which is acceptable during boot.

---

## Resource requirements

Estimates are for a single-developer / small team deployment.

| Service | Min RAM | Recommended RAM | CPU (steady state) |
|---------|---------|-----------------|-------------------|
| traefik | 64 MB | 128 MB | < 0.1 core |
| postgres | 256 MB | 512 MB | 0.1 – 0.5 core |
| redis | 64 MB | 256 MB | < 0.1 core |
| minio | 128 MB | 512 MB | 0.1 – 0.3 core |
| keycloak | 512 MB | 1 GB | 0.2 – 0.5 core |
| outline | 256 MB | 512 MB | 0.1 – 0.3 core |
| mattermost | 512 MB | 1 GB | 0.2 – 0.5 core |
| meilisearch | 256 MB | 512 MB | 0.1 – 0.5 core |
| agent-runtime | 256 MB | 512 MB | 0.2 – 1.0 core |
| web-ui | 128 MB | 256 MB | 0.1 – 0.3 core |
| **Total** | **~2.4 GB** | **~5.2 GB** | **~1.5 – 4.1 cores** |

Minimum recommended host: 4 vCPU, 8 GB RAM, 40 GB SSD.

For a full team (10–50 users) with Plane also running: 8 vCPU, 16 GB RAM, 100 GB SSD.

---

## Scaling considerations

### Horizontal scaling (multiple replicas)

The following services are stateless and can be scaled horizontally by
increasing the `replicas` count (requires Docker Swarm or Kubernetes):

- `agent-runtime` — stateless FastAPI; all state lives in Postgres/Redis
- `web-ui` — Next.js; stateless if session data is stored in agent-runtime

The following services require additional configuration before scaling:

- `outline` — Redis-based pub/sub is already configured; file storage is
  delegated to MinIO, so multiple replicas are safe.
- `mattermost` — Requires the cluster-mode license (Enterprise) to run more
  than one replica.
- `keycloak` — Supports clustering (Infinispan cache); set
  `KC_CACHE=ispn` and configure a shared cache.

The following services should remain single-instance or use managed alternatives:

- `postgres` — Use a managed database (RDS, Cloud SQL) or set up streaming
  replication + pgBouncer for high availability.
- `redis` — Use Redis Sentinel or a managed Redis service for HA.
- `minio` — MinIO supports distributed mode; in production use at least 4 nodes
  or replace with AWS S3 / GCS.
- `meilisearch` — Single-instance in v1; multi-node federation is on the roadmap.

### Production hardening checklist

- [ ] Replace `start-dev` with `start` in the Keycloak command + configure TLS
- [ ] Enable HTTPS in Traefik and point `KEYCLOAK_HOSTNAME` to your domain
- [ ] Set `MEILISEARCH_ENV=production` (disables the search preview UI)
- [ ] Restrict Traefik dashboard access with Basic Auth or IP allowlist
- [ ] Move Postgres, Redis, and MinIO to managed cloud services
- [ ] Configure SMTP for email notifications in Outline and Mattermost
- [ ] Enable log aggregation (ship container logs to Loki, Datadog, etc.)
- [ ] Set resource limits (`mem_limit`, `cpus`) on all containers

---

## Plane integration

Plane ships its own docker-compose with ~15 tightly-coupled services and is
excluded from the main docker-compose.yml to avoid merge conflicts when
upgrading Plane independently.

**Recommended integration steps:**

1. Clone the Plane repository alongside this repo:
   ```bash
   git clone https://github.com/makeplane/plane.git ../plane
   ```
2. Follow Plane's setup guide (`make setup`) to generate its `.env`.
3. Add the `agentcompany_external` network to Plane's `proxy` service:
   ```yaml
   networks:
     - default
     - agentcompany_external
   ```
4. Add the external network to Plane's `docker-compose.yml` bottom section:
   ```yaml
   networks:
     agentcompany_external:
       external: true
   ```
5. Start Plane: `docker compose -f ../plane/docker-compose.yml up -d`
6. Update `docker/traefik/dynamic.yml` to point the Plane service URL at
   the correct container name (e.g. `http://plane-proxy:80`).
