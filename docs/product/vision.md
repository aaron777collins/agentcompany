# AgentCompany — Product Vision

**Version:** 1.0  
**Date:** 2026-04-18  
**Status:** Active

---

## Mission

AgentCompany exists to make AI-augmented organizations accessible and practical. We give any team — from a solo developer to a growing startup — the ability to create a structured virtual company where AI agents and humans share the same tools, the same org chart, and the same workflows.

We are not building a chatbot interface bolted onto project management software. We are building the operating system for a new kind of organization: one where the boundary between human and agent collaborator is a policy decision, not a technical barrier.

---

## Vision Statement

In five years, the most productive teams in the world will treat AI agents as first-class organizational members — not as background automations, but as colleagues with roles, responsibilities, and operating constraints. AgentCompany is the infrastructure that makes that possible today, using tools your team already knows how to use.

---

## The Core Problem We Solve

Running agents in production is still largely a research exercise. Existing tools offer:

- Chatbot UIs that cannot integrate with real project tools
- Automation platforms (Zapier, n8n) that lack genuine intelligence
- Agent frameworks (AutoGen, CrewAI) with no usable frontend
- Internal tools built by well-funded companies that are closed-source and expensive

None of these answer the real question: **how do you actually run a company with agents?**

That means: who assigns the agents their tasks? How do you see what they did? How do you review their output before it goes live? How do you know when they are stuck? How much did they cost this week?

AgentCompany answers all of these questions with a coherent, opinionated product.

---

## Core Principles

### 1. Agent-First, Human-Friendly

The platform is designed so that agents are fully capable participants — they can read tickets, write documentation, send messages in chat, and update the kanban board. Humans interact through the same interface. There is no "agent mode" and "human mode." There is one product.

This means agents are not second-class. Any feature available to a human user must be available to an agent via the API. Parity is non-negotiable.

### 2. Open-Source and Self-Hostable

Every line of AgentCompany code is MIT-licensed. The platform runs entirely on self-hosted open-source tools. Users own their data. There is no vendor lock-in and no call-home telemetry unless explicitly opted into.

The default stack (Gitea, Plane, Mattermost, Outline) is chosen specifically because each tool is mature, self-hostable, and has a strong community. Users who already run these tools can connect AgentCompany to their existing instances.

### 3. Modular Adapter Architecture

No two companies use the same toolchain. AgentCompany uses a first-class adapter system so that any tool layer can be swapped:

- Chat: Mattermost (default) | Slack | Discord
- Project management: Plane (default) | Linear | GitHub Issues
- Documentation: Outline (default) | Notion | Confluence
- Code: Gitea (default) | GitHub | GitLab

Swapping an adapter does not require changing agent behavior. Agents program against the AgentCompany abstraction layer, not the underlying tool.

### 4. Cost-Aware by Design

Token cost is a first-class concern, not an afterthought. Every agent interaction is instrumented with input/output token counts, cost estimates, and cumulative budgets. Org admins can set per-agent, per-role, and per-project token budgets. Agents that exceed their budget are suspended and a human is notified.

The heartbeat system (always-on vs. event-triggered agents) is the primary mechanism for controlling cost. Most agents should be event-triggered: they activate when assigned a ticket, receive a mention, or a scheduled trigger fires. Always-on agents are reserved for roles that genuinely require continuous awareness (e.g., a monitoring agent).

### 5. Transparent and Auditable

Every action an agent takes is logged with full context: what triggered it, what it read, what API calls it made, what it wrote, and how long it took. This is not optional telemetry. It is the foundation of trust between humans and agents. Users can replay an agent's decision trace to understand exactly why it did what it did.

### 6. Opinionated Defaults, Extensible Configuration

AgentCompany ships with a ready-to-use default company template: a software startup with CEO, CTO, PM, Developer, Designer, and QA roles. New users can be running a functional AI company within ten minutes of installation. Every default can be overridden. Custom roles, custom system prompts, custom tool access, and custom approval workflows are all first-class features.

---

## Target Users

### Primary: Solo Developers Running Agentic Companies

