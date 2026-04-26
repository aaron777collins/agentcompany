# Architecture Documentation

This directory contains the authoritative architecture and design specifications for AgentCompany. Each document covers a specific subsystem in depth: data models, sequence diagrams, code contracts, and design rationale.

Read `system-overview.md` first — it contains the high-level architecture diagram, component inventory, and technology decision log that all other documents build on.

---

## Documents

| Document | Status | Description |
|----------|--------|-------------|
| [system-overview.md](system-overview.md) | Authoritative | High-level architecture diagram, component inventory, data flow sequences, network topology, deployment options, and technology decision log |
| [agent-framework.md](agent-framework.md) | Draft | Agent lifecycle state machine, heartbeat and trigger system, two-tier memory model, inter-agent communication patterns, and the four-phase decision loop |
| [agent-runtime.md](agent-runtime.md) | Draft | Python/FastAPI service structure, async concurrency model, agent process isolation, resource management, and observability hooks |
| [agent-tools.md](agent-tools.md) | Draft | Tool definition schema, built-in tools (ProjectManagementTool, DocumentationTool, ChatTool, SearchTool, CodeTool, AnalyticsTool), permission model, and execution sandbox |
| [llm-adapters.md](llm-adapters.md) | Draft | LLM adapter interface, provider implementations (Anthropic, OpenAI, Ollama, Custom), token counting, cost calculation, prompt template management, context window compaction, and streaming |
| [integration-layer.md](integration-layer.md) | Authoritative | Adapter architecture for Plane, Outline, Mattermost, and Meilisearch; webhook normalization; circuit breaker; capability declaration contract |
| [org-hierarchy-engine.md](org-hierarchy-engine.md) | Draft | Org hierarchy DAG representation, authority and delegation model, escalation paths, approval workflows, and agent spawning flow |
| [api-design.md](api-design.md) | Authoritative | REST API design principles, authentication/authorization scheme, resource endpoints, request/response envelope, pagination, idempotency, and WebSocket protocol |
| [data-model.md](data-model.md) | Authoritative | PostgreSQL schema, ER diagram, ULID key conventions, multi-tenancy via `org_id`, soft deletes, optimistic concurrency, and audit log immutability |
| [security.md](security.md) | Authoritative | Threat model, human and agent authentication flows, RBAC permission hierarchy, agent credential management (Vault / Docker Secrets), prompt injection defenses, audit logging, and production security checklist |
| [infrastructure.md](infrastructure.md) | Authoritative | Docker Compose network design, port allocation, volume mapping, service dependency graph, resource requirements per service, GPU setup for Ollama, Plane integration steps, and scaling guidance |
| [error-handling.md](error-handling.md) | Authoritative | Error taxonomy (infrastructure, tool, agent, auth, validation), retry policies with exponential backoff, circuit breaker configuration, graceful degradation strategy, and observability integration |

---

## Reading Order

**To understand the system end-to-end**, read in this order:

1. `system-overview.md` — what is the system and why does it exist
2. `infrastructure.md` — how the services are deployed and connected
3. `data-model.md` — what data is stored and how it is structured
4. `api-design.md` — how clients interact with the platform
5. `security.md` — how authentication, authorization, and audit work
6. `agent-framework.md` — how agents work internally
7. `llm-adapters.md` — how agents call LLMs
8. `agent-tools.md` — what agents can do in the world
9. `integration-layer.md` — how the platform connects to external tools
10. `org-hierarchy-engine.md` — how company structure and escalation work
11. `agent-runtime.md` — service-level implementation details
12. `error-handling.md` — failure modes and recovery

---

## Architecture Decisions and Status

| Decision | Status | Document |
|----------|--------|----------|
| FastAPI as primary API framework | Decided | system-overview.md §7 |
| Redis Streams + Pub/Sub as message queue (over Kafka/NATS) | Decided | system-overview.md §7 |
| Keycloak for identity (over Auth0/Okta) | Decided | system-overview.md §7 |
| Meilisearch for search (over Elasticsearch) | Decided | system-overview.md §7 |
| pgvector for agent memory embeddings (over dedicated vector DB) | Decided | agent-framework.md |
| Custom LLM adapter interface (over LiteLLM) | Decided | llm-adapters.md |
| No direct agent-to-agent RPC — tool-mediated only | Decided | agent-framework.md |
| Async coroutines over subprocesses for agent isolation | Decided | agent-framework.md |
| Event sourcing for agent state transitions | Decided | agent-framework.md |
| Multi-tenant isolation strategy (shared schema vs. per-tenant DB) | Open | system-overview.md §9 |
| Agent-to-agent communication model (current: tool-mediated only) | Open | system-overview.md §9 |
