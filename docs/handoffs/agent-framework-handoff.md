# Agent Framework Handoff

**Date**: 2026-04-18  
**Author**: AI/Agent Framework Architect  
**Status**: Architecture complete, implementation not started  
**Recipient**: Engineering team beginning implementation

---

## What Was Designed

Five architecture documents covering the complete agent framework for AgentCompany. These are design specifications — no implementation code exists yet.

| Document | Path | Purpose |
|---|---|---|
| Agent Framework | `docs/architecture/agent-framework.md` | Agent lifecycle, state machine, heartbeat system, memory model, inter-agent communication, decision loop |
| Agent Runtime | `docs/architecture/agent-runtime.md` | Python/FastAPI service, process model, concurrency, resource management, sandbox, observability |
| LLM Adapters | `docs/architecture/llm-adapters.md` | Adapter interface, Anthropic/OpenAI/Ollama/Custom implementations, cost tracking, prompt templates, context management, streaming |
| Agent Tools | `docs/architecture/agent-tools.md` | Tool schema, six built-in tools, permission model, code execution sandbox |
| Org Hierarchy Engine | `docs/architecture/org-hierarchy-engine.md` | Org data model, authority/delegation, escalation, approval workflows, agent spawning |

---

## Architecture Summary

### What Was Decided

**Agent Process Model**: Async coroutines, not subprocesses or containers per agent. Agents are I/O-bound (waiting on LLM APIs and tool calls). A single Python process with asyncio handles dozens of concurrent agents efficiently. The code sandbox (for `CodeTool`) is the only place where subprocesses are used, and that is explicitly for isolation.

**Communication via Shared Tools**: Agents do not call each other directly. All inter-agent communication flows through the same tools humans use: Plane tasks, Mattermost messages, Outline documents. This keeps all activity visible to humans without special tooling.

**Event-Driven Triggers**: The heartbeat system supports four modes — always-on (periodic tick), event-triggered (webhook-based), scheduled (cron), and manual. Redis Streams provide durable delivery with consumer group semantics.

**Two-Tier Memory**: Short-term context is the LLM conversation window (held in memory during a run). Long-term memory is pgvector on PostgreSQL (embedded summaries and facts, retrieved by similarity search). No separate vector database is required.

**Thin Adapter Interface**: The `LLMAdapter` abstract base class is small and concrete. Provider differences (Anthropic tool_use vs OpenAI function_calling) are handled inside each adapter, not exposed to the decision loop.

**Cost as a First-Class Concern**: Every `LLMResponse` includes `cost_usd`. Budget checks happen before each LLM call. Budget enforcement pauses agents mid-run. Daily and monthly budgets are tracked per agent and per company.

**Escalation and Approval as Separate Concepts**: Escalations are for uncertainty (agent cannot decide). Approvals are for policy (agent needs permission for a specific action). Both are first-class records in the DB, surfaced in the web UI, and notify humans via Mattermost.

---

## Implementation Order

These components have dependencies. Build them in this sequence.

### Phase 1: Foundation (Weeks 1–3)

Nothing else works without the database schema and the basic agent lifecycle.

1. **Database schema** — Create all tables: `agents`, `agent_runs`, `org_nodes`, `reporting_relationships`, `token_usage`, `agent_transitions`, `escalations`, `approval_requests`, `prompt_templates`, `agent_entities`
2. **Agent repository** — CRUD for the `agents` table using asyncpg
3. **Lifecycle manager** — State machine transitions with validation
4. **Agent config models** — `AgentConfig`, `AgentPersonality`, `AgentCapabilities`, `HeartbeatConfig`

**Done when**: You can create an agent record, configure it, and transition it through states. No LLM calls yet.

### Phase 2: LLM Layer (Weeks 2–4, parallel with Phase 1)

