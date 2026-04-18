# Web UI Handoff — AgentCompany

**Date:** 2026-04-18
**Author:** Staff Software Engineer
**Status:** Complete — ready for integration testing

---

## What Was Built

A complete Next.js 14 web UI for the AgentCompany platform. All files are hand-written (no `create-next-app`). The UI targets a modern SaaS aesthetic (Linear/Vercel/Raycast style) with a dark-first color scheme, smooth transitions, and no external component libraries.

---

## File Inventory

```
services/web-ui/
├── package.json                      Next.js 14, React 18, Tailwind 3, TypeScript
├── next.config.js                    Standalone output, image domains, /api/* rewrite
├── tailwind.config.ts                Custom color tokens, font stack, animation keyframes
├── tsconfig.json                     Strict mode, path aliases (@/*)
├── postcss.config.js                 Tailwind + autoprefixer
├── Dockerfile                        3-stage build (deps → builder → runner)
├── .env.example                      All env vars documented
├── src/
│   ├── app/
│   │   ├── layout.tsx                Root layout (metadata, html/body, dark class)
│   │   ├── ClientLayout.tsx          'use client' wrapper: Sidebar + CommandPalette + Cmd+K
│   │   ├── globals.css               Tailwind imports, Inter font, dark scrollbar, base styles
│   │   ├── page.tsx                  Dashboard: stats, agent table, activity feed, approvals
│   │   ├── companies/page.tsx        Company list + create modal
│   │   ├── org-chart/page.tsx        Org chart with company selector
│   │   ├── agents/page.tsx           Agent grid with status/company/name filters
│   │   ├── agents/[id]/page.tsx      Agent detail with 5 tabs
│   │   ├── tasks/page.tsx            Kanban board with drag-and-drop
│   │   ├── search/page.tsx           Unified search with debounce + tab filters
│   │   └── settings/page.tsx        Company settings, integration health, agent defaults
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx           Fixed left nav, active state, badge count
│   │   │   ├── Header.tsx            Sticky top bar with page title + actions slot
│   │   │   └── CommandPalette.tsx    Cmd+K modal: quick links + API search + keyboard nav
│   │   ├── dashboard/
│   │   │   ├── StatsCards.tsx        4-up metric cards with icons and skeleton states
│   │   │   ├── AgentStatusTable.tsx  Sortable agent table with status dots
│   │   │   ├── ActivityFeed.tsx      SSE-backed live event stream
│   │   │   └── ApprovalQueue.tsx     Approve/deny actions with optimistic updates
│   │   ├── agents/
│   │   │   ├── AgentCard.tsx         Grid card: avatar, status, task preview, token bar
│   │   │   ├── AgentDetail.tsx       5-tab detail: Overview, Logs, Tokens, Config, Memory
│   │   │   ├── TokenUsageChart.tsx   CSS bar chart (no library), 24h/7d/30d selector
│   │   │   └── AgentLogs.tsx         Scrollable log table with auto-scroll toggle
│   │   ├── org-chart/
│   │   │   └── OrgTree.tsx           Recursive CSS tree with status dots, click to agent
│   │   ├── tasks/
│   │   │   ├── KanbanBoard.tsx       Drag-and-drop state manager (optimistic updates)
│   │   │   ├── KanbanColumn.tsx      Single column: header, drop target highlight, task list
│   │   │   └── TaskCard.tsx          Task card: priority icon, labels, assignee avatar
│   │   └── ui/
│   │       ├── Button.tsx            5 variants, 4 sizes, loading state, icon slots
│   │       ├── Card.tsx              Base card + CardHeader/CardTitle sub-components
│   │       ├── Badge.tsx             Generic badge + StatusBadge with animated ping
│   │       ├── Input.tsx             Label, error, hint, left/right icon
│   │       ├── Modal.tsx             Escape key, backdrop click, scroll lock, slide-up
│   │       ├── Dropdown.tsx          Click-outside close, left/right align, danger items
│   │       └── Spinner.tsx           SVG spinner + PageSkeleton + SkeletonBlock
│   ├── lib/
│   │   ├── api.ts                    Typed fetch wrapper for all API endpoints
│   │   ├── types.ts                  TypeScript types matching backend Pydantic schemas
│   │   └── utils.ts                  Date formatting, status colors, cx(), debounce, etc.
│   └── hooks/
│       ├── useAgents.ts              Agent list + single agent hook with 15s polling
│       ├── useCompany.ts             Company list, single company, active company (localStorage)
│       └── useSSE.ts                 EventSource with exponential backoff reconnect
```

---

## Design System

### Color Tokens (tailwind.config.ts)

