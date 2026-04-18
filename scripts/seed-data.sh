#!/usr/bin/env bash
# seed-data.sh — populate AgentCompany with sample data for development
#
# This script calls the agent-runtime REST API to create:
#   1. A sample company
#   2. Default org roles (CEO, CTO, CFO, PM, Developer, Designer, QA)
#   3. Sample agents for CEO and Developer roles
#   4. A sample project board (via Plane API stub)
#   5. A welcome document (via Outline API)
#   6. A general chat channel and welcome message (via Mattermost API)
#
# Requirements:
#   - All services must be running (./scripts/setup.sh or ./scripts/dev.sh)
#   - curl and jq must be installed
#
# Usage:
#   ./scripts/seed-data.sh
#   ./scripts/seed-data.sh --base-url http://staging.example.com

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

info()  { printf '\033[0;34m[seed]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[0;32m[seed]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[0;33m[seed]\033[0m  %s\n' "$*"; }
die()   { printf '\033[0;31m[seed]\033[0m  %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

BASE_URL="http://localhost"
AGENT_API_URL=""
MM_URL=""

for arg in "$@"; do
    case "${arg}" in
        --base-url=*)
            BASE_URL="${arg#*=}"
            ;;
        --base-url)
            shift
            BASE_URL="$1"
            ;;
        --help|-h)
            echo "Usage: $0 [--base-url <url>]"
            echo ""
            echo "  --base-url   Base URL of the running platform (default: http://localhost)"
            exit 0
            ;;
        *)
            die "Unknown argument: ${arg}"
            ;;
    esac
done

AGENT_API_URL="${BASE_URL}/api/v1"
MM_URL="${BASE_URL}/chat/api/v4"

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

command -v curl >/dev/null 2>&1 || die "curl is required but not installed."
command -v jq   >/dev/null 2>&1 || die "jq is required but not installed."

[[ -f "${ENV_FILE}" ]] || die ".env not found. Run ./scripts/setup.sh first."

# shellcheck disable=SC1090
set -a
source "${ENV_FILE}"
set +a

# ---------------------------------------------------------------------------
# Helper: POST to agent-runtime API with JSON body
# Returns the parsed response body and fails loud if HTTP status >= 400.
# ---------------------------------------------------------------------------

api_post() {
    local path="$1"
    local body="$2"
    local response http_code body_text

    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "${body}" \
        "${AGENT_API_URL}${path}")

    http_code=$(printf '%s' "${response}" | tail -n1)
    body_text=$(printf '%s' "${response}" | head -n -1)

    if [[ "${http_code}" -ge 400 ]]; then
        warn "POST ${path} returned HTTP ${http_code}: ${body_text}"
        echo ""
    else
        echo "${body_text}"
    fi
}

api_get() {
    local path="$1"
    curl -s "${AGENT_API_URL}${path}"
}

mm_post() {
    local path="$1"
    local body="$2"
    local token="${3:-}"
    local auth_header=""
    [[ -n "${token}" ]] && auth_header="-H \"Authorization: Bearer ${token}\""

    curl -s -X POST \
        -H "Content-Type: application/json" \
        ${token:+-H "Authorization: Bearer ${token}"} \
        -d "${body}" \
        "${MM_URL}${path}"
}

# ---------------------------------------------------------------------------
# Check that the agent-runtime API is reachable before proceeding
# ---------------------------------------------------------------------------

info "Checking agent-runtime API at ${AGENT_API_URL}..."

HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/health" 2>/dev/null || echo "000")

if [[ "${HEALTH_STATUS}" != "200" ]]; then
    die "agent-runtime is not responding at ${BASE_URL}/api/health (got HTTP ${HEALTH_STATUS}).\nMake sure the platform is running: ./scripts/setup.sh"
fi

ok "Agent Runtime is healthy"

# ---------------------------------------------------------------------------
# 1. Create sample company
# ---------------------------------------------------------------------------

info "Creating sample company 'Acme Corp'..."

COMPANY_RESPONSE=$(api_post "/companies" '{
  "name": "Acme Corp",
  "slug": "acme",
  "description": "Sample company created by the seed script for development purposes",
  "settings": {
    "max_agents": 20,
    "token_budget_daily": 500000,
    "token_budget_monthly": 10000000
  }
}')

if [[ -n "${COMPANY_RESPONSE}" ]]; then
    COMPANY_ID=$(echo "${COMPANY_RESPONSE}" | jq -r '.id // empty')
    ok "Company created: ${COMPANY_ID}"
