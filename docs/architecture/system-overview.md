# AgentCompany — System Overview

**Version**: 1.0.0
**Date**: 2026-04-18
**Status**: Authoritative Design Document

---

## 1. Problem Statement

AgentCompany is an open-source platform that instantiates AI-powered companies where AI agents and humans collaborate to accomplish business goals. The system integrates proven open-source tools (Plane, Outline, Mattermost, Keycloak) under a unified orchestration layer, enabling agents to autonomously create tasks, write documentation, communicate in chat, and report results — all within a governed, auditable environment.

### Core Challenges

- **Integration complexity**: Five distinct open-source services each with their own APIs, data models, auth schemes, and webhook formats.
- **Agent orchestration**: Routing work to the right agent (or human), managing concurrency, handling failures.
- **Unified identity**: Humans and agents must coexist in a single identity plane with coherent RBAC.
- **Observability**: Token usage, costs, latency, and audit trails must be captured without instrumenting every individual tool.
- **Incremental adoption**: The platform must work with Docker Compose for a single developer and scale to Kubernetes for production.

### Design Constraints

| Constraint | Decision |
|---|---|
| All services are open-source | No proprietary SaaS dependencies at the infra layer |
| MVP runs on a single machine | Docker Compose with defined resource limits |
| Agents must be auditable | Every agent action produces an immutable audit log entry |
| Humans remain in control | Agent actions on high-risk operations require human approval |
| Extensible adapter model | New tools can be added without modifying core platform code |

---

## 2. High-Level Architecture

```mermaid
graph TB
    subgraph External["External Clients"]
        Browser["Browser / Web UI\n(Next.js + TypeScript)"]
        API_Client["API Clients\n(CLI, SDKs)"]
        Webhooks["Inbound Webhooks\n(from tools)"]
    end

    subgraph Gateway["API Gateway Layer"]
        Traefik["Traefik\n(TLS termination, routing,\nrate limiting)"]
    end

    subgraph Core["AgentCompany Core"]
        CoreAPI["Core API Service\n(FastAPI / Python)\nREST + WebSocket"]
        AgentRuntime["Agent Runtime\n(FastAPI / Python)\nLLM orchestration"]
        EventBus["Event Bus\n(Redis Pub/Sub)"]
        TaskQueue["Task Queue\n(Redis Streams)"]
    end

    subgraph Auth["Identity Layer"]
        Keycloak["Keycloak\nSSO + JWT issuance\nRBAC realm"]
    end

    subgraph Tools["Integrated Tools"]
        Plane["Plane\n(Project Management)\nKanban + issues"]
        Outline["Outline\n(Documentation)\nWiki + knowledge base"]
        Mattermost["Mattermost\n(Chat)\nChannels + direct messages"]
        Meilisearch["Meilisearch\n(Search)\nFull-text + semantic"]
    end

    subgraph Data["Data Layer"]
        Postgres["PostgreSQL\n(Primary data store)\nCompanies, agents, audit log"]
        Redis["Redis\n(Cache + pub/sub + streams)"]
        ObjectStore["Object Storage\n(MinIO / S3-compatible)\nFile attachments"]
    end

    subgraph Observability["Observability"]
        Prometheus["Prometheus\n(Metrics scraping)"]
        Grafana["Grafana\n(Dashboards)"]
        Loki["Loki\n(Log aggregation)"]
    end

    Browser -->|HTTPS| Traefik
    API_Client -->|HTTPS| Traefik
    Webhooks -->|HTTPS POST| Traefik

    Traefik -->|/api/v1/*| CoreAPI
    Traefik -->|/auth/*| Keycloak
    Traefik -->|/ui/*| Browser

    CoreAPI -->|verify JWT| Keycloak
    CoreAPI -->|publish events| EventBus
    CoreAPI -->|enqueue tasks| TaskQueue
    CoreAPI -->|read/write| Postgres
    CoreAPI -->|cache| Redis

    AgentRuntime -->|subscribe events| EventBus
    AgentRuntime -->|dequeue tasks| TaskQueue
    AgentRuntime -->|tool calls via adapters| Plane
    AgentRuntime -->|tool calls via adapters| Outline
    AgentRuntime -->|tool calls via adapters| Mattermost
    AgentRuntime -->|search calls| Meilisearch
    AgentRuntime -->|write audit log| Postgres

    Plane -->|webhooks| Traefik
    Outline -->|webhooks| Traefik
    Mattermost -->|webhooks| Traefik

    CoreAPI -->|metrics| Prometheus
    AgentRuntime -->|metrics| Prometheus
    Prometheus --> Grafana
    CoreAPI -->|structured logs| Loki
    AgentRuntime -->|structured logs| Loki
    Loki --> Grafana
```

