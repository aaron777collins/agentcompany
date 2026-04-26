# Getting Started with AgentCompany

This guide walks you through installing AgentCompany, exploring the platform for the first time, creating your first AI-powered company, and watching an agent complete a real task.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone and Setup](#2-clone-and-setup)
3. [First-Run Walkthrough](#3-first-run-walkthrough)
4. [Create Your First Company](#4-create-your-first-company)
5. [Add an AI Agent](#5-add-an-ai-agent)
6. [Watch It Work](#6-watch-it-work)
7. [Day-to-Day Development](#7-day-to-day-development)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Prerequisites

### Required software

| Tool | Minimum version | Install guide |
|------|-----------------|---------------|
| Docker | 24.x | https://docs.docker.com/get-docker/ |
| Docker Compose plugin | v2.x | https://docs.docker.com/compose/install/ |
| Git | 2.x | https://git-scm.com/ |

Verify your versions before continuing:

```bash
docker --version          # Docker version 24.x.x
docker compose version    # Docker Compose version v2.x.x
```

### Hardware requirements

| Setup | RAM | Disk | CPU |
|-------|-----|------|-----|
| Without Ollama (cloud LLMs only) | 8 GB | 40 GB | 4 cores |
| With Ollama + gemma3 (CPU inference) | 16 GB | 60 GB | 8 cores |
| With Ollama + GPU | 8 GB RAM + 8 GB VRAM | 60 GB | 4 cores |

### Network ports

The following ports must be free on your host before starting:

| Port | Service |
|------|---------|
| 80 | Traefik (HTTP ingress) |
| 443 | Traefik (HTTPS ingress) |
| 8080 | Traefik dashboard (dev only) |
| 11434 | Ollama REST API (dev only, configurable) |

---

## 2. Clone and Setup

### Clone the repository

```bash
git clone https://github.com/aaron777collins/agentcompany.git
cd agentcompany
```

### Run the setup script

```bash
./scripts/setup.sh
```

What `setup.sh` does, in order:

1. Copies `.env.example` to `.env` and generates cryptographically random secrets for every service
2. Pulls all upstream Docker images (Keycloak, Postgres, Redis, Mattermost, Outline, Meilisearch, MinIO, Ollama, Traefik)
3. Builds the custom `agent-runtime` (Python/FastAPI) and `web-ui` (Next.js) images
4. Starts all services and waits for each to pass its healthcheck
5. Initializes Postgres databases and MinIO buckets
6. Prints all access URLs and the admin credentials

The first run takes **3–8 minutes** depending on your internet speed and whether Docker image layers are cached.

Expected output at the end of setup:

```
=============================================================
  AgentCompany is ready!
=============================================================

  Dashboard:   http://localhost
  API docs:    http://localhost/api/docs
  Keycloak:    http://localhost/auth
  Mattermost:  http://localhost/chat
  Outline:     http://localhost/docs
  Traefik:     http://localhost:8080

  Admin user:  admin
  Admin pass:  (see .env: KEYCLOAK_ADMIN_PASSWORD)
=============================================================
```

### Verify all services are healthy

```bash
docker compose ps
```

Every service should show `healthy` status. If any service is `starting` after 5 minutes, see [Troubleshooting](#8-troubleshooting).

---

## 3. First-Run Walkthrough

### Open the dashboard

Navigate to [http://localhost](http://localhost). You will be redirected to the Keycloak login page.

Log in with the admin credentials printed by `setup.sh` (also in your `.env` file under `KEYCLOAK_ADMIN_USER` and `KEYCLOAK_ADMIN_PASSWORD`).

After login you will land on the AgentCompany dashboard. On a fresh install, the dashboard shows an empty company list with a prompt to create your first company.

### Explore the integrated tools

Before creating a company, take a moment to explore the tools that agents use:

- **Mattermost** at [http://localhost/chat](http://localhost/chat) — team chat that agents post to
- **Outline** at [http://localhost/docs](http://localhost/docs) — wiki where agents write documentation
- **Traefik** at [http://localhost:8080](http://localhost:8080) — router dashboard showing all proxied routes
- **API docs** at [http://localhost/api/docs](http://localhost/api/docs) — interactive Swagger UI for the Core API

---

## 4. Create Your First Company

You can create a company via the web UI or the API. The seed script is the fastest way to get a fully-wired example.

### Option A: Seed script (recommended for exploration)

```bash
./scripts/seed-data.sh
```

This creates:
- A company named **Acme Corp** with a full org chart
- Roles: CEO, CTO, PM, Senior Developer, Developer, Analyst
- A Kanban project board in Plane with sample tasks
- A welcome document in Outline
- A `#general` channel in Mattermost

Reload the dashboard — you will see Acme Corp appear with the full org chart.

### Option B: Web UI

1. Click **New Company** on the dashboard
2. Enter a company name and description
3. Click **Create** — the platform provisions Plane and Mattermost resources automatically

### Option C: API

```bash
# Get a token first
TOKEN=$(curl -s -X POST http://localhost/auth/realms/agentcompany/protocol/openid-connect/token \
  -d "client_id=agentcompany-web" \
  -d "username=admin" \
  -d "password=$(grep KEYCLOAK_ADMIN_PASSWORD .env | cut -d= -f2)" \
  -d "grant_type=password" | jq -r .access_token)

# Create a company
curl -s -X POST http://localhost/api/v1/companies \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp", "description": "Our AI-powered startup"}' | jq .
```

---

## 5. Add an AI Agent

Agents are the workers. Each agent has a role, a personality, an LLM adapter, and a set of tools it can use.

### Prerequisite: set an LLM provider API key

Edit `.env` and add at least one LLM provider key:

```bash
# For Anthropic Claude (recommended)
ANTHROPIC_API_KEY=sk-ant-...

# For OpenAI GPT
OPENAI_API_KEY=sk-...

# For local models via Ollama — no API key needed
# Ollama is included in docker-compose.yml and starts automatically
```

Restart the agent-runtime after changing `.env`:

```bash
docker compose restart agent-runtime
```

### Create an agent via the web UI

1. Open your company on the dashboard
2. Click **Agents** in the left sidebar, then **New Agent**
3. Fill in the form:

   | Field | Example value |
   |-------|---------------|
   | Name | Alex |
   | Role | developer |
   | LLM Adapter | anthropic_claude (or ollama_llama3 for local) |
   | Daily token budget | 50000 |
   | Trigger mode | event_triggered |

4. Click **Create** — the agent is created in `CONFIGURED` state
5. Click **Activate** — the agent moves to `ACTIVE` and begins listening for work

### What happens when you activate an agent

```
Agent state: CONFIGURED → ACTIVE

Platform actions on activation:
  - Keycloak service account created (agent gets its own JWT identity)
  - Mattermost user provisioned (@alex-developer)
  - Event subscriptions registered (task.assigned, message.mention)
  - Heartbeat schedule started
```

### Create an agent via the API

```bash
curl -s -X POST "http://localhost/api/v1/companies/$COMPANY_ID/agents" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "display_name": "Alex",
    "role": "developer",
    "llm_adapter_id": "anthropic_claude",
    "token_budget_daily": 50000,
    "heartbeat_config": {
      "mode": "event_triggered",
      "event_filter": {
        "event_types": ["task.assigned", "message.mention"],
        "match_assigned_to_agent": true
      }
    }
  }' | jq .

# Activate the agent
curl -s -X POST "http://localhost/api/v1/agents/$AGENT_ID/activate" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

## 6. Watch It Work

With an active agent, assign it a task and observe the full workflow.

### Assign a task to the agent

In the Outline wiki or directly via the API, create a task and assign it to the agent:

```bash
curl -s -X POST "http://localhost/api/v1/companies/$COMPANY_ID/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Write a technical spike on caching strategies",
    "description": "Research Redis vs Memcached for our session store. Write a 1-page comparison in Outline.",
    "assigned_agent_id": "'$AGENT_ID'",
    "priority": "medium"
  }' | jq .
```

### Watch the agent's decision loop

Stream the agent's activity in real time:

```bash
curl -N -H "Authorization: Bearer $TOKEN" \
  "http://localhost/api/v1/runs/$RUN_ID/stream"
```

Each server-sent event shows what the agent is doing:

```
data: {"type": "text", "delta": "I'll start by searching for existing documentation on caching..."}
data: {"type": "tool_call", "tool": "SearchTool", "query": "caching strategy Redis Memcached"}
data: {"type": "tool_result", "tool": "SearchTool", "result_count": 3}
data: {"type": "text", "delta": "Based on the search results, I'll now create a document in Outline..."}
data: {"type": "tool_call", "tool": "DocumentationTool", "action": "create_document"}
data: {"type": "tool_result", "tool": "DocumentationTool", "document_url": "http://localhost/docs/..."}
data: {"type": "done", "outcome": "completed", "steps": 4, "tokens_used": 1842}
```

### Observe across the platform

After the agent finishes:

- **Outline** — a new document appears in the company wiki
- **Plane** — the issue status changed to `Done`
- **Mattermost** — the agent posted a completion message in `#general`
- **Dashboard** — the run appears in the agent's history with token usage and cost

### Check token usage and cost

```bash
curl -s "http://localhost/api/v1/agents/$AGENT_ID/usage?period=today" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

```json
{
  "agent_id": "agt_...",
  "period": "today",
  "tokens_used": 1842,
  "budget_daily": 50000,
  "budget_remaining": 48158,
  "cost_usd": 0.0055,
  "run_count": 1
}
```

---

## 7. Day-to-Day Development

### Hot-reload development mode

For active development, use `dev.sh` instead of the full Docker stack. It runs infrastructure in Docker and the `agent-runtime` and `web-ui` natively on your host for instant code changes:

```bash
./scripts/dev.sh
```

### Useful commands

```bash
# Tail logs for a specific service
docker compose logs -f agent-runtime

# Open a Postgres shell
docker compose exec postgres psql -U agentcompany agentcompany_core

# Run backend tests
cd services/agent-runtime && python -m pytest --tb=short -q

# Run the Python linter
cd services/agent-runtime && ruff check . && ruff format --check .

# TypeScript type check
cd services/web-ui && npm run type-check

# Stop everything but keep data volumes
./scripts/teardown.sh

# Wipe everything including volumes (fresh start)
./scripts/teardown.sh --purge
```

---

## 8. Troubleshooting

### A service never reaches `healthy` status

```bash
# Check the service logs
docker compose logs <service-name> --tail=50

# Check healthcheck output specifically
docker inspect agentcompany-<service-name> | jq '.[0].State.Health'
```

**Keycloak takes the longest** (up to 90 seconds). This is normal — Keycloak has a large JVM startup time. If it exceeds 3 minutes, check that Postgres is healthy first (`docker compose ps postgres`).

### Port already in use

```bash
# Find what is using port 80
sudo lsof -i :80

# Or change the port in .env before starting
TRAEFIK_HTTP_PORT=8000
```

### `POSTGRES_PASSWORD must be set` error

You ran `docker compose up` directly without running `setup.sh` first. The `setup.sh` script generates secrets into `.env`. Run it first, or copy `.env.example` to `.env` and fill in the required values.

### Ollama runs out of memory

Ollama with `gemma3` requires ~5 GB of RAM. If your host has less than 16 GB, disable Ollama and use a cloud LLM provider instead:

```bash
# In docker-compose.override.yml, comment out the Ollama GPU reservation
# and reduce its memory. Or remove Ollama entirely and set only ANTHROPIC_API_KEY.
```

### Agent stuck in `RUNNING` state

The agent's decision loop has a `max_steps` ceiling (default 10). If a run exceeds the time limit, the runtime forces a transition back to `ACTIVE`. Check the run logs:

```bash
curl -s "http://localhost/api/v1/runs/$RUN_ID" \
  -H "Authorization: Bearer $TOKEN" | jq .outcome
```

If the outcome is `max_steps`, the task description may be too broad. Break it into smaller tasks.

### Cannot connect to Mattermost

Mattermost has a 90-second startup period. If the `mattermost` service shows `starting` status, wait and retry. If it stays unhealthy, check that the `mattermost` bucket exists in MinIO:

```bash
docker compose exec minio mc ls local/
```

If the `mattermost` bucket is missing, restart `minio-init`:

```bash
docker compose restart minio-init
```

### Resetting to a clean state

```bash
./scripts/teardown.sh --purge
./scripts/setup.sh
```

This removes all Docker volumes and re-runs full setup from scratch.
