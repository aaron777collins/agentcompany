# AgentCompany — User Stories

**Version:** 1.0  
**Date:** 2026-04-18  
**Status:** Active

---

## Story Format

Each story follows the format:

> **As a** [persona], **I want to** [action], **so that** [outcome].

Acceptance criteria are written as testable conditions. Priority levels: **P0** (must-have for MVP), **P1** (important for v1), **P2** (nice-to-have).

---

## Personas

- **Alex** — Solo developer building a SaaS product, acting as human CEO
- **Sam** — Engineering lead at a 6-person startup, introducing agent collaborators
- **Jordan** — Enterprise architect evaluating AgentCompany for a pilot program
- **The CEO Agent** — An AI agent filling the CEO role in Alex's company
- **Dev Agent** — An AI agent filling a developer role

---

## Company Setup

### US-01 — Create a New Company (P0)

**As** Alex, **I want to** create a new virtual company with a name, description, and initial org structure template, **so that** I can start delegating work to agents within minutes.

**Acceptance Criteria:**
- User can create a company from a template (e.g., "Software Startup") or from scratch
- Template pre-populates roles: CEO, CTO, PM, Developer (x2), Designer, QA
- User is prompted to choose which roles to fill with agents vs. humans
- Company is provisioned with default boards, channels, and a documentation space
- Setup wizard completes in under 5 steps
- Completion time target: under 10 minutes from blank page to first agent assigned

---

### US-02 — Define and Customize Roles (P0)

**As** Alex, **I want to** add custom roles to my org chart and configure their responsibilities, tool access, and decision authority, **so that** my company structure matches my actual workflow.

**Acceptance Criteria:**
- User can add a role with a name, description, reporting line, and tool permission set
- Each role has a configurable system prompt template (personality/behavior for agents filling that role)
- Roles can be designated as agent-only, human-only, or either
- Changes to a role definition apply immediately to all agents holding that role
- Role hierarchy determines escalation and approval routing

---

### US-03 — Assign an Agent to a Role (P0)

**As** Alex, **I want to** assign an AI agent to a specific role in my org chart, **so that** the agent starts operating with that role's permissions, personality, and responsibilities.

**Acceptance Criteria:**
- User selects a role and clicks "Fill with Agent"
- User selects the underlying LLM (e.g., claude-sonnet-4-6, gpt-4o)
- User configures heartbeat mode: always-on, event-triggered, or scheduled
- Agent is created with a unique identity (name, avatar, role badge)
- Agent immediately appears in the org chart alongside human members
- Agent status shows as "Active" or "Standby" depending on heartbeat mode

---

### US-04 — Invite a Human to a Role (P1)

**As** Sam, **I want to** invite a human team member to fill a role in the org chart, **so that** they can collaborate with agents in the same tools and workflows.

**Acceptance Criteria:**
- User enters an email address and selects a role
- Invitation email is sent with a link to join the workspace
- Once accepted, the human appears in the org chart with a "Human" badge
- Human and agent occupying the same role tier can both see the same boards and channels
- Admin can reassign a human role to an agent at any time without disrupting in-flight work

---

## Agent Interaction

### US-05 — Trigger an Agent Manually (P0)

**As** Alex, **I want to** manually trigger an agent by assigning it a task or sending it a direct message, **so that** I can direct its effort on demand.

**Acceptance Criteria:**
- User can open an agent's profile and click "Assign Task," which creates a ticket assigned to the agent
- User can send a direct message to an agent in the chat interface
- Agent acknowledges the trigger within a configurable timeout (default: 30 seconds)
- Agent's current status updates to "Working" during task execution
- Trigger creates an audit log entry with timestamp, user, and task description

---

### US-06 — Review Agent Work Before It Goes Live (P0)

**As** Alex, **I want to** review and approve an agent's output before it is published or committed, **so that** I maintain control over final artifacts.

**Acceptance Criteria:**
- Roles can be configured with an approval requirement: "Agent output requires human approval before publishing"
- Agent-generated artifacts (docs, code, ticket updates) are placed in a "Pending Approval" state
- Human reviewer receives a notification in chat and email
- Reviewer can approve, reject with comments, or request changes
- Rejected artifacts are returned to the agent with reviewer comments as context for revision
- Approved artifacts are published immediately without further action