---

## 3. Component Inventory

### 3.1 First-Party Services

| Service | Language | Role | Exposes | Connects To |
|---|---|---|---|---|
| **Core API** | Python / FastAPI | Primary REST API, business logic, event routing | HTTP :8000, WS :8001 | Postgres, Redis, Keycloak, Meilisearch |
| **Agent Runtime** | Python / FastAPI | LLM agent execution, tool adapter calls | HTTP :8010 (internal) | Redis, Postgres, Plane, Outline, Mattermost, Meilisearch, LLM provider |
| **Web UI** | TypeScript / Next.js | Browser front-end | HTTP :3000 | Core API, Keycloak (OIDC) |

### 3.2 Third-Party Open-Source Services

| Service | Version Target | Role | Default Port | Persistence |
|---|---|---|---|---|
| **Keycloak** | 24.x | SSO, JWT, RBAC realm | 8080 | Postgres (dedicated schema) |
| **Plane** | 0.22.x | Kanban, issues, cycles, sprints | 3001 | Postgres + Redis |
| **Outline** | 0.78.x | Wiki, knowledge base | 3002 | Postgres + Redis + S3 |
| **Mattermost** | 9.x | Team chat, channels, DMs | 8065 | Postgres |
| **Meilisearch** | 1.8.x | Full-text search | 7700 | Local disk |
| **PostgreSQL** | 16.x | Relational data | 5432 | Persistent volume |
| **Redis** | 7.x | Cache, pub/sub, streams | 6379 | AOF persistence |
| **MinIO** | RELEASE.2024 | S3-compatible object store | 9000/9001 | Persistent volume |
| **Traefik** | 3.x | Reverse proxy / API gateway | 80/443 | — |
| **Prometheus** | 2.x | Metrics collection | 9090 | Persistent volume |
| **Grafana** | 10.x | Visualization | 3003 | Persistent volume |
| **Loki** | 3.x | Log aggregation | 3100 | Persistent volume |

### 3.3 Component Responsibilities

**Core API**
- Serves all `/api/v1/*` endpoints documented in `api-design.md`
- Validates JWT tokens against Keycloak JWKS endpoint
- Enforces RBAC policy — no business logic runs outside authorization check
- Routes inbound webhooks from tools to the appropriate event handler
- Maintains the canonical AgentCompany data model (companies, agents, roles, tasks)
- Publishes normalized events to Redis Pub/Sub for Agent Runtime consumption

**Agent Runtime**
- Subscribes to event channels on Redis
- Executes LLM inference calls (configurable provider: OpenAI, Anthropic, Ollama)
- Calls tool adapters (Plane, Outline, Mattermost) to take actions
- Records every action to the audit log before and after execution
- Reports token usage and cost per task completion
- Implements circuit-breaker and retry logic per adapter

**Web UI**
- Server-side rendered Next.js application
- Authenticates via Keycloak OIDC (authorization code flow with PKCE)
- Renders company dashboard, agent roster, task board, chat integration
- Connects to Core API via REST and WebSocket for real-time updates

---

## 4. Data Flow Diagrams

### 4.1 Human Creates a Task (Task Assignment Flow)

