# AgentCompany — Product Handoff

**Handoff Type:** Product Definition to Engineering  
**Date:** 2026-04-18  
**Status:** Ready for Engineering Review  
**Author:** Product Architecture

---

## Summary

This handoff delivers the complete product definition for AgentCompany: an open-source platform for running AI-powered organizations where agents and humans collaborate through shared tools, org structures, and workflows.

All five product documents are complete and ready for engineering design. This document summarizes what was produced, calls out the highest-priority engineering decisions that need to be made immediately, and lists the open questions that remain unresolved.

---

## Deliverables Produced

| Document | Path | Purpose |
|---|---|---|
| Vision | `docs/product/vision.md` | Mission, principles, target users, competitive positioning |
| User Stories | `docs/product/user-stories.md` | 20 user stories with acceptance criteria and priority |
| Interaction Flows | `docs/product/interaction-flows.md` | 5 detailed end-to-end flows with Mermaid diagrams |
| Org Structure | `docs/product/org-structure.md` | Role definitions, agent behavior config schema, hierarchy rules |
| UI Wireframes | `docs/product/ui-wireframes.md` | Detailed wireframes for 5 primary screens |

---

## What Engineering Needs to Build (Priority Order)

### P0 — MVP Blockers (must ship to have a usable product)

**1. Agent Runtime**  
The core engine that manages agent lifecycle: instantiation, event-triggered wake-up, always-on heartbeat, tool execution, and suspension. This is the hardest and most important piece.