---

### US-07 — Inspect an Agent's Decision Trace (P1)

**As** Alex, **I want to** open an agent's activity log and see exactly what it read, what it decided, and what it wrote during a task, **so that** I can understand and trust its behavior.

**Acceptance Criteria:**
- Each completed task has a linked "Decision Trace" view
- Trace shows: trigger event, tools called (in order), content read, content written, LLM calls made
- Each LLM call shows: model, input token count, output token count, estimated cost
- Trace is stored for a configurable retention period (default: 90 days)
- Trace is exportable as JSON

---

### US-08 — Chat with an Agent in Natural Language (P0)

**As** Sam, **I want to** @mention an agent in a team channel or DM and have a natural language conversation with it, **so that** I can collaborate with agents the same way I collaborate with human colleagues.

**Acceptance Criteria:**
- @mentioning an agent in any channel triggers the agent to read the message and respond
- Agent response appears in the thread within a configurable timeout (default: 60 seconds)
- Agent has access to channel history (configurable number of messages as context)
- Agent can take actions from chat: "Create a ticket for this", "Write a doc about this", "Check the status of X"
- Agent identifies itself with its role badge in every message

---

## Project Management

### US-09 — Create a Project Board with Sprints (P0)

**As** Sam, **I want to** create a project board with a backlog and active sprint, **so that** both humans and agents can pick up and track work.

**Acceptance Criteria:**
- User can create a project with a name, description, and optional agent assignment rules
- Board supports Kanban and sprint views
- Tickets can be assigned to agents or humans
- Auto-assignment rules can be configured: "Tickets tagged 'backend' auto-assign to the Dev Agent"
- Sprint progress is visible on the company dashboard

---

### US-10 — Agent Auto-Triages and Estimates a Ticket (P1)

**As** Sam, **I want to** have a PM agent automatically review new tickets in the backlog, add labels, estimate complexity, and assign them to the appropriate agent or human, **so that** I spend less time on ticket hygiene.

**Acceptance Criteria:**
- PM agent is triggered when a new ticket is created (event-triggered heartbeat)
- Agent reads the ticket description and comments
- Agent adds complexity estimate (XS/S/M/L/XL) and confidence score as a ticket field
- Agent adds labels based on content (e.g., "backend," "bug," "research")
- Agent posts a brief triage comment explaining its reasoning
- Agent assigns the ticket if a matching auto-assignment rule exists; otherwise leaves it unassigned with a recommendation

---

### US-11 — Agent Picks Up a Ticket and Reports Progress (P0)

**As** Alex, **I want to** assign a ticket to a Dev Agent and have it update the ticket with progress as it works, **so that** I can monitor work without interrupting the agent.

**Acceptance Criteria:**
- When a ticket is assigned to an agent, the agent transitions it to "In Progress" immediately
- Agent posts progress comments at configurable intervals (default: on each significant action)
- Agent transitions the ticket to "In Review" when it believes the task is complete
- Ticket history shows all agent actions in the same timeline as human actions
- If the agent gets stuck, it transitions the ticket to "Blocked" and posts an explanation

---

## Documentation

### US-12 — Agent Generates Documentation After Completing a Task (P1)

**As** Sam, **I want to** have agents automatically generate or update documentation when they complete significant tasks, **so that** the knowledge base stays current without manual effort.

**Acceptance Criteria:**
- Each role can be configured with a "post-task documentation" policy
- After completing a task, the agent creates or updates a doc in the documentation system
- Doc is linked from the source ticket
- Doc is placed in the correct space based on role (e.g., Developer agent writes to "Engineering" space)
- Documentation is created in "Pending Approval" state if approval is required for that role

---

### US-13 — Unified Search Across All Tools (P0)

**As** Alex, **I want to** search for any piece of information — tickets, docs, chat messages, code — from a single search bar, **so that** I never have to remember which tool holds which information.

**Acceptance Criteria:**
- Search bar is accessible from every page via keyboard shortcut (Cmd/Ctrl + K)
- Results are returned across: tickets, documents, chat messages, and agent logs
- Results are ranked by relevance and recency
- Each result shows its source (tool name and location)
- Clicking a result opens it in context within the relevant tool view
- Search indexes update within 60 seconds of content creation