else
    warn "Company creation failed or already exists — attempting to fetch existing..."
    COMPANY_ID=$(api_get "/companies?slug=acme" | jq -r '.[0].id // empty')
    [[ -n "${COMPANY_ID}" ]] && ok "Using existing company: ${COMPANY_ID}" || die "Could not create or find company."
fi

# ---------------------------------------------------------------------------
# 2. Create default org roles
# ---------------------------------------------------------------------------

info "Creating default org roles..."

declare -A ROLE_IDS

create_role() {
    local name="$1"
    local title="$2"
    local description="$3"
    local level="$4"
    local budget="$5"

    local response
    response=$(api_post "/companies/${COMPANY_ID}/org-roles" \
        "$(jq -n \
            --arg name "${name}" \
            --arg title "${title}" \
            --arg desc "${description}" \
            --argjson level "${level}" \
            --argjson budget "${budget}" \
        '{
            name: $name,
            title: $title,
            description: $desc,
            hierarchy_level: $level,
            token_budget_daily: $budget
        }')")

    local role_id
    role_id=$(echo "${response}" | jq -r '.id // empty')
    if [[ -n "${role_id}" ]]; then
        ROLE_IDS["${name}"]="${role_id}"
        ok "  Role '${title}' created: ${role_id}"
    else
        warn "  Role '${title}' may already exist"
    fi
}

create_role "ceo"        "Chief Executive Officer"   "Company leader — strategic direction and final authority"  1  100000
create_role "cto"        "Chief Technology Officer"  "Technology direction and engineering leadership"            2  80000
create_role "cfo"        "Chief Financial Officer"   "Financial planning, reporting, and budget approval"        2  60000
create_role "pm"         "Product Manager"           "Product roadmap, backlog prioritisation, and delivery"     3  40000
create_role "developer"  "Software Developer"        "Feature development, bug fixes, and code review"           4  30000
create_role "designer"   "UX/UI Designer"            "User research, wireframes, and visual design"              4  25000
create_role "qa"         "QA Engineer"               "Test planning, automated tests, and release sign-off"      4  20000

ok "All org roles created"

# ---------------------------------------------------------------------------
# 3. Create sample agents for CEO and Developer roles
# ---------------------------------------------------------------------------

info "Creating sample agents..."

CEO_ROLE_ID="${ROLE_IDS[ceo]:-}"
DEV_ROLE_ID="${ROLE_IDS[developer]:-}"

if [[ -n "${CEO_ROLE_ID}" ]]; then
    CEO_RESPONSE=$(api_post "/companies/${COMPANY_ID}/agents" \
        "$(jq -n \
            --arg role_id "${CEO_ROLE_ID}" \
        '{
            name: "Alex (CEO Agent)",
            description: "Strategic decision-maker. Reviews key metrics, prioritises company goals, and communicates direction to the team.",
            role_id: $role_id,
            llm_adapter: "anthropic",
            llm_model: "claude-opus-4-5",
            personality: {
                tone: "confident and visionary",
                communication_style: "concise executive summaries",
                decision_style: "data-driven with strategic perspective"
            },
            capabilities: {
                allowed_tools: ["search", "project", "chat", "documentation", "analytics"],
                max_steps_per_run: 20
            },
            heartbeat_config: {
                mode: "scheduled",
                cron_expression: "0 9 * * 1-5"
            }
        }')")

    CEO_AGENT_ID=$(echo "${CEO_RESPONSE}" | jq -r '.id // empty')
    [[ -n "${CEO_AGENT_ID}" ]] && ok "CEO agent created: ${CEO_AGENT_ID}" || warn "CEO agent creation failed"
fi

if [[ -n "${DEV_ROLE_ID}" ]]; then
    DEV_RESPONSE=$(api_post "/companies/${COMPANY_ID}/agents" \
        "$(jq -n \
            --arg role_id "${DEV_ROLE_ID}" \
        '{
            name: "Dev Bot (Developer Agent)",
            description: "Handles code review requests, creates boilerplate, and triages incoming bug reports.",
            role_id: $role_id,
            llm_adapter: "anthropic",
            llm_model: "claude-sonnet-4-6",
            personality: {
                tone: "technical and precise",
                communication_style: "code snippets and bullet points",
                decision_style: "pragmatic engineering trade-offs"
            },
            capabilities: {
                allowed_tools: ["search", "project", "chat", "documentation", "code"],
                max_steps_per_run: 30
            },
            heartbeat_config: {
                mode: "event",
                event_filters: ["plane.issue.assigned", "plane.issue.comment"]
            }
        }')")

    DEV_AGENT_ID=$(echo "${DEV_RESPONSE}" | jq -r '.id // empty')
    [[ -n "${DEV_AGENT_ID}" ]] && ok "Developer agent created: ${DEV_AGENT_ID}" || warn "Developer agent creation failed"