2. **AnthropicAdapter** — The primary adapter. Implement `complete()` first, then `stream()`.
3. **Token counting and cost calculation** — Pricing tables and cost calculation in each adapter.
4. **Context window manager** — Compaction strategy (needed before any long runs).
5. **LLM adapter registry** — Registration and resolution by adapter_id.
6. **Prompt template manager** — Jinja2 rendering with file-based defaults.

**Done when**: You can call `adapter.complete(messages, system, tools)` and get back a typed `LLMResponse` with cost.

### Phase 3: Tool Layer (Weeks 3–5)

3. **Tool base classes and registry** — `BaseTool`, `ToolRegistry`, `ToolSandbox`
4. **SearchTool** — Meilisearch integration. Build this first because it's read-only.
5. **ProjectManagementTool** — Plane integration. The most-used tool.
6. **ChatTool** — Mattermost integration. Required for agent communication.
7. **DocumentationTool** — Outline integration.
8. **AnalyticsTool** — Internal DB queries, no external client needed.
9. **CodeTool + DockerCodeSandbox** — Build last; requires Docker-in-Docker setup.

**Done when**: You can call each tool directly (without an agent) and get back a string result.

### Phase 4: Decision Loop (Week 4–5)

4. **AgentDecisionLoop** — The `observe → think → act → reflect` cycle.
5. **AgentContext** — Context window management during a run.
6. **Memory service** — pgvector store and entity facts store.

**Done when**: You can run a full agent loop end-to-end: create agent, give it a trigger, it reads a task, calls a tool, and completes.

### Phase 5: Heartbeat and Runtime (Week 5–6)

5. **HeartbeatService** — APScheduler for always-on and scheduled modes.
6. **TriggerConsumer** — Redis Streams consumer with semaphore-based concurrency.
7. **TaskDispatcher** — Distributed lock, context building, loop execution.
8. **BudgetService** — Redis-based counters with DB flush.
9. **Webhook receivers** — Plane, Mattermost, Outline webhook handlers.
10. **FastAPI application** — Wire everything together.

**Done when**: The full service runs. Agents wake on events and complete tasks.

### Phase 6: Org Hierarchy (Week 6–7)

6. **OrgHierarchyService** — DB queries for nodes, relationships, authority paths.
7. **EscalationService** — Create and resolve escalations with routing logic.
8. **ApprovalService** — Request/resolve/expire approvals with policy enforcement.
9. **AgentSpawnerService** — End-to-end agent creation from a SpawnRequest.

**Done when**: Adding a new role to the org automatically creates and activates an agent with correct permissions, manager relationship, and event filters.

---

## Critical Implementation Notes

### Things That Will Break If You Cut Corners

**Distributed lock on agent runs** (`agent_run_lock:{agent_id}` in Redis): If you skip this, two triggers can start the same agent simultaneously, causing duplicate tool calls, conflicting state, and doubled token costs. This is non-optional.

**Budget check before every LLM call**: The check must happen inside the decision loop, before each call — not once at the start of a run. A run that starts under budget can exceed it mid-run if it runs many steps. The check must be inside the loop.

**Tool permission check in the sandbox, not in the LLM**: The LLM can hallucinate that it has permission to use a tool. The sandbox must check `agent.capabilities.allowed_tools` independently, before every call. Never trust the LLM's tool selection as a permission decision.

**Context window management before every LLM call**: If you forget to compact, a long run will hit the provider's context limit and fail with a 400 error mid-task. Call `context_manager.maybe_compact()` before every `adapter.complete()` call.

**State transition validation**: The `VALID_TRANSITIONS` set in `lifecycle.py` must be enforced. Without it, bugs that cause an agent to call `transition(CREATED, RUNNING)` will corrupt state and cause unpredictable behavior.

### Where the Architecture is Intentionally Incomplete

**Mattermost, Plane, and Outline clients**: The architecture assumes async Python clients for these services. The actual client implementations are not designed here. You will need to build or adapt these. The tool implementations show the expected client interface (method names and return shapes). Use `httpx.AsyncClient` as the base.