| Token | Value | Usage |
|---|---|---|
| `surface` | `#0f1117` | Body background |
| `surface-1` through `surface-4` | `#151821`–`#252840` | Card backgrounds, elevated surfaces |
| `surface-border` | `#2a2f45` | Borders throughout |
| `accent` | `#6366f1` | Primary actions, active nav, focus rings |
| `status-active` | `#22c55e` | Active agent status |
| `status-idle` | `#eab308` | Idle agent status |
| `status-error` | `#ef4444` | Error state, destructive actions |
| `status-stopped` | `#6b7280` | Stopped / disabled |
| `status-pending` | `#3b82f6` | In-queue, waiting |
| `text-primary` | `#f1f5f9` | Primary text |
| `text-secondary` | `#94a3b8` | Body copy, descriptions |
| `text-muted` | `#475569` | Labels, hints |

### Font Stack
Primary: Inter (loaded from Google Fonts in globals.css). Monospace: JetBrains Mono (agent logs, IDs, code).

### Component Patterns
- All interactive elements have `focus-visible:ring-2 ring-accent` for keyboard accessibility
- Skeleton states match the shape of real content (not generic spinners)
- Hover states use `transition-all duration-150` for snappy feel
- Cards use `hover:-translate-y-0.5` for depth on hover

---

## API Integration

### Base URL
Set via `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000/api/v1`).

### Auth
Currently uses `credentials: 'include'` (cookie-based). When Keycloak SSO is wired in, change the fetch wrapper in `src/lib/api.ts` to add an `Authorization: Bearer <token>` header. The cookie approach is a known placeholder (documented in api.ts with a ticket reference comment).

### SSE
The `useSSE` hook creates an `EventSource` pointing at `/events/stream`. It expects each `message` event to carry a JSON-encoded `Event` object. Reconnects with exponential backoff (1s → 30s cap).

### Error Handling
All API errors throw `ApiClientError` with `{ status, code, message, detail }`. Components catch these and display inline error states. The `ApiClientError` class is exported from `lib/api.ts` for `instanceof` checking.

---

## State Management

No global state library (no Redux, no Zustand). State is local to each page component, passed down as props. The only cross-page state is:

- `activeCompanyId` — stored in `localStorage` via `useActiveCompany` hook. Used by Tasks and Org Chart pages to remember which company is selected.

---

## Pages and Routes

| Route | Component | Data sources |
|---|---|---|
| `/` | Dashboard | `metrics.platform`, `agents.list`, `approvals.list`, SSE |
| `/companies` | Company list + create | `companies.list`, `companies.create` |
| `/org-chart` | Tree visualization | `orgChart.get(companyId)` |
| `/agents` | Agent grid | `agents.list` with filters |
| `/agents/[id]` | Agent detail | `agents.get`, `agents.memories`, `agents.tokenUsage`, `agents.logs` |
| `/tasks` | Kanban board | `tasks.list`, `tasks.update` (drag), `tasks.create` |
| `/search` | Unified search | `search.query` (debounced 300ms) |
| `/settings` | Platform settings | `integrations.health`, `companies.get/update` |

---

## Performance Notes

- All pages are `'use client'` because they need React hooks. Converting to RSC + server actions would reduce JS bundle size but requires auth cookie handling in server context — deferred to a future sprint.
- `useAgents` polls every 15s. The dashboard's metrics poll every 30s. These intervals were chosen to keep the UI feeling live without hammering the API in development.
- The token usage chart is a pure CSS/SVG bar chart — no charting library dependency.
- The Kanban board uses native HTML5 drag-and-drop (no library). Optimistic updates mean the UI feels instant even if the API call takes 200ms.

---

## Known Gaps / Follow-up Work

| Item | Priority | Notes |
|---|---|---|
| Keycloak SSO integration | High | Replace `credentials: 'include'` in api.ts with Bearer token. Redirect to Keycloak login if 401. |
| Real-time Kanban | Medium | Wire task status changes through SSE so multiple users see updates. |
| Org chart drag-to-reorder | Low | Architecture spec marks this as future. OrgTree is structured to support it. |
| Light mode toggle | Low | Dark mode is default and `darkMode: 'class'` is configured. Add a toggle button to the header. |
| Error boundaries | Medium | Pages show inline error states but no React ErrorBoundary wraps the route tree. |
| Pagination | Medium | API client sends `page`/`page_size` but pages only load the first 50/100 items. |
| `notFound()` usage in agents/[id] | Low | The import is present but unused — the error state covers this case. Remove the import. |

---

## Running Locally

```bash
cd services/web-ui
cp .env.example .env.local
# Edit .env.local — set NEXT_PUBLIC_API_URL to your backend

npm install
npm run dev
```

The UI is available at `http://localhost:3000`.

### With Docker

```bash
docker build -t agentcompany-web-ui .
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 agentcompany-web-ui
```

The Dockerfile uses Next.js `output: 'standalone'` for a minimal image. The final stage runs as a non-root `nextjs` user.

---

## Files Produced

```
services/web-ui/          (all files — see inventory above)
docs/handoffs/webui-handoff.md  (this document)
```