Key decisions needed:
- Agent orchestration framework underneath (CrewAI, AutoGen, LangGraph, or custom)
- How agent state persists between triggered activations (must not lose in-flight context)
- How concurrent agents are isolated (one agent's LLM call must not block another)
- Token counting: real-time, per-call, with accurate model pricing tables

**2. Adapter Layer / Integration Service**  
Abstraction layer that normalizes tool APIs (Mattermost, Plane, Outline, Gitea) into a single internal interface that agents program against.

Key decisions needed:
- Interface contract for each adapter category (chat, board, docs, code)
- How adapters handle authentication (per-tool credentials stored securely)
- Event subscription model (how tools notify AgentCompany of new events — webhooks vs. polling)
- What the "local dev" stack looks like for contributors who do not have all tools running

**3. Approval Queue**  
The mechanism by which agent-generated artifacts wait for human review before taking effect. This is critical for trust.

Key decisions needed:
- Where approval state lives (AgentCompany database, not in the downstream tool)
- How artifacts are presented for review (inline diff, PR link, doc preview)
- What happens to the agent while it waits (does it hold state? Is the task paused?)
- Timeout policy: what happens if a human never approves (auto-escalate, auto-expire)

**4. Event Bus**  
The internal event system that routes tool events to agent triggers.

Key decisions needed:
- Message queue technology (Redis Streams, NATS, Kafka — choose based on scale target)
- Event schema standard (what fields every event must contain)
- Delivery guarantee (at-least-once is probably sufficient for MVP; exactly-once for budget events)

**5. Web UI — Dashboard and Org Chart**  
The two screens that define first impressions. Must be production-quality on day one.

Key decisions needed:
- Frontend framework (the README suggests this is a separate `web-ui` service; confirm tech stack)
- Real-time updates strategy (WebSocket or Server-Sent Events for agent status feed)
- Org chart rendering library (D3, React Flow, or similar)

### P1 — Required for v1.0

**6. Unified Search**  
Aggregates results from all connected tools and the AgentCompany database.

Key decisions needed:
- Search index technology (Elasticsearch, Typesense, Meilisearch)
- Index update latency target (60 seconds per the user stories)
- How chat history is indexed given volume

**7. Token Budget Enforcement**  
The system that tracks usage, fires alerts, and suspends agents.

Key decisions needed:
- Where token counts are accumulated (event bus message enrichment vs. post-call webhook)
- How budget suspension is communicated back to the agent mid-task
- Pricing table maintenance (models change pricing; need a maintainable source of truth)

**8. Audit Log**  
Append-only log of every agent action with full context.

Key decisions needed:
- Storage backend (time-series DB, append-only table in PostgreSQL, object storage)
- Retention and archival policy
- Export performance for large date ranges

**9. Agent Configuration UI**  
The Settings screen for configuring agent personality, heartbeat mode, approval policies, and tool access.

**10. Adapter Swap Workflow**  
The admin flow for changing which tool fulfills each integration category without breaking in-flight agent tasks.

### P2 — Post-v1.0

- Mobile-responsive layout
- SSO / SAML authentication
- Custom role creation UI
- Scheduled reports (weekly status digest)
- Agent delegation depth enforcement
- Bulk audit log export

---

## Architecture Decisions Required Before Engineering Starts

The following decisions block significant amounts of implementation work and need to be resolved in the architecture design phase:

### Decision 1: Agent Orchestration Framework

**Options:**
- **LangGraph** — stateful agent graphs, supports complex workflows, Python-only, active development
- **CrewAI** — simpler, role-based framing that maps naturally to AgentCompany's org model, Python
- **AutoGen** — Microsoft research project, multi-agent conversations, Python, more experimental
- **Custom** — maximum control, most implementation work, no external dependency

**Recommendation signal from product:** The org structure and role-based behavior model aligns very naturally with CrewAI's mental model. LangGraph's stateful graph approach may be more appropriate if complex multi-step agent workflows are expected. Custom gives the most control but delays shipping.

**Blocking:** Agent Runtime, entire agent execution path.

---

### Decision 2: Event System

**Options:**
- **Redis Streams** — simple, already likely in the stack for caching, limited routing
- **NATS JetStream** — lightweight, fast, good for microservices, less ecosystem tooling
- **Kafka** — robust at scale, heavy operational overhead for a small team
- **In-process event bus** (for monolith start) — simplest, limits horizontal scaling

**Recommendation signal from product:** Start with Redis Streams or NATS. The platform does not need Kafka-scale at launch, and operational simplicity is important for a self-hosted open-source project.

**Blocking:** Heartbeat system, agent triggers, approval queue notifications.

---

### Decision 3: Search Backend

**Options:**
- **Meilisearch** — fast, easy to self-host, good developer experience, limited advanced features
- **Typesense** — similar to Meilisearch, slightly different performance profile
- **Elasticsearch / OpenSearch** — full-featured, heavy, complex to operate
- **Delegate to tools** — each tool's native search is exposed; no unified index

**Recommendation signal from product:** The 60-second index latency requirement and the need for cross-tool search make "delegate to tools" impractical. Meilisearch or Typesense fits the self-hosted open-source positioning. Avoid Elasticsearch for MVP.

**Blocking:** Unified Search (Screen 4), any feature that depends on cross-tool discovery.

---

### Decision 4: Database Schema for Company/Role/Agent State

The AgentCompany database is the system of record for:
- Company configuration
- Org structure (roles, hierarchy)
- Agent configuration and state
- Approval queue
- Token usage and budgets
- Audit log

This needs a data model design before any of the P0 services are implemented. The architecture team should produce an entity-relationship diagram and schema draft as the first output of the engineering design phase.

---

## Open Questions for Product Clarification

The following questions arose during the product definition phase and require product decisions before the relevant features can be specified precisely:

**Q1: Multi-company support**  
Does a single AgentCompany installation support multiple companies (for SaaS future), or is it single-company (for self-hosted)? This affects database schema, auth model, and UI routing significantly.

*Recommended default:* Single-company for v1.0. Multi-tenancy is a v2 consideration.

---

**Q2: Agent-to-agent messaging**  
Can agents communicate directly with each other (e.g., a Developer agent asking the QA agent a question), or do all agent communications pass through the chat system as observable messages?

*Recommended default:* All inter-agent communication passes through the chat system. This preserves observability and the "single interface" principle, but adds latency.

---

**Q3: Approval timeout behavior**  
If a human does not review an approval queue item within a configurable period (e.g., 24 hours), what happens? Options: auto-reject, auto-approve, escalate to admin, leave pending indefinitely.

*Recommended default:* Escalate to admin and leave pending. Auto-approve is a security risk; auto-reject wastes agent work.

---

**Q4: Agent identity in external tools**  
When a Developer agent posts a comment in Plane or sends a message in Mattermost, does it use its own user account in those tools (one account per agent), or a shared service account?

*Recommended default:* One service account per agent in each tool. This preserves traceability in the tools themselves and aligns with the "agents are first-class org members" principle. Implementation complexity is higher.

---

**Q5: Real-time vs. near-real-time dashboard**  
The dashboard shows agent status and recent activity. How fresh does this need to be? WebSockets enable true real-time but add complexity. Server-Sent Events or polling every 30 seconds is simpler.

*Recommended default:* Server-Sent Events (SSE) for agent status updates (simple, unidirectional, HTTP-compatible). Full WebSocket upgrade is a v1.1 optimization.

---

**Q6: Model selection granularity**  
Can individual agents use different models (e.g., CFO uses claude-haiku for cost reports, CTO uses claude-sonnet for code review), or is there one model per company?

*Recommended default:* Per-agent model selection. This is a key cost-optimization lever that users will want from day one.

---

## Critical Design Constraints

These constraints are non-negotiable and must be respected in all engineering decisions:

1. **All agent actions are logged.** No agent can take an action without creating an audit log entry. This is enforced at the agent runtime layer, not by individual tool adapters.

2. **Adapters are swappable without agent code changes.** Agents program against the AgentCompany abstraction layer. If an adapter is swapped, the agents should not need reconfiguration.

3. **Token budgets are enforced before agent suspension.** Agents must receive a warning at the configurable threshold (default 80%) before being suspended at 100%. An agent that is suspended mid-task must gracefully transition any in-progress ticket to "Blocked."

4. **Approval policies are role-level defaults, overridable per-agent.** An engineering decision that bakes approval logic into agents (rather than the platform) would violate this constraint.

5. **The platform must be runnable with `docker compose up` on a developer laptop.** All default adapters (Mattermost, Plane, Outline, Gitea) must be included in the Compose file. External API dependencies (LLM provider) are the only thing requiring external credentials.

---

## Recommended Engineering Start Sequence

1. **Week 1–2:** Database schema design (entity-relationship model for company/role/agent/audit)
2. **Week 1–2:** Adapter interface contracts (define the abstract API for each integration category)
3. **Week 3–4:** Event bus implementation + agent trigger system (skeleton)
4. **Week 3–6:** Agent runtime (core loop, tool execution, token tracking, suspension)
5. **Week 5–8:** Adapter implementations (Mattermost, Plane, Outline, Gitea — one each)
6. **Week 5–8:** Web UI — Dashboard, Org Chart, Agent Detail (frontend team in parallel)
7. **Week 9–10:** Approval queue + notification system
8. **Week 11–12:** Unified search (Meilisearch integration)
9. **Week 13–14:** Admin settings UI (adapter configuration, budget management)
10. **Week 15–16:** End-to-end integration testing + Docker Compose packaging

---

## Files for Engineering to Consult First

In priority order:

1. `docs/product/org-structure.md` — Agent behavior configuration schema (section: "Agent Personality and Behavior Configuration Schema") defines the data contract that the agent runtime must implement
2. `docs/product/interaction-flows.md` — Flow 5 (Cross-Tool Workflow) is the integration test specification for the entire platform
3. `docs/product/user-stories.md` — US-06 (Approval Queue), US-11 (Ticket Pickup), US-17 (Budget Enforcement) are the three stories most likely to reveal architectural complexity early
4. `docs/product/ui-wireframes.md` — Agent Detail view and Decision Trace sub-view define the data model requirements for the audit log
5. `docs/product/vision.md` — Core Principles section is the tiebreaker for all engineering trade-off discussions

---

## Contact

For product clarifications on any item in this handoff, refer questions to the product architecture track. Engineering design documents should reference specific section numbers from the product docs when making decisions that trace back to product requirements.