**Authentication and authorization for the management API**: The `GET /api/v1/agents` endpoints are shown without auth. Before any user-facing deployment, add JWT authentication at the gateway layer. Every management API call must validate that the caller belongs to the correct company.

**Meilisearch indexing**: `SearchTool` queries Meilisearch indexes (`plane_issues`, `outline_documents`, `mattermost_posts`). These indexes must be populated by sync jobs or webhooks. That sync pipeline is not designed here.

**Web UI streaming interface**: `agent-runtime.md` shows the SSE endpoint and how stream events are written to Redis Streams. The web UI component that consumes these events and renders live agent activity is not designed here.

**Email notifications for approvals/escalations**: The architecture mentions Mattermost DMs for approvals. An email notification path for humans who are not active in Mattermost is not designed.

---

## Open Questions

These questions were not resolved in the architecture and should be decided before implementation of the affected components.

1. **Mattermost vs. Slack**: The design uses Mattermost. If the team wants to support Slack as an alternative, the `ChatTool` needs a strategy for multiple chat backends. Decide before building `ChatTool`.

2. **pgvector vs. dedicated vector DB**: The architecture uses pgvector. If the team expects high memory volume (>1M entries per agent), evaluate Qdrant or Weaviate. The `AgentMemoryService` interface is the only place that changes.

3. **Code workspace storage**: `CodeTool` uses a local directory per workspace. For multi-instance deployment, this must be a shared filesystem (NFS, EFS) or an object store (S3) with a local mount. Decide before building `CodeTool`.

4. **Ollama model selection**: The `OllamaAdapter` defaults to `llama3.2`. The team must decide which local models to support and how model selection is configured per agent.

5. **Token budget defaults**: The design sets `token_budget_daily = 100,000` and `token_budget_monthly = 2,000,000` per agent. These should be reviewed against actual cost projections for typical agent workflows before going live.

6. **Multi-company isolation**: The architecture stores all agents and orgs in shared tables with a `company_id` column. Row-level security (RLS) in PostgreSQL would provide database-level isolation for multi-tenant deployments. This is not implemented in the schema as designed.

7. **Agent identity in Plane**: Agents act as Plane users. The spawner creates a Plane user for each agent. Confirm that Plane's user model supports this at the expected scale (many agents per company) and that Plane API credentials allow programmatic user creation.

---

## Files Created

```
docs/architecture/agent-framework.md      — Agent lifecycle, state machine, heartbeat, memory, communication, decision loop
docs/architecture/agent-runtime.md        — Runtime service, process model, concurrency, sandbox, observability
docs/architecture/llm-adapters.md         — Adapter interface, Anthropic/OpenAI/Ollama/Custom, cost, prompts, context, streaming
docs/architecture/agent-tools.md          — Tool schema, six built-in tools, permissions, code sandbox
docs/architecture/org-hierarchy-engine.md — Org model, authority, escalation, approval workflows, agent spawning
docs/handoffs/agent-framework-handoff.md  — This file
```

---

## Recommended First PR

**Target**: A minimal end-to-end agent that can be triggered manually, calls `ProjectManagementTool` to read a task, and posts a Mattermost message summarizing what it found.

**Scope**:
- Database schema (agents, agent_runs, agent_transitions tables only)
- AgentConfig model, AgentRepository
- AnthropicAdapter (complete only, no streaming)
- ProjectManagementTool (read_issue, list_issues actions only)
- ChatTool (send_message action only)
- AgentDecisionLoop (no memory, no compaction — add later)
- ToolSandbox (permissions only — no code sandbox)
- Manual trigger endpoint: `POST /api/v1/agents/{id}/trigger`
- FastAPI app with hardcoded config (no Redis, no heartbeat)

This gives the team a working foundation to build on and validate all the core interfaces before adding complexity.