fi

# ---------------------------------------------------------------------------
# 4. Create a sample project board via the project-management API stub
# ---------------------------------------------------------------------------

info "Creating sample project board..."

PROJECT_RESPONSE=$(api_post "/companies/${COMPANY_ID}/projects" '{
    "name": "AgentCompany Platform v1",
    "identifier": "AC",
    "description": "Core platform development — agent runtime, web UI, integrations",
    "network": "public",
    "labels": ["backend", "frontend", "infra", "ai"],
    "default_state": "backlog"
}')

PROJECT_ID=$(echo "${PROJECT_RESPONSE}" | jq -r '.id // empty')

if [[ -n "${PROJECT_ID}" ]]; then
    ok "Project created: ${PROJECT_ID}"

    # Create starter issues
    create_issue() {
        local title="$1"
        local description="$2"
        local priority="$3"
        local label="$4"

        api_post "/companies/${COMPANY_ID}/projects/${PROJECT_ID}/issues" \
            "$(jq -n \
                --arg title "${title}" \
                --arg desc "${description}" \
                --arg priority "${priority}" \
                --arg label "${label}" \
            '{
                title: $title,
                description: $desc,
                priority: $priority,
                label_ids: [$label],
                state: "backlog"
            }')" >/dev/null

        ok "  Issue created: ${title}"
    }

    create_issue "Set up agent-runtime FastAPI scaffolding" \
        "Create the FastAPI app structure, health endpoint, and basic middleware." \
        "urgent" "backend"

    create_issue "Implement AnthropicAdapter" \
        "Build the LLM adapter for Claude. Include streaming and cost tracking per llm-adapters.md." \
        "high" "ai"

    create_issue "Scaffold Next.js web-ui" \
        "Create pages: dashboard, agent list, agent detail with live run feed." \
        "high" "frontend"

    create_issue "Mattermost ChatTool integration" \
        "Implement the ChatTool that lets agents post and read messages via Mattermost API v4." \
        "medium" "backend"

    create_issue "Write Keycloak realm setup runbook" \
        "Document the manual steps to configure realm clients after first Keycloak boot." \
        "medium" "infra"
else
    warn "Project creation failed — skipping issue creation"
fi

# ---------------------------------------------------------------------------
# 5. Create a welcome document in Outline
# ---------------------------------------------------------------------------

info "Creating welcome document in Outline..."

OUTLINE_API="${BASE_URL}/docs/api"
OUTLINE_TOKEN=""

# We need an Outline API token.  In development Outline doesn't expose a
# bootstrap token via env, so we attempt to create one via the internal API.
# If it fails we skip silently — the document can be created manually.

OUTLINE_TOKEN_RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"token": "'"${OUTLINE_UTILS_SECRET:-}"'"}' \
    "${OUTLINE_API}/auth.info" 2>/dev/null || echo "{}")

OUTLINE_TOKEN=$(echo "${OUTLINE_TOKEN_RESPONSE}" | jq -r '.data.token // empty' 2>/dev/null || echo "")

if [[ -n "${OUTLINE_TOKEN}" ]]; then
    # Find or create a "General" collection
    COLLECTION_RESPONSE=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${OUTLINE_TOKEN}" \
        -d '{"name": "General", "color": "#4E5C6E", "sharing": true}' \
        "${OUTLINE_API}/collections.create" 2>/dev/null || echo "{}")

    COLLECTION_ID=$(echo "${COLLECTION_RESPONSE}" | jq -r '.data.id // empty' 2>/dev/null || echo "")

    if [[ -n "${COLLECTION_ID}" ]]; then
        curl -s -X POST \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer ${OUTLINE_TOKEN}" \
            -d "$(jq -n \
                --arg cid "${COLLECTION_ID}" \
            '{
                collectionId: $cid,
                title: "Welcome to AgentCompany",
                text: "# Welcome to AgentCompany\n\nThis wiki is the shared knowledge base for your AI-powered organisation.\n\n## What is AgentCompany?\n\nAgentCompany is a platform that runs AI agents in the roles of your organisational chart. Each agent has a persona, a set of tools, and a budget. They read tasks from your project board, communicate via chat, and write documentation here.\n\n## Getting started\n\n1. **Explore the agent dashboard** → `/app`\n2. **Check the project board** → tasks are synced from Plane\n3. **Chat with the team** → Mattermost at `/chat`\n4. **Read the architecture docs** → `docs/architecture/`\n\n## Key contacts\n\n| Role | Agent | Email |\n|---|---|---|\n| CEO | Alex (CEO Agent) | Responds to @ceo in chat |\n| Developer | Dev Bot | Responds to code review requests |\n\n## Contributing to this wiki\n\nAny team member (human or agent) can create documents. Use the sidebar to navigate collections. Pin important documents to the top of their collection.\n"
            }')" \
            "${OUTLINE_API}/documents.create" >/dev/null 2>&1 && ok "Welcome document created in Outline" || warn "Could not create Outline document"
    fi
