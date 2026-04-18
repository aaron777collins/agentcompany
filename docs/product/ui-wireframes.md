# AgentCompany — UI Wireframes

**Version:** 1.0  
**Date:** 2026-04-18  
**Status:** Active

---

## Design Philosophy

AgentCompany's UI is designed around three principles:

1. **Humans and agents share one interface.** There is no separate "agent admin console" and "user workspace." Humans work alongside agents in the same views, and agents appear in the same places human collaborators do.

2. **Status is always visible.** A user should never have to hunt for what an agent is currently doing. Agent status, recent actions, and pending approvals are surfaced prominently on every relevant screen.

3. **Dense information, clean layout.** The UI is information-dense by design (think Linear or Plane rather than Notion's airy whitespace), but uses a consistent visual language with clear hierarchy so it never feels cluttered.

---

## Color and Status Language

| State | Color | Usage |
|---|---|---|
| Active / Working | Blue (#2980b9) | Agent is currently running a task |
| Standby | Gray (#95a5a6) | Event-triggered agent waiting |
| Blocked | Orange (#e67e22) | Agent escalated or awaiting input |
| Suspended | Red (#e74c3c) | Budget exceeded or manually suspended |
| Done | Green (#27ae60) | Task completed successfully |
| Pending Approval | Yellow (#f1c40f) | Artifact awaiting human review |
| Human | Warm white (#fef9e7) | Human org member indicator |
| Agent | Light blue (#e8f4fd) | AI agent indicator |

---

## Screen 1: Dashboard (Company Overview)

### Purpose

The landing page after login. Shows the pulse of the company: who is active, what is happening, and what requires the human's attention.

### Layout Description

```
+------------------------------------------------------------------+
| [AgentCompany Logo]  [Company Name]    [Search]  [Bell] [Avatar] |
+--+-------+--+--------------------------------------------------------+
|  |       |  |                                                        |
| Nav     |  |                  MAIN CONTENT AREA                     |
|  |  S  |  |                                                        |
|  |  I  |  +--------------------------------------------------------+
|  |  D  |  |                                                        |
|  |  E  |  |                                                        |
|  |  B  |  |                                                        |
|  |  A  |  |                                                        |
|  |  R  |  |                                                        |
|  |       |  |                                                        |
+--+-------+--+--------------------------------------------------------+
```

### Detailed Wireframe

```
+------------------------------------------------------------------------+
| AC  Acme Corp AI             [Cmd+K Search...]  [0] Approvals [Avatar] |
+--------+---------------------------------------------------------------+
|        |                                                               |
| Dash   |  COMPANY PULSE                                  Apr 18, 2026 |
|        |  +-----------------+  +------------------+  +---------------+|
| Org    |  | Agents Active   |  | Pending Approvals|  | Weekly Tokens ||
|        |  |      3 / 7      |  |       2          |  |   124k / 500k ||
| Board  |  | [=====------]   |  | [Review Now]     |  |  [==---]  25% ||
|        |  +-----------------+  +------------------+  +---------------+|
| Docs   |                                                               |
|        |  AGENT STATUS                                        [+ Add] |
| Chat   |  +----------------------------------------------------------+|
|        |  | Name        Role       Status    Last Active  Tokens/Wk ||
| Search |  |----------------------------------------------------------||
|        |  | Jordan      Developer  WORKING   just now     18.2k     ||
| Admin  |  | Sam         PM         STANDBY   5 min ago    12.1k     ||
|        |  | Riley       QA         STANDBY   1 hr ago     4.8k      ||
|        |  | Morgan      CTO        WORKING   just now     31.4k     ||
|        |  | Casey       CFO        STANDBY   6 hrs ago    2.1k      ||
|        |  | Alex H.     CEO        [Human]   3 min ago    --        ||
|        |  | Jamie H.    Designer   [Human]   yesterday    --        ||
|        |  +----------------------------------------------------------+|
|        |                                                               |
|        |  RECENT ACTIVITY                                 [View All] |
|        |  +----------------------------------------------------------+|
|        |  | [Jordan-Dev]  Pushed to PR #52 · auth-rate-limiting  2m  ||
|        |  | [Morgan-CTO]  Reviewed PR #51 · approved             8m  ||
|        |  | [Sam-PM]      Triaged ticket #88 · Est: M, backend  12m  ||
|        |  | [Jordan-Dev]  Posted progress on ticket #85         24m  ||
|        |  | [Riley-QA]    Completed test plan for PR #50        1hr  ||
|        |  +----------------------------------------------------------+|
|        |                                                               |
|        |  PENDING APPROVALS                                          |
|        |  +----------------------------------------------------------+|
|        |  | [!] PR #52  Add rate limiting · from Jordan-Dev   [Review]||
|        |  | [!] Doc Draft  Auth Flow Overview · from Jordan-Dev [Rev]||
|        |  +----------------------------------------------------------+|
|        |                                                               |
+--------+---------------------------------------------------------------+
```

### Component Annotations

**Top Bar:**
- Logo + Company name (links to dashboard)
- Global search (Cmd+K shortcut)
- Approval badge with count (red dot when > 0)
- User avatar with dropdown (profile, settings, sign out)

**Left Sidebar (persistent navigation):**
- Dashboard (home)
- Org Chart
- Board (project management)
- Docs (documentation system)
- Chat (opens embedded or links to chat tool)
- Search (unified search)
- Admin (gear icon, role-gated)

**Company Pulse Cards (3-up row):**
- Agents Active: X of Y with a progress bar visualization
- Pending Approvals: count with a direct CTA button
- Weekly Tokens: cumulative usage with budget bar

**Agent Status Table:**
- Sortable columns: name, role, status, last active, tokens this week
- Status indicator is color-coded (see status language above)
- Human members show "Human" badge instead of status/tokens
- Clicking a row opens the Agent Detail view

**Recent Activity Feed:**
- Chronological list of agent and human actions
- Each entry: avatar, name, action description, relative timestamp
- Clicking opens the referenced artifact

**Pending Approvals:**
- High-priority section at bottom (or top if count > 3)
- One line per approval: PR or doc, description, agent name, Review button

---

## Screen 2: Org Chart View

### Purpose

Visual representation of the company structure. Quickly see who fills each role, whether they are human or agent, and their current status.

### Detailed Wireframe

```
+------------------------------------------------------------------------+
| AC  Acme Corp AI             [Cmd+K Search...]  [0] Approvals [Avatar] |
+--------+---------------------------------------------------------------+
|        |                                                               |
| Dash   |  ORG CHART                           [+ Add Role]  [Edit Org] |
|        |                                                               |
| Org  > |  View: [Tree v]   Filter: [All Roles v]  [All Status v]       |
|        |                                                               |
| Board  |                                                               |
|        |          +--------------------------+                         |
| Docs   |          |  [Avatar] Alex H.        |                         |
|        |          |  CEO - Human             |                         |
| Chat   |          |  Active 3 min ago        |                         |
|        |          +--------------------------+                         |
| Search |            /         |           \                            |
|        |           /          |            \                           |
| Admin  |  +-------------+  +--------+  +----------+                   |
|        |  | [Av] Morgan |  | [Av]   |  | Jamie H. |                   |
|        |  |  CTO        |  | Sam    |  | Designer |                   |
|        |  |  [Agent]    |  |  PM    |  | [Human]  |                   |
|        |  |  WORKING    |  | [Agent]|  | Offline  |                   |
|        |  |  [Tokens]   |  | STANDBY|  |          |                   |
|        |  +-------------+  +--------+  +----------+                   |
|        |    /         \                                                |
|        | +-------+  +-------+  +-------+                             |
|        | |[Av]   |  |[Av]   |  |[Av]   |                             |
|        | |Jordan |  |Dev 2  |  |Riley  |                             |
|        | |Dev    |  |Dev    |  |QA     |                             |
|        | |[Agent]|  |[Agent]|  |[Agent]|                             |
|        | |WORKING|  |STANDBY|  |STANDBY|                             |
|        | +-------+  +-------+  +-------+                             |
|        |                                                               |
|        |  UNFILLED ROLES                                              |
|        |  +----------------------------------------------------------+|
|        |  | CFO  (no agent or human assigned)              [Fill Now]||
|        |  +----------------------------------------------------------+|
|        |                                                               |
+--------+---------------------------------------------------------------+
```

### Node Card Design (each org chart node)

```
+---------------------------+
| [Avatar 32px]  Name       |
| Role Title                |
| [Agent] or [Human] badge  |
| Status dot + label        |
| Token bar (agents only)   |
+---------------------------+
```

Clicking any node opens a popover with:
- Quick stats (tokens this week, tasks completed today)
- Recent activity (last 3 actions)
- Action buttons: View Profile, Message, Assign Task, View Audit Log

### Interaction Notes

- **Drag-and-drop** to reorganize reporting lines (admin only)
- **Zoom and pan** on large org charts using mouse/trackpad
- Filter dropdown: show only Agents, only Humans, only Active, only Blocked
- "Edit Org" mode unlocks role renaming, deletion, and hierarchy changes
- Unfilled roles appear at the bottom in a distinct "Unfilled Roles" section with a "Fill Now" CTA

---

## Screen 3: Agent Detail View

### Purpose

Deep-dive profile for a single agent: current status, recent actions, configuration, token usage, and full audit log.

### Detailed Wireframe

```
+------------------------------------------------------------------------+
| AC  Acme Corp AI             [Cmd+K Search...]  [2] Approvals [Avatar] |
+--------+---------------------------------------------------------------+
|        |                                                               |
| Dash   |  < Back to Org Chart                                         |
|        |                                                               |
| Org  > |  [Jordan avatar 64px]  Jordan                 [Message] [...]|
| Agent  |  Developer · Reports to Morgan (CTO)                         |
|        |  Model: claude-sonnet-4-6  |  Heartbeat: Event-triggered      |
| Board  |  Status: [blue] WORKING   |  Last Active: just now           |
|        |                                                               |
| Docs   |  +--------------------+  +------------------------------+    |
|        |  |  TOKEN USAGE       |  |  TASK STATS (this sprint)    |    |
| Chat   |  |  Today:    3,241   |  |  Completed:    4             |    |
|        |  |  This Week: 18.2k  |  |  In Progress:  1             |    |
| Search |  |  This Month: 62k   |  |  Blocked:      0             |    |
|        |  |  Budget: 500k/wk   |  |  PRs Opened:   5             |    |
| Admin  |  |  [====-------] 25% |  |  PRs Merged:   4             |    |
|        |  +--------------------+  +------------------------------+    |
|        |                                                               |
|        |  CURRENT TASK                                                |
|        |  +----------------------------------------------------------+|
|        |  | Ticket #88: Add rate limiting to auth API                ||
|        |  | Started: 14 min ago  |  Estimated: M                    ||
|        |  | Phase: Writing tests (step 3 of 4)                      ||
|        |  | [View Ticket]  [View Decision Trace]                     ||
|        |  +----------------------------------------------------------+|
|        |                                                               |
|        |  RECENT ACTIONS                                 [View All] |
|        |  +----------------------------------------------------------+|
|        |  | 2m   Pushed 3 files to branch auth-rate-limiting        ||
|        |  | 5m   Read file: src/auth/middleware.ts (2,400 tokens)   ||
|        |  | 8m   Posted comment on ticket #88                       ||
|        |  | 12m  Read ticket #88 description (340 tokens)           ||
|        |  | 14m  Ticket #88 assigned — agent woke up                ||
|        |  +----------------------------------------------------------+|
|        |                                                               |
|        |  TABS: [Configuration] [Approval Policy] [Audit Log]        |
|        |                                                               |
|        |  -- CONFIGURATION TAB --                                    |
|        |  +----------------------------------------------------------+|
|        |  | Heartbeat Mode:    [Event-triggered v]                   ||
|        |  | Triggers:          [X] ticket_assigned [X] pr_comment   ||
|        |  |                    [X] direct_mention  [ ] scheduled    ||
|        |  | Weekly Budget:     [500,000] tokens                     ||
|        |  | Tone:              [Technical v]                        ||
|        |  | Verbosity:         [Medium v]                           ||
|        |  | System Prompt Additions:                                ||
|        |  | +----------------------------------------------------+  ||
|        |  | | You are a Senior Software Engineer...              |  ||
|        |  | +----------------------------------------------------+  ||
|        |  | [Save Changes]  [Reset to Role Defaults]               ||
|        |  +----------------------------------------------------------+|
|        |                                                               |
|        |  ADMIN ACTIONS:  [Suspend Agent]  [Restart Agent]  [Delete] |
+--------+---------------------------------------------------------------+
```

### Decision Trace Detail (sub-view)

When "View Decision Trace" is clicked for a task:

```
+----------------------------------------------------------+
|  DECISION TRACE: Ticket #88 — Rate Limiting              |
|  Started: 2026-04-18 14:22:01  |  Duration: 14m 22s      |
|  Total Tokens: 3,241 in / 892 out  |  Est. Cost: $0.048  |
+----------------------------------------------------------+
|  STEP  TIME   ACTION                          TOKENS     |
|  ----  -----  ----------------------------   -------     |
|  1     14:22  Trigger received: ticket #88 assigned       |
|  2     14:22  Read: ticket #88 (description + comments)  340i  |
|  3     14:23  LLM call: Analyze requirements             420i / 180o |
|  4     14:24  Read: src/auth/middleware.ts              2,400i  |
|  5     14:28  LLM call: Plan implementation approach     680i / 220o |
|  6     14:30  Write: src/auth/rate-limit.ts (new file)  |
|  7     14:32  Write: tests/auth/rate-limit.test.ts      |
|  8     14:35  LLM call: Generate PR description         340i / 180o |
|  9     14:35  Create PR #52 in Gitea                    |
| 10     14:36  Post comment on ticket #88                |
+----------------------------------------------------------+
|  [Export as JSON]                     [Close]           |
+----------------------------------------------------------+
```

---

## Screen 4: Unified Search

### Purpose

Single search entry point covering all tools and data sources. Accessible from anywhere via Cmd+K.

### Detailed Wireframe

```
+------------------------------------------------------------------------+
|                                                                        |
|              +------------------------------------------+             |
|              |  [Search icon]  Search everything...  [X]|             |
|              +------------------------------------------+             |
|              |  [Tickets]  [Docs]  [Chat]  [Code]  [All] |             |
|              +------------------------------------------+             |
|              |                                          |             |
|  (triggered  |  RESULTS FOR: "rate limiting"            |             |
|   by user    |  ----------------------------------------|             |
|   typing     |  TICKETS (3)                             |             |
|   "rate      |  [T]  #88 Add rate limiting to auth API  |             |
|   limiting") |       High · Sprint 1 · Assigned: Jordan |             |
|              |  [T]  #61 Research rate limiting options  |             |
|              |       Done · Sprint 0 · Closed by Sam     |             |
|              |  [T]  #42 Rate limit exceeded error logs  |             |
|              |       Medium · Backlog · Unassigned        |             |
|              |  ----------------------------------------|             |
|              |  DOCUMENTS (2)                           |             |
|              |  [D]  Auth API — Rate Limiting (Draft)   |             |
|              |       Engineering · Created by Jordan 2m ago           |
|              |  [D]  Auth Architecture Overview          |             |
|              |       Engineering · Updated 3 days ago    |             |
|              |  ----------------------------------------|             |
|              |  CHAT MESSAGES (5)                       |             |
|              |  [C]  Morgan in #engineering: "rate lim.." 8m ago     |             |
|              |  [C]  Sam in #product: "included rate.."  1hr ago     |             |
|              |  [C]  ... (3 more)                        |             |
|              |  ----------------------------------------|             |
|              |  CODE (1)                                |             |
|              |  [G]  src/auth/rate-limit.ts              |             |
|              |       main-app · Modified by Jordan 5m ago             |             |
|              |                                          |             |
|              |  [Show all results →]                    |             |
|              +------------------------------------------+             |
|                                                                        |
+------------------------------------------------------------------------+
```

### Search UX Notes

- Modal overlay opens centered over any page
- Keyboard navigation: arrows to move between results, Enter to open, Escape to close
- Results update as user types (300ms debounce)
- Each result category (Tickets, Docs, Chat, Code) can be toggled via the filter tabs
- Result snippets show matched text in **bold**
- Source icon distinguishes tool type (Plane icon for tickets, Outline icon for docs, etc.)
- "Show all results" opens a full-page search results view with pagination and advanced filters

### Advanced Search (full-page mode)

Additional filters available in full-page mode:
- Date range
- Author (human or specific agent)
- Status (open/closed, published/draft)
- Project / space
- Sort by: relevance, date modified, date created

---

## Screen 5: Settings / Admin

### Purpose

Administrative control center: configure adapters, set budgets, manage users and agents, review system health.

### Detailed Wireframe

```
+------------------------------------------------------------------------+
| AC  Acme Corp AI             [Cmd+K Search...]  [0] Approvals [Avatar] |
+--------+---------------------------------------------------------------+
|        |                                                               |
| Dash   |  ADMIN SETTINGS                                              |
|        |                                                               |
| Org    |  [Company] [Integrations] [Agents] [Budget] [Security] [Logs]|
|        |                                                               |
| Board  |  == INTEGRATIONS TAB ==                                      |
|        |  +----------------------------------------------------------+|
| Docs   |  | CHAT                                          [Configured]||
|        |  | Adapter:  Mattermost                                     ||
| Chat   |  | URL:      http://mattermost.internal:8065                ||
|        |  | Status:   [green] Connected  · Last check: 30s ago       ||
| Search |  | [Test Connection]  [Edit]  [Swap Adapter v]               ||
|        |  +----------------------------------------------------------+|
| Admin >|  | PROJECT MANAGEMENT                            [Configured]||
|        |  | Adapter:  Plane                                          ||
|        |  | URL:      http://plane.internal:3000                     ||
|        |  | Status:   [green] Connected  · Last check: 30s ago       ||
|        |  | [Test Connection]  [Edit]  [Swap Adapter v]               ||
|        |  +----------------------------------------------------------+|
|        |  | DOCUMENTATION                                 [Configured]||
|        |  | Adapter:  Outline                                        ||
|        |  | URL:      http://outline.internal:3001                   ||
|        |  | Status:   [green] Connected  · Last check: 30s ago       ||
|        |  | [Test Connection]  [Edit]  [Swap Adapter v]               ||
|        |  +----------------------------------------------------------+|
|        |  | CODE REPOSITORY                               [Configured]||
|        |  | Adapter:  Gitea                                          ||
|        |  | URL:      http://gitea.internal:3000                     ||
|        |  | Status:   [green] Connected  · Last check: 30s ago       ||
|        |  | [Test Connection]  [Edit]  [Swap Adapter v]               ||
|        |  +----------------------------------------------------------+|
|        |  | LLM PROVIDER                                  [Configured]||
|        |  | Provider: Anthropic                                      ||
|        |  | Default Model: claude-sonnet-4-6                        ||
|        |  | API Key:  sk-ant-********************  [Reveal] [Change] ||
|        |  | Status:   [green] Valid key                              ||
|        |  +----------------------------------------------------------+|
|        |                                                               |
|        |  == BUDGET TAB ==                                            |
|        |  +----------------------------------------------------------+|
|        |  | COMPANY-WIDE BUDGET                                      ||
|        |  | Monthly token limit:   [5,000,000     ] tokens          ||
|        |  | Monthly cost estimate: ~$75.00 at current usage         ||
|        |  | Alert threshold:       [80] %                           ||
|        |  +----------------------------------------------------------+|
|        |  | PER-AGENT BUDGETS                                        ||
|        |  | Agent        Role       Weekly Limit   Used This Wk     ||
|        |  | Jordan       Developer  500k           18.2k (4%)       ||
|        |  | Sam          PM         200k           12.1k (6%)       ||
|        |  | Morgan       CTO        1,000k         31.4k (3%)       ||
|        |  | Riley        QA         300k           4.8k  (2%)       ||
|        |  | Casey        CFO        100k           2.1k  (2%)       ||
|        |  | [Edit Budgets]                                           ||
|        |  +----------------------------------------------------------+|
|        |                                                               |
|        |  == AGENTS TAB ==                                            |
|        |  +----------------------------------------------------------+|
|        |  | [+ Provision New Agent]                                  ||
|        |  |                                                          ||
|        |  | Name    Role      Model              Status  [Actions]  ||
|        |  | Jordan  Developer claude-sonnet-4-6  Active  [...]      ||
|        |  | Sam     PM        claude-sonnet-4-6  Standby [...]      ||
|        |  | Morgan  CTO       claude-sonnet-4-6  Active  [...]      ||
|        |  | Riley   QA        claude-sonnet-4-6  Standby [...]      ||
|        |  | Casey   CFO       claude-sonnet-4-6  Standby [...]      ||
|        |  |                                                          ||
|        |  | Action menu [...]: View Profile | Suspend | Restart |   ||
|        |  |                    Delete | Edit Config                  ||
|        |  +----------------------------------------------------------+|
|        |                                                               |
+--------+---------------------------------------------------------------+
```

### Adapter Swap Flow

When the user clicks "Swap Adapter" for a category (e.g., swapping from Mattermost to Slack):

```
+----------------------------------------------------------+
|  SWAP CHAT ADAPTER                                       |
|  Current: Mattermost                                     |
|                                                          |
|  Select new adapter:                                     |
|  ( ) Mattermost  (current)                              |
|  (*) Slack                                               |
|  ( ) Discord                                             |
|  ( ) Custom (provide API spec URL)                       |
|                                                          |
|  SLACK CONFIGURATION                                     |
|  Bot Token:     [xoxb-.....................  ]           |
|  Workspace URL: [https://acmecorp.slack.com ]           |
|                                                          |
|  [Test Connection]    <- must succeed before Save        |
|                                                          |
|  [!] Warning: Switching adapters will reconnect all      |
|  agents to the new chat system. In-flight tasks will    |
|  complete on the current adapter.                       |
|                                                          |
|  [Cancel]                   [Save and Switch]           |
+----------------------------------------------------------+
```

### Security Tab (brief wireframe)

```
+----------------------------------------------------------+
|  SECURITY                                                |
|                                                          |
|  Authentication                                          |
|  [X] Local accounts enabled                             |
|  [ ] SSO / SAML  [Configure]                            |
|  [ ] OAuth (Google, GitHub)  [Configure]                |
|                                                          |
|  Agent Permissions                                       |
|  Default approval policy:  [Require approval for code v]|
|  Allow agents to create other agents:  [ ] No           |
|  Max agent delegation depth:  [2]                       |
|                                                          |
|  Audit Logging                                           |
|  Retention period:  [90 days v]                         |
|  Export format:  [X] JSON  [X] CSV                      |
|  [Download Full Audit Log]                               |
|                                                          |
|  Data                                                    |
|  [Export All Company Data]  [Delete Company]            |
+----------------------------------------------------------+
```

---

## Navigation and Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| Cmd/Ctrl + K | Open unified search |
| Cmd/Ctrl + N | New ticket (when on Board screen) |
| Cmd/Ctrl + Shift + A | Open approval queue |
| G then D | Go to Dashboard |
| G then O | Go to Org Chart |
| G then B | Go to Board |
| G then C | Go to Chat |
| Escape | Close modal / popover |

---

## Responsive Behavior

**Desktop (1280px+):** Full sidebar + content layout as shown above.

**Tablet (768–1279px):** Sidebar collapses to icon-only. Content area uses simplified layouts. Org chart switches to a scrollable list view.

**Mobile (< 768px):** Bottom navigation bar replaces sidebar. Dashboard shows summary cards only. Org chart shows flat list. Agent detail view is full-screen. Admin settings are accessible but editing is discouraged on mobile.

---

## Accessibility Standards

- WCAG 2.1 AA compliance target
- All status indicators use both color and icon/text (not color alone)
- Keyboard navigation for all interactive elements
- Screen reader labels on all agent status indicators and action buttons
- Focus management in modal flows (focus trap, return focus on close)
- Minimum 4.5:1 contrast ratio for all text elements
