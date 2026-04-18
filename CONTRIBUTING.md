# Contributing to AgentCompany

Thank you for your interest in contributing. This guide explains how to set up
a development environment, navigate the project structure, and get your changes
merged.

---

## Table of contents

- [Development environment setup](#development-environment-setup)
- [Project structure](#project-structure)
- [How to add a new adapter](#how-to-add-a-new-adapter)
- [How to add a new agent role](#how-to-add-a-new-agent-role)
- [Code style](#code-style)
- [Pull request process](#pull-request-process)
- [License](#license)

---

## Development environment setup

### Prerequisites

| Tool | Minimum version | Install guide |
|------|----------------|---------------|
| Docker | 24.x | https://docs.docker.com/get-docker/ |
| Docker Compose plugin | v2.x | https://docs.docker.com/compose/install/ |
| Python | 3.12 | https://www.python.org/downloads/ |
| Node.js | 20 LTS | https://nodejs.org/ |
| npm | 10.x | ships with Node.js |
| Git | 2.x | https://git-scm.com/ |

Optional but recommended:

- `jq` — used by seed-data.sh and helpful for inspecting API responses
- `ruff` — Python linter/formatter (installed automatically in the venv)

### First-time setup

```bash
git clone https://github.com/aaron777collins/agentcompany.git
cd agentcompany

# Start infrastructure, generate secrets, pull and build images
./scripts/setup.sh
```

`setup.sh` copies `.env.example` to `.env`, fills in random secrets, pulls all
Docker images, and starts every service. Access URLs are printed at the end.

### Day-to-day development

```bash
# Start infrastructure containers + watch-mode processes for agent-runtime and web-ui
./scripts/dev.sh
```

`dev.sh` keeps infrastructure services running in Docker and starts
`uvicorn --reload` (Python) and `next dev` (Node) natively on your host so
code changes are reflected immediately without rebuilding images.

### Seed development data

After the platform is running for the first time:

```bash
./scripts/seed-data.sh
```

This creates a sample company, org roles, agents, a project board, a welcome
document, and a Mattermost channel.

### Useful commands

```bash
# Tail logs for a specific service
docker compose logs -f agent-runtime

# Open a Postgres shell
docker compose exec postgres psql -U agentcompany agentcompany_core

# Run backend tests
cd services/agent-runtime
python -m pytest --tb=short -q

# Run the Python linter
ruff check .
ruff format --check .

# TypeScript type check
cd services/web-ui
npm run type-check

# Stop everything (keep data)
./scripts/teardown.sh

# Wipe everything including volumes
./scripts/teardown.sh --purge
```

---

## Project structure

```
agentcompany/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml              # PR and push CI (lint, test, docker build)
│   │   └── docker-publish.yml  # Release pipeline (ghcr.io push on v* tag)
│   └── ISSUE_TEMPLATE/         # Bug report and feature request templates
│
├── configs/
│   ├── keycloak/
│   │   └── realm-export.json   # Keycloak realm: clients, roles, default user
│   ├── mattermost/
│   │   └── config.json         # Mattermost server config (dev baseline)
│   └── outline/
│       └── outline.env         # Outline env var reference (documented)
│
├── docker/
│   ├── init-scripts/
│   │   └── init-databases.sql  # Creates postgres databases on first boot
│   └── traefik/
│       ├── traefik.yml         # Traefik static config
│       └── dynamic.yml         # Traefik dynamic routes and middleware
│
├── docs/
│   ├── architecture/           # Architecture decision records and specs
│   ├── handoffs/               # Per-agent handoff notes
│   ├── product/                # Product requirements and roadmap
│   └── research/               # Technical research notes
│
├── scripts/
│   ├── setup.sh                # First-time bootstrap (DO NOT overwrite)
│   ├── teardown.sh             # Graceful shutdown (DO NOT overwrite)
│   ├── dev.sh                  # Dev mode with hot-reload
│   └── seed-data.sh            # Populate sample data via API
│
├── services/
│   ├── agent-runtime/          # Python/FastAPI agent orchestration service
│   │   ├── app/                # Application code
│   │   │   ├── main.py         # FastAPI app and startup
│   │   │   ├── agents/         # Agent lifecycle, decision loop
│   │   │   ├── adapters/       # LLM adapters (Anthropic, OpenAI, Ollama)
│   │   │   ├── tools/          # Built-in tools (search, chat, project, ...)
│   │   │   ├── org/            # Org hierarchy and escalation engine
│   │   │   ├── api/            # Route handlers
│   │   │   └── db/             # SQLAlchemy models and repositories
│   │   ├── alembic/            # Database migrations
│   │   ├── tests/              # pytest test suite
│   │   ├── Dockerfile
│   │   ├── pyproject.toml      # Project metadata, ruff config, pytest config
│   │   └── requirements.txt
│   │
│   └── web-ui/                 # Next.js 14 frontend
│       ├── src/
│       │   ├── app/            # App Router pages and layouts
│       │   ├── components/     # Shared React components
│       │   └── lib/            # API client, auth helpers, utilities
│       ├── public/             # Static assets
│       ├── Dockerfile
│       ├── package.json
│       └── tsconfig.json
│
├── docker-compose.yml          # Full stack (DO NOT overwrite)
├── .env.example                # Environment variable reference (DO NOT overwrite)
├── CONTRIBUTING.md             # This file
└── LICENSE                     # MIT
```

---

## How to add a new adapter

LLM adapters live in `services/agent-runtime/app/adapters/`. Each adapter
implements the `LLMAdapter` abstract base class defined in
`app/adapters/base.py`.

### Step 1: Read the spec

Read `docs/architecture/llm-adapters.md` before writing any code. The
interface, cost tracking contract, streaming protocol, and error handling
expectations are documented there.

### Step 2: Create the adapter module

```python
# services/agent-runtime/app/adapters/myprovider.py

from app.adapters.base import LLMAdapter, LLMRequest, LLMResponse

class MyProviderAdapter(LLMAdapter):
    adapter_id = "myprovider"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        ...

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        ...
```

Key requirements:
- `adapter_id` must be unique across all adapters
- `complete()` must return an `LLMResponse` with `cost_usd` populated
- `stream()` must yield `LLMStreamChunk` and emit a final chunk with full usage
- Raise `AdapterError` (not a raw exception) on provider API failures
- Never log secret keys or full prompts at INFO level

### Step 3: Register the adapter

```python
# services/agent-runtime/app/adapters/registry.py

from app.adapters.myprovider import MyProviderAdapter

ADAPTERS = {
    ...,
    MyProviderAdapter.adapter_id: MyProviderAdapter,
}
```

### Step 4: Add provider config

Add any required environment variables to `.env.example` with a `CHANGE_ME`
placeholder and a comment explaining what the variable does.

### Step 5: Write tests

Add a test file at `services/agent-runtime/tests/adapters/test_myprovider.py`.
Mock the HTTP client; do not make real API calls in CI. Test:
- Successful completion with cost tracking
- Streaming (assert final chunk includes usage)
- Provider error surfaces as `AdapterError`
- Budget exceeded raises `BudgetExceededError`

---

## How to add a new agent role

Agent roles are defined in the database, not in code. To add a new role:

### Option A: Via seed script (development)

Edit `scripts/seed-data.sh` and add a `create_role` call with the new role's
name, title, description, hierarchy level, and daily token budget.

### Option B: Via API (any environment)

```bash
curl -X POST http://localhost/api/v1/companies/{company_id}/org-roles \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "name": "security-engineer",
    "title": "Security Engineer",
    "description": "Monitors for vulnerabilities, reviews PRs for security issues",
    "hierarchy_level": 4,
    "token_budget_daily": 25000
  }'
```

### Wiring the role to an agent

After creating the role, create an agent with that `role_id`. See
`docs/architecture/org-hierarchy-engine.md` for the full agent spawning flow
and the authority/delegation model.

The agent's `personality`, `capabilities.allowed_tools`, and
`heartbeat_config.event_filters` should be tailored to the role's
responsibilities.

---

## Code style

### Python (agent-runtime)

- Formatter and linter: **ruff** (config in `pyproject.toml`)
- Type annotations required on all public functions
- `mypy --strict` must pass (CI enforces this in the lint job)
- Maximum line length: 100 characters

Run before committing:

```bash
cd services/agent-runtime
ruff format .
ruff check --fix .
```

Common ruff rules enforced:
- `E` / `F` — pycodestyle errors, pyflakes
- `I` — isort import ordering
- `UP` — pyupgrade (modernise syntax)
- `B` — flake8-bugbear (likely bugs)
- `SIM` — flake8-simplify

### TypeScript (web-ui)

- Linter: **ESLint** with `eslint-config-next`
- Type checker: **TypeScript** (`tsc --noEmit`)
- No `any` types without a comment explaining why
- Prefer named exports over default exports for components (easier refactoring)

Run before committing:

```bash
cd services/web-ui
npm run lint
npm run type-check
```

### Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add OllamaAdapter with streaming support
fix: correct budget check to run before each LLM call, not once per run
chore: update ruff to 0.5
docs: add LLM adapter implementation guide to CONTRIBUTING
```

Allowed types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`, `ci`

---

## Pull request process

1. **Open an issue first** for any non-trivial change. Use the issue templates
   in `.github/ISSUE_TEMPLATE/`. This saves wasted effort if the approach
   doesn't align with the roadmap.

2. **Branch naming**: `feat/<issue-number>-short-description` or
   `fix/<issue-number>-short-description`.

3. **Keep PRs small**. A PR that touches one component is easier to review
   than one that spans the whole stack. Aim for under 500 lines of diff.

4. **CI must pass** before requesting review. The CI pipeline runs:
   - `ruff check` and `ruff format --check` on the backend
   - ESLint and `tsc --noEmit` on the frontend
   - `pytest` with a live Postgres container
   - `next build` to catch compile-time errors
   - Docker builds for both `agent-runtime` and `web-ui`

5. **One approving review** is required to merge to `main`.

6. **Squash merge** is preferred. The squash commit message should be a
   Conventional Commit that summarises the PR.

7. **No force-pushing to `main`**. If you need to fix the last commit,
   open a new PR.

---

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