else
    warn "Skipping Outline document creation — could not obtain API token"
fi

# ---------------------------------------------------------------------------
# 6. Create general chat channel and post welcome message in Mattermost
# ---------------------------------------------------------------------------

info "Setting up Mattermost general channel..."

# Authenticate as admin to get a session token
MM_AUTH_RESPONSE=$(curl -s -i -X POST \
    -H "Content-Type: application/json" \
    -d '{"login_id": "admin", "password": "admin"}' \
    "${MM_URL}/users/login" 2>/dev/null || echo "")

MM_TOKEN=$(echo "${MM_AUTH_RESPONSE}" | grep -i '^Token:' | tr -d '[:space:]' | cut -d: -f2 || echo "")

if [[ -z "${MM_TOKEN}" ]]; then
    warn "Could not authenticate to Mattermost — skipping chat setup"
    warn "Default admin credentials may not be configured yet."
else
    ok "Authenticated to Mattermost"

    # Get or create a team
    TEAM_RESPONSE=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${MM_TOKEN}" \
        -d '{"name": "agentcompany", "display_name": "AgentCompany", "type": "O"}' \
        "${MM_URL}/teams" 2>/dev/null || echo "{}")

    TEAM_ID=$(echo "${TEAM_RESPONSE}" | jq -r '.id // empty' 2>/dev/null || echo "")

    # If team creation failed (already exists), look it up
    if [[ -z "${TEAM_ID}" ]]; then
        TEAM_ID=$(curl -s \
            -H "Authorization: Bearer ${MM_TOKEN}" \
            "${MM_URL}/teams/name/agentcompany" | jq -r '.id // empty')
    fi

    if [[ -n "${TEAM_ID}" ]]; then
        ok "Team ID: ${TEAM_ID}"

        # Ensure the Town Square (general) channel exists — it's auto-created
        # with every new team, so just look it up.
        CHANNEL_ID=$(curl -s \
            -H "Authorization: Bearer ${MM_TOKEN}" \
            "${MM_URL}/teams/${TEAM_ID}/channels/name/town-square" | jq -r '.id // empty')

        if [[ -n "${CHANNEL_ID}" ]]; then
            ok "Town Square channel: ${CHANNEL_ID}"

            # Post welcome message
            POST_RESPONSE=$(curl -s -X POST \
                -H "Content-Type: application/json" \
                -H "Authorization: Bearer ${MM_TOKEN}" \
                -d "$(jq -n \
                    --arg channel_id "${CHANNEL_ID}" \
                '{
                    channel_id: $channel_id,
                    message: ":wave: **Welcome to AgentCompany!**\n\nThis is the general channel for the whole team — humans and agents alike.\n\n**Quick links:**\n- Web UI: http://localhost/app\n- Wiki: http://localhost/docs\n- Project board: http://localhost/plane\n- API docs: http://localhost/api/docs\n\nAI agents will post status updates here. You can also @mention any agent role to get their attention.\n\n_This message was posted by the seed script._"
                }')" \
                "${MM_URL}/posts" 2>/dev/null || echo "{}")

            POST_ID=$(echo "${POST_RESPONSE}" | jq -r '.id // empty')
            [[ -n "${POST_ID}" ]] && ok "Welcome message posted to Town Square" || warn "Could not post welcome message"
        else
            warn "Town Square channel not found — Mattermost team may still be initialising"
        fi
    else
        warn "Could not create or find Mattermost team"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "============================================================"
echo " Seed data summary"
echo "============================================================"
echo ""
echo "  Company ID:      ${COMPANY_ID:-not created}"
echo "  CEO Agent ID:    ${CEO_AGENT_ID:-not created}"
echo "  Dev Agent ID:    ${DEV_AGENT_ID:-not created}"
echo "  Project ID:      ${PROJECT_ID:-not created}"
echo ""
echo "  Org roles:       CEO, CTO, CFO, PM, Developer, Designer, QA"
echo ""
echo "  Platform:        ${BASE_URL}/app"
echo ""
