# Architecture Handoff — AgentCompany Platform

**Date**: 2026-04-18
**Prepared by**: System Architect
**Status**: Complete — ready for engineering handoff

---

## Context: Existing Architecture Work

Before reading this document, be aware that parallel work has already produced the following documents which are complementary to (not duplicated by) this architecture handoff:

- `docs/architecture/agent-runtime.md` — Internal agent process model, concurrency, sandboxing
- `docs/architecture/agent-framework.md` — Agent decision loop, state machine, lifecycle
- `docs/architecture/agent-tools.md` — Tool definition schema, tool registry, built-in tools
- `docs/architecture/llm-adapters.md` — LLM provider abstraction (OpenAI, Anthropic, Ollama)
- `docs/architecture/infrastructure.md` — Docker Compose network diagram, port/volume tables
- `docs/handoffs/infra-handoff.md` — Infrastructure already built: docker-compose.yml, Traefik config, init scripts, setup.sh

This architecture handoff covers the **platform-level** concerns: the Core API contract, the PostgreSQL data model, the tool integration adapter layer (Plane/Outline/Mattermost/Meilisearch), security design, and error handling. These layers are distinct from and depend on the agent runtime internals documented in the files above.

---

## What Was Delivered

This handoff covers the complete system architecture for the AgentCompany platform. Six authoritative design documents have been written and are ready for engineering team consumption.

---

## Document Index

| Document | Path | Purpose |
|---|---|---|
| System Overview | `docs/architecture/system-overview.md` | High-level architecture, component inventory, data flows, network topology, deployment approach |
| API Design | `docs/architecture/api-design.md` | Complete REST API specification with request/response examples, auth scheme, rate limiting, pagination |
| Data Model | `docs/architecture/data-model.md` | PostgreSQL schema, ER diagrams, migration strategy, retention policy |
| Integration Layer | `docs/architecture/integration-layer.md` | Adapter pattern design, all four adapter implementations, event routing, webhook normalization |
| Security Design | `docs/architecture/security.md` | Auth flows, RBAC, agent credential management, secrets, network security, audit logging |
| Error Handling | `docs/architecture/error-handling.md` | Error taxonomy, retry strategies, circuit breaker, dead letter queue, monitoring/alerting |

---

## Architecture Decisions Summary

The following decisions were made during architecture design. Each is documented with rationale in the relevant document. Engineering should not reverse these without a recorded architecture review.

### Technology Stack (locked for MVP)

| Layer | Choice | Primary Rationale |
|---|---|---|
| API framework | FastAPI (Python) | Async-native; OpenAPI generation; LLM/AI ecosystem |
| Message queue | Redis Streams + Pub/Sub | Sufficient throughput; single dependency; already needed for caching |
| Auth | Keycloak | Self-hosted OIDC/SAML; enterprise RBAC; no SaaS lock-in |
| Search | Meilisearch | Lowest ops overhead; excellent relevance defaults |
| Reverse proxy | Traefik | Dynamic service discovery; automatic Let's Encrypt |
| Primary store | PostgreSQL 16 | ACID; RLS for tenant isolation; mature tooling |
| Container | Docker Compose (MVP) → Kubernetes | Progressive path; developer-friendly start |

### Key Architectural Patterns

1. **Adapter pattern for tool integrations** — `BaseAdapter` abstract class isolates all tool-specific logic. Adding GitHub, Jira, or Slack requires only a new adapter class, zero core changes.

2. **Event-driven agent execution** — Agents do not call the Core API directly to find work. They subscribe to Redis Pub/Sub channels and react to normalized events. This decouples agent execution from API availability.

3. **ULID primary keys** — All entities use `{prefix}_{ulid}` format (e.g., `tsk_01HX...`). ULIDs are sortable by creation time, URL-safe, and collision-resistant without a central sequence.

4. **Soft deletes everywhere** — No row is ever hard-deleted in the MVP. `deleted_at IS NULL` is filtered at the query layer. Hard deletes run as a scheduled job after the 30-day retention window.