```mermaid
sequenceDiagram
    actor Human
    participant UI as Web UI
    participant Gateway as Traefik
    participant CoreAPI as Core API
    participant Keycloak
    participant Postgres
    participant Redis as Redis Pub/Sub
    participant Runtime as Agent Runtime
    participant Plane

    Human->>UI: Creates task "Research competitors"
    UI->>Gateway: POST /api/v1/tasks (JWT in header)
    Gateway->>CoreAPI: Forward request
    CoreAPI->>Keycloak: Validate JWT (JWKS)
    Keycloak-->>CoreAPI: Claims: {sub, roles, org_id}
    CoreAPI->>CoreAPI: Authorize: user has task:create permission
    CoreAPI->>Postgres: INSERT into tasks
    CoreAPI->>Plane: PlaneAdapter.create_issue(task)
    Plane-->>CoreAPI: issue_id
    CoreAPI->>Postgres: UPDATE task SET external_ref = issue_id
    CoreAPI->>Redis: PUBLISH agent_events {type: task.created, task_id, assignee_agent_id}
    CoreAPI-->>Gateway: 201 Created {task_id, plane_issue_url}
    Gateway-->>UI: Response
    UI-->>Human: Task created, visible in board

    Redis-->>Runtime: Event received
    Runtime->>Postgres: Fetch task + agent config
    Runtime->>Runtime: Invoke LLM with task context
    Runtime->>Mattermost: Post status update in project channel
    Runtime->>Outline: Create research document
    Runtime->>Plane: Update issue status to "In Progress"
    Runtime->>Postgres: Write audit log entry
    Runtime->>Redis: PUBLISH task_events {type: task.started}
    Redis-->>CoreAPI: Forward to WebSocket
    CoreAPI-->>UI: WS push: task.started
    UI-->>Human: Task status updated in real-time
```

### 4.2 Inbound Webhook Flow (Tool Event to Agent Action)

```mermaid
sequenceDiagram
    participant Tool as Plane / Mattermost / Outline
    participant Gateway as Traefik
    participant CoreAPI as Core API
    participant Validator as Webhook Validator
    participant EventRouter as Event Router
    participant Redis
    participant Runtime as Agent Runtime
    participant Postgres

    Tool->>Gateway: POST /api/v1/webhooks/{tool}/{secret}
    Gateway->>CoreAPI: Route to webhook handler
    CoreAPI->>Validator: Verify HMAC signature
    Validator-->>CoreAPI: Valid / Invalid
    alt Invalid signature
        CoreAPI-->>Gateway: 401 Unauthorized
    end
    CoreAPI->>CoreAPI: Parse raw webhook payload
    CoreAPI->>EventRouter: Normalize to AgentCompany event schema
    EventRouter->>Postgres: Store event in events table
    EventRouter->>Redis: PUBLISH normalized event
    CoreAPI-->>Gateway: 200 OK
    Gateway-->>Tool: 200 OK

    Redis-->>Runtime: Receive normalized event
    Runtime->>Runtime: Match event to active agent subscriptions
    Runtime->>Postgres: Log agent action start
    Runtime->>Runtime: Execute agent decision logic (LLM call)
    Runtime->>Tool: Take action via adapter (API call)
    Runtime->>Postgres: Log agent action completion + token usage
```

### 4.3 Agent Search Flow

```mermaid
sequenceDiagram
    participant Runtime as Agent Runtime
    participant CoreAPI as Core API
    participant Meilisearch
    participant Plane
    participant Outline
    participant Mattermost

    Runtime->>CoreAPI: GET /api/v1/search?q=competitor+analysis&scope=all
    CoreAPI->>Meilisearch: Multi-index search (tasks, documents, messages)
    Meilisearch-->>CoreAPI: Ranked results across all indexes
    CoreAPI->>CoreAPI: Re-rank and deduplicate
    CoreAPI-->>Runtime: SearchResults {hits: [...], total, facets}

    Note over Runtime: Agent uses results as context for LLM prompt
    Runtime->>Runtime: LLM generates response with citations
    Runtime->>Outline: Create/update document with findings
    Runtime->>Plane: Create follow-up tasks if needed
    Runtime->>Mattermost: Post summary to channel
```

---

## 5. Network Topology

### 5.1 Docker Compose Network Design (MVP)