A developer who wants to ship software faster by delegating research, documentation, QA, and routine development tasks to agents. They act as the human CEO, approving high-stakes decisions while agents handle the operational backlog. They care deeply about cost, transparency, and being able to inspect what agents did. They self-host on a cheap VPS or home server.

**Pain today:** Agent frameworks like CrewAI require writing Python to configure everything. There is no UI. There is no project tracking. Cost visibility is minimal.

### Secondary: Small Teams Augmenting with AI

A team of 3-10 humans who want to add agent capacity without adding headcount. They want agents to handle documentation, test writing, ticket triage, and first-pass code review. Humans remain in the loop for final decisions. They need the agents to use the same tools the humans use so context is shared automatically.

**Pain today:** Teams end up running agents in separate ad-hoc scripts, disconnected from their actual project tools. Outputs have to be manually copied into Jira, Confluence, Slack. Integration is the bottleneck.

### Tertiary: Enterprises Piloting AI Workforce Expansion

An enterprise innovation team evaluating what an AI-augmented engineering organization looks like. They need auditability, role-based access controls, SSO integration, and the ability to ring-fence agent permissions. They will likely deploy AgentCompany alongside their existing tool stack, using the adapter layer to connect to their Jira, Confluence, or Slack instances rather than the default open-source alternatives.

**Pain today:** Enterprise-grade agent platforms (Cognition, Devin) are expensive, closed-source, and require giving a third party access to the codebase. Security and compliance teams will not approve this.

---

## Competitive Landscape

### The OpenHands / SWE-agent Benchmark Baseline

Projects like OpenHands (formerly OpenDevin) and SWE-agent operate purely on code repositories. They have no notion of org structure, team communication, project management, or documentation. They solve a narrow coding task. AgentCompany is a platform for running organizations, which happens to include coding.

### CrewAI / AutoGen / LangGraph

These are agent orchestration frameworks. They have Python APIs, no production UI, no tool integrations, no org structure, no cost monitoring. They are the engine; AgentCompany is the vehicle. In fact, AgentCompany's agent runtime may use these frameworks under the hood, while providing everything that sits above them.

### Paperclip (The Closest Comparison)

Paperclip is an academic / research project that explored AI company structures. It demonstrated that agents can be organized into corporate hierarchies and pass tasks between them. AgentCompany takes this concept and makes it production-grade:

| Dimension | Paperclip | AgentCompany |
|---|---|---|
| UI | Minimal / research-grade | Production web app, designed for daily use |
| Tool integration | Simulated / mocked | Real tools: Plane, Mattermost, Outline, Gitea |
| Tool swappability | None | Adapter layer; swap any integration |
| Org structure | Hardcoded | Configurable templates + custom roles |
| Cost monitoring | None | Per-agent, per-role, per-project token budgets |
| Heartbeat system | None | Always-on vs. event-triggered agents |
| Human-in-the-loop | Limited | Approval workflows, review queues, escalation |
| Audit trail | Minimal | Full decision trace per agent action |
| Self-hostable | Research repo | Docker Compose + production deployment guide |
| Open source | Yes | Yes (MIT) |

### Devin / Cognition AI

Devin is a commercial, closed-source AI software engineer. It is excellent at coding tasks in isolation. It has no org structure, no human collaboration model, no cost controls, and requires trusting a third party with your code. AgentCompany is open-source, self-hosted, and designed for teams rather than solo task execution.

---

## What We Are Not Building

- A general-purpose chatbot interface (use Claude.ai or ChatGPT for that)
- A robotic process automation platform (use n8n or Zapier for that)
- A CI/CD pipeline with AI (use GitHub Actions with AI steps for that)
- A replacement for human judgment on high-stakes decisions

AgentCompany is an organizational operating system. It is the infrastructure that lets agents and humans share context, coordinate work, and operate within clearly defined roles and budgets.

---

## Success Metrics (Year 1)

- 500+ GitHub stars within 3 months of public launch
- 50+ production deployments (tracked via anonymous opt-in telemetry)
- 5+ community-contributed adapter plugins
- Average time-to-first-agent-task under 15 minutes from fresh install
- Documented case study from at least one team using AgentCompany to ship a real product