---

### US-14 — Agent-Generated Weekly Status Report (P1)

**As** Alex, **I want to** receive a weekly status report automatically generated by a PM agent, summarizing what was completed, what is in progress, and what is blocked, **so that** I stay informed without attending status meetings.

**Acceptance Criteria:**
- PM agent is scheduled to run every Monday morning (configurable)
- Report covers the previous week's completed tickets, open tickets by status, and blocked items
- Report includes token cost summary for all agents in the previous week
- Report is posted as a document and summarized in the main team channel
- Report format is configurable via a template

---

## Communication

### US-15 — @Mention Triggers Agent Action (P0)

**As** Sam, **I want to** @mention an agent in a ticket comment or chat message and have it execute a specific action, **so that** I can direct agents inline without switching contexts.

**Acceptance Criteria:**
- @mentioning an agent anywhere (chat, ticket comment, doc comment) triggers that agent
- Agent reads the surrounding context (ticket description, thread history, or doc section)
- Supported inline commands: "@agent summarize this", "@agent write tests for this", "@agent research X"
- Agent confirms the action it will take before executing (configurable: auto-execute for low-risk actions)
- Agent posts its output as a reply in the same thread

---

### US-16 — Human Escalation When Agent Is Stuck (P0)

**As** a Dev Agent, **I want to** escalate a task to my manager or the human admin when I cannot complete it autonomously, **so that** work is never silently abandoned.

**Acceptance Criteria:**
- Agent can detect "stuck" conditions: dependency missing, ambiguous requirements, tool error, exceeded retry limit
- On escalation, agent posts a structured message in the escalation channel: task summary, what was attempted, what is needed
- Agent transitions the ticket to "Blocked" with an escalation comment
- The responsible human (ticket assignee's manager, or org admin) receives a notification
- Escalation is logged in the agent's decision trace

---

## Admin and Observability

### US-17 — Monitor Token Usage and Set Budgets (P0)

**As** Alex, **I want to** see how many tokens each agent is consuming and set a weekly budget per agent, **so that** I can control AI costs.

**Acceptance Criteria:**
- Admin dashboard shows token usage per agent: today, this week, this month
- Cost is displayed in USD based on the configured model's pricing
- Admin can set a weekly token budget per agent
- When an agent reaches 80% of its budget, a warning notification is sent to the admin
- When an agent reaches 100% of its budget, it is suspended and the admin is notified
- Suspended agent transitions all in-progress tickets to "Blocked" with a budget explanation

---

### US-18 — Configure and Swap Adapters (P1)

**As** Jordan, **I want to** connect AgentCompany to my organization's existing Slack and Jira instances instead of the default tools, **so that** agents work with the tools my team already uses.

**Acceptance Criteria:**
- Admin settings has an "Integrations" section showing all configured adapters
- Each adapter category (chat, project management, docs, code) can be configured independently
- Switching an adapter requires entering credentials and clicking "Test Connection" before saving
- After switching, existing agent behavior continues without reconfiguration
- Failed adapter connections surface a clear error message with remediation steps
- Adapter health status is shown on the admin dashboard

---

### US-19 — View Agent Health Dashboard (P1)

**As** Sam, **I want to** see the real-time health status of all agents in my org, **so that** I know immediately when something is wrong.

**Acceptance Criteria:**
- Dashboard shows each agent's current state: Active, Standby, Working, Blocked, Suspended, Error
- Last-active timestamp is shown for each agent
- Agents in Error state show a brief error summary with a link to the full trace
- Dashboard auto-refreshes every 30 seconds
- Admin can restart, suspend, or force-trigger any agent from this view

---

### US-20 — Export Full Audit Log (P2)

**As** Jordan, **I want to** export a complete audit log of all agent actions within a date range, **so that** I can satisfy compliance requirements.

**Acceptance Criteria:**
- Admin can select a date range and export agent activity logs
- Export includes: agent ID, role, action type, timestamp, affected resource, token usage
- Export format: CSV and JSON
- Export is generated within 60 seconds for date ranges up to 90 days
- Logs are retained for a minimum of 1 year (configurable)
- Export action is itself logged in the audit trail