```mermaid
graph LR
    subgraph public_net["public network (bridge)"]
        Traefik["Traefik\n:80/:443"]
    end

    subgraph internal_net["internal network (bridge, no external access)"]
        CoreAPI["Core API\n:8000"]
        AgentRuntime["Agent Runtime\n:8010"]
        Keycloak["Keycloak\n:8080"]
        Plane["Plane\n:3001"]
        Outline["Outline\n:3002"]
        Mattermost["Mattermost\n:8065"]
        Meilisearch["Meilisearch\n:7700"]
        Postgres["PostgreSQL\n:5432"]
        Redis["Redis\n:6379"]
        MinIO["MinIO\n:9000"]
    end

    subgraph observability_net["observability network (bridge)"]
        Prometheus["Prometheus\n:9090"]
        Grafana["Grafana\n:3003"]
        Loki["Loki\n:3100"]
    end

    Traefik -->|proxy| CoreAPI
    Traefik -->|proxy| Keycloak
    Traefik -->|proxy| Plane
    Traefik -->|proxy| Outline
    Traefik -->|proxy| Mattermost
    Traefik -->|proxy| Grafana

    CoreAPI -->|internal| Postgres
    CoreAPI -->|internal| Redis
    CoreAPI -->|internal| Meilisearch
    CoreAPI -->|internal| Keycloak

    AgentRuntime -->|internal| Postgres
    AgentRuntime -->|internal| Redis
    AgentRuntime -->|internal| Plane
    AgentRuntime -->|internal| Outline
    AgentRuntime -->|internal| Mattermost
    AgentRuntime -->|internal| Meilisearch

    CoreAPI -->|metrics| Prometheus
    AgentRuntime -->|metrics| Prometheus
    Prometheus --> Grafana
    Loki --> Grafana
```

### 5.2 Service Communication Matrix

| From \ To | Core API | Agent Runtime | Keycloak | Plane | Outline | Mattermost | Meilisearch | Postgres | Redis |
|---|---|---|---|---|---|---|---|---|---|
| **Traefik** | PROXY | - | PROXY | PROXY | PROXY | PROXY | - | - | - |
| **Core API** | - | HTTP (internal) | HTTP JWKS | HTTP API | HTTP API | HTTP API | HTTP API | TCP 5432 | TCP 6379 |
| **Agent Runtime** | HTTP (internal) | - | - | HTTP API | HTTP API | HTTP API | HTTP API | TCP 5432 | TCP 6379 |
| **Web UI** | HTTP (via gateway) | - | OIDC | - | - | - | - | - | - |

### 5.3 Port Allocation

| Service | External (via Traefik) | Internal |
|---|---|---|
| Web UI | 443 (path /) | 3000 |
| Core API | 443 (path /api) | 8000 |
| Agent Runtime | Not exposed | 8010 |
| Keycloak | 443 (path /auth) | 8080 |
| Plane | 443 (path /plane) | 3001 |
| Outline | 443 (path /docs) | 3002 |
| Mattermost | 443 (path /chat) | 8065 |
| Grafana | 443 (path /metrics) | 3003 |
| PostgreSQL | Not exposed | 5432 |
| Redis | Not exposed | 6379 |
| Meilisearch | Not exposed | 7700 |
| MinIO API | Not exposed | 9000 |
| MinIO Console | 443 (path /storage, admin only) | 9001 |

---

## 6. Deployment Architecture

### 6.1 MVP — Docker Compose

Single-host deployment suitable for development and small teams.

```
docker-compose.yml
  ├── traefik
  ├── postgres (single instance, multiple databases)
  ├── redis
  ├── minio
  ├── keycloak
  ├── plane
  ├── outline
  ├── mattermost
  ├── meilisearch
  ├── agentcompany-core-api
  ├── agentcompany-agent-runtime
  ├── agentcompany-web-ui
  ├── prometheus
  ├── grafana
  └── loki
```

Resource requirements for MVP (single host): 8 CPU cores, 16 GB RAM, 100 GB SSD.

### 6.2 Production — Kubernetes (Future State)