5. **Secrets never in the database** — `adapter_configs.config` stores only secret references (`secret://vault/path`). The raw secret never touches PostgreSQL, logs, or API responses.

6. **Tenant isolation at two layers** — (1) Application layer: every query filters on `org_id` from the JWT. (2) Database layer: Postgres Row-Level Security enforces the same constraint. Both must be bypassed for a cross-tenant leak.

---

## Engineering Priorities for Sprint 1

Based on the architecture, the recommended build order is:

1. **Infrastructure** — Docker Compose file with all services, Traefik routing, Keycloak realm configuration.
2. **Core API skeleton** — FastAPI app, Alembic migrations for `orgs`, `users`, `companies`, JWT middleware.
3. **Adapter registry** — `BaseAdapter`, `AdapterRegistry`, `PlaneAdapter` (priority: needed for task sync).
4. **Event bus** — Redis publish/subscribe wiring between Core API (publish) and Agent Runtime (subscribe).
5. **Agent Runtime skeleton** — FastAPI app, event consumer, LLM client abstraction.
6. **Task flow end-to-end** — Human creates task via API → task persisted → Plane issue created → agent picks up → executes → status updated.

Authentication and audit logging should be wired in during steps 2-3, not deferred.

---

## Open Questions Requiring Product/Engineering Decisions

The following questions were identified during architecture design. They are documented in `system-overview.md` but require decisions before beta:

1. **Multi-tenant database isolation** — Shared Postgres schema with RLS vs. separate databases per company. RLS is implemented in the design; separate databases offer stronger isolation but significantly higher ops cost. Decision needed before onboarding external customers.

2. **LLM provider per agent vs. per org** — The data model supports per-agent `llm_config`. The question is whether the UI exposes per-agent LLM selection or enforces a single provider per org for billing simplicity.

3. **Human-in-the-loop approval UI** — The architecture has an approval gate based on Mattermost interactive buttons. An alternative (web UI modal) is architecturally simpler. Mattermost buttons have a 3-second response time requirement that may be difficult to meet in the first sprint.

4. **Agent-to-agent communication** — The current design is event-driven only (agents communicate by publishing events). Direct agent-to-agent RPC calls are not designed. If the product requires synchronous agent delegation, this needs an architecture addition.

---

## What Is Not In Scope (Future State)

- Kubernetes Helm charts — mentioned in `system-overview.md` as future state, not designed
- Multi-region deployment — data residency constraints not addressed in MVP
- LLM fine-tuning or RLHF — outside scope; only inference is addressed
- Third-party tool billing/metering — token cost tracking is in the data model but billing integration is not designed
- Agent-to-agent communication protocol — event-driven pattern is defined; direct RPC is deferred

---

## Files Produced

All files are in `/home/ubuntu/topics/agentcompany/docs/`:

```
docs/
├── architecture/
│   ├── system-overview.md        (system topology, data flows, component inventory)
│   ├── api-design.md             (complete REST API specification)
│   ├── data-model.md             (PostgreSQL schema, ER diagrams, migrations)
│   ├── integration-layer.md      (adapter pattern + all four adapter implementations)
│   ├── security.md               (auth, RBAC, secrets, network, audit)
│   └── error-handling.md         (error taxonomy, retry, circuit breaker, DLQ, observability)
└── handoffs/
    └── architecture-handoff.md   (this document)
```

---

## Review Checklist

Before engineering begins implementation, the following reviews are recommended:

- [ ] Security review of agent credential management approach (section 4, `security.md`)
- [ ] DBA review of PostgreSQL schema, especially RLS policies and partition strategy (`data-model.md`)
- [ ] Product review of human approval gate flow (`security.md` section 3.3)
- [ ] Engineering lead review of Docker Compose resource requirements (`system-overview.md` section 6.1)
- [ ] Legal/compliance review of audit log retention policy (`data-model.md` section 10)