```mermaid
graph TB
    subgraph k8s["Kubernetes Cluster"]
        subgraph ingress_ns["ingress namespace"]
            IngressController["Traefik IngressController"]
            CertManager["cert-manager\n(Let's Encrypt)"]
        end

        subgraph platform_ns["platform namespace"]
            CoreAPI_Deploy["Core API\nDeployment (2+ replicas)"]
            AgentRuntime_Deploy["Agent Runtime\nDeployment (2+ replicas)\nHPA on queue depth"]
            WebUI_Deploy["Web UI\nDeployment (2+ replicas)"]
        end

        subgraph tools_ns["tools namespace"]
            Plane_SS["Plane StatefulSet"]
            Outline_SS["Outline StatefulSet"]
            Mattermost_SS["Mattermost StatefulSet"]
        end

        subgraph data_ns["data namespace"]
            PG_Operator["CloudNativePG Operator\nPostgreSQL HA"]
            Redis_Operator["Redis Operator\n(Sentinel mode)"]
            Meilisearch_SS["Meilisearch StatefulSet"]
        end

        subgraph auth_ns["auth namespace"]
            Keycloak_SS["Keycloak StatefulSet\n(HA mode)"]
        end
    end

    IngressController --> CoreAPI_Deploy
    IngressController --> WebUI_Deploy
    IngressController --> Keycloak_SS
    CoreAPI_Deploy --> PG_Operator
    CoreAPI_Deploy --> Redis_Operator
    AgentRuntime_Deploy --> Redis_Operator
    AgentRuntime_Deploy --> PG_Operator
```

---

## 7. Technology Decisions and Rationale

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| API framework | FastAPI (Python) | Django REST, Express.js, Go Fiber | Async-native, excellent OpenAPI generation, strong AI/ML ecosystem for agent code |
| Message queue | Redis Streams + Pub/Sub | Kafka, RabbitMQ, NATS | Sufficient throughput for MVP, already required for caching, single dependency |
| Auth | Keycloak | Auth0, Okta, custom JWT | Self-hosted, full OIDC/SAML support, enterprise-grade RBAC, no SaaS lock-in |
| Search | Meilisearch | Elasticsearch, OpenSearch, Typesense | Lowest operational overhead, sub-millisecond latency, excellent relevance out-of-box |
| Chat | Mattermost | Slack, Discord, Matrix | Open-source, self-hosted, webhooks/bot API, GDPR-friendly |
| Project mgmt | Plane | Linear, GitLab issues, Jira | Open-source, Jira-compatible UX, active development, REST API |
| Wiki | Outline | Confluence, Notion, BookStack | Clean UX, solid REST API, Markdown-native, S3 attachment support |
| Container orchestration | Docker Compose (MVP) | Nomad, Podman Compose | Industry standard, developer familiarity, smooth path to Kubernetes |
| Object storage | MinIO | AWS S3, Backblaze B2 | S3-compatible API, self-hosted, no egress costs, same SDK as cloud S3 |
| Observability | Prometheus + Grafana + Loki | Datadog, New Relic, ELK | Open-source PLG stack, zero licensing cost, Kubernetes-native, excellent community |

---

## 8. Scalability Considerations

### 8.1 Bottlenecks and Mitigations

| Bottleneck | Risk | Mitigation |
|---|---|---|
| LLM API rate limits | Agent tasks blocked | Per-provider rate limiter in Agent Runtime; queue backpressure |
| PostgreSQL single instance | Write contention | PgBouncer connection pooling; read replicas for reporting queries |
| Redis single node | Cache/queue unavailability | Redis Sentinel in production; graceful degradation |
| Meilisearch single node | Search unavailability | Search is non-critical path; Core API returns empty results on failure |
| Agent task fan-out | Redis Streams overload | Partition streams by company_id; horizontal scale of Agent Runtime |

### 8.2 Performance Targets (MVP)

| Operation | P50 Target | P99 Target |
|---|---|---|
| REST API response (non-LLM) | < 50ms | < 200ms |
| Task creation (with Plane sync) | < 500ms | < 2000ms |
| Search query | < 100ms | < 500ms |
| Agent action execution (LLM) | < 5s | < 30s |
| Webhook ingestion | < 100ms | < 500ms |

---

## 9. Open Questions and Future Decisions

| Question | Owner | Target Resolution |
|---|---|---|
| Multi-tenant isolation: shared Postgres schemas vs separate databases per company | Platform team | Before beta |
| LLM provider abstraction: single provider vs. per-agent provider selection | Agent team | MVP |
| Agent-to-agent communication model: direct calls vs. event-driven only | Architecture | Before beta |
| Human-in-the-loop approval: synchronous gate vs. async approval workflow | Product | MVP |
| Data residency requirements for EU customers | Legal/Infra | Before GA |
