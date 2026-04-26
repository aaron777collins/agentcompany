#!/usr/bin/env bash
# seed-data.sh — populate AgentCompany with sample data for development
#
# Calls the agent-runtime REST API to create:
#   1. A sample company ("Acme Corp")
#   2. Default org roles with proper hierarchy (CEO → CTO/CFO → PM → Dev/Designer/QA)
#   3. Sample agents for CEO and Developer roles
#   4. Sample tasks on the Acme Corp board
#   5. Meilisearch indexes for agents and tasks
#
# Auth:
#   Uses Keycloak client_credentials grant.  The agentcompany-api client must
#   exist in the realm and have the service-accounts-enabled + org:admin roles
#   mapped.  See docs/handoffs/seed-script-handoff.md for details.
#
# Requirements:
#   - All services must be running (./scripts/setup.sh or ./scripts/dev.sh)
#   - curl and jq must be installed
#
# Usage:
#   ./scripts/seed-data.sh
#   ./scripts/seed-data.sh --base-url http://staging.example.com
#   SKIP_WAIT=1 ./scripts/seed-data.sh   # skip service readiness check

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPTS_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

if [[ -t 1 ]]; then
    _BLUE='\033[0;34m' _GREEN='\033[0;32m' _RED='\033[0;31m' _YELLOW='\033[0;33m' _RESET='\033[0m'
else
    _BLUE='' _GREEN='' _RED='' _YELLOW='' _RESET=''
fi

info()  { printf "${_BLUE}[seed]${_RESET}  %s\n" "$*"; }
ok()    { printf "${_GREEN}[seed]${_RESET}  %s\n" "$*"; }
warn()  { printf "${_YELLOW}[seed]${_RESET}  %s\n" "$*"; }
die()   { printf "${_RED}[seed]${_RESET}  %s\n" "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

BASE_URL="http://localhost"

for arg in "$@"; do
    case "${arg}" in
        --base-url=*)   BASE_URL="${arg#*=}" ;;
        --base-url)     shift; BASE_URL="$1" ;;
        --help|-h)
            echo "Usage: $0 [--base-url <url>]"
            echo ""
            echo "  --base-url   Base URL of the running platform (default: http://localhost)"
            echo ""
            echo "Environment variables:"
            echo "  SKIP_WAIT=1             Skip the service readiness wait"
            echo "  KEYCLOAK_CLIENT_SECRET  Override the client secret used for auth"
            exit 0
            ;;
        *)  die "Unknown argument: ${arg}" ;;
    esac
done

API_BASE="${BASE_URL}/api/v1"
KEYCLOAK_BASE="${BASE_URL}/auth"
MEILI_BASE="${BASE_URL}/search"

# Keycloak realm defaults — override via env if your realm is configured differently
KEYCLOAK_REALM="${KEYCLOAK_REALM:-agentcompany}"
KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:-agentcompany-api}"
KEYCLOAK_CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-agentcompany-api-secret}"
MEILISEARCH_MASTER_KEY="${MEILISEARCH_MASTER_KEY:-}"

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

command -v curl >/dev/null 2>&1 || die "curl is required but not installed."
command -v jq   >/dev/null 2>&1 || die "jq is required but not installed."

# Load .env if present — non-fatal because the script may be run without one
# in CI where env vars are injected directly.
if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "${ENV_FILE}"
    set +a
else
    warn ".env not found — relying on environment variables."
fi

# Re-apply after sourcing .env so explicit CLI env wins over the file
KEYCLOAK_CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-agentcompany-api-secret}"
MEILISEARCH_MASTER_KEY="${MEILISEARCH_MASTER_KEY:-}"

# ---------------------------------------------------------------------------
# Step 0: Wait for services
# ---------------------------------------------------------------------------

if [[ "${SKIP_WAIT:-0}" != "1" ]]; then
    info "Waiting for services to be healthy..."
    if [[ -x "${SCRIPTS_DIR}/wait-for-services.sh" ]]; then
        "${SCRIPTS_DIR}/wait-for-services.sh" 120 || die "Services did not become healthy in time."
    else
        warn "wait-for-services.sh not found or not executable — skipping readiness check."
    fi
else
    info "Skipping service readiness check (SKIP_WAIT=1)."
fi

# ---------------------------------------------------------------------------
# Auth helpers
#
# Every mutating request to agent-runtime requires a Bearer token issued by
# Keycloak.  We use the client_credentials grant so this script can run
# headlessly without a human logging in.
#
# The service account for agentcompany-api MUST have the org:admin realm role
# mapped in Keycloak.  See docs/handoffs/seed-script-handoff.md for setup.
# ---------------------------------------------------------------------------

TOKEN=""

acquire_token() {
    local response http_code body

    response=$(curl -s -w "\n%{http_code}" \
        -X POST "${KEYCLOAK_BASE}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "client_id=${KEYCLOAK_CLIENT_ID}" \
        -d "client_secret=${KEYCLOAK_CLIENT_SECRET}" \
        -d "grant_type=client_credentials")

    http_code=$(printf '%s' "${response}" | tail -n1)
    body=$(printf '%s' "${response}" | head -n -1)

    if [[ "${http_code}" != "200" ]]; then
        warn "Keycloak token request failed (HTTP ${http_code})."
        warn "The seed script will attempt unauthenticated requests — most will fail."
        warn "Ensure the '${KEYCLOAK_CLIENT_ID}' client exists in realm '${KEYCLOAK_REALM}'"
        warn "with service accounts enabled and the 'org:admin' realm role assigned."
        TOKEN=""
        return 0
    fi

    TOKEN=$(printf '%s' "${body}" | jq -r '.access_token // empty')

    if [[ -z "${TOKEN}" ]]; then
        warn "Keycloak returned 200 but no access_token was present in the response."
        TOKEN=""
    else
        ok "Acquired Keycloak token (client=${KEYCLOAK_CLIENT_ID}, realm=${KEYCLOAK_REALM})"
    fi
}

# ---------------------------------------------------------------------------
# API request helpers
#
# Responses from agent-runtime follow the envelope:
#   { "data": { ... }, "meta": { ... } }
#
# api_post / api_get return the inner .data object on success, or empty string
# on failure so callers can test with [[ -n "${result}" ]].
#
# We build curl argument arrays rather than using eval so that JWT tokens
# (which contain '/', '+', '=' characters) are never word-split or
# re-interpreted as shell syntax.
# ---------------------------------------------------------------------------

# Populate an array with the Authorization header args when a token is present.
# Usage: _auth_args; then reference "${AUTH_ARGS[@]}"
_build_auth_args() {
    AUTH_ARGS=()
    [[ -n "${TOKEN}" ]] && AUTH_ARGS=("-H" "Authorization: Bearer ${TOKEN}")
}

api_post() {
    local path="$1"
    local body="$2"
    local response http_code body_text

    _build_auth_args
    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        "${AUTH_ARGS[@]}" \
        -d "${body}" \
        "${API_BASE}${path}")

    http_code=$(printf '%s' "${response}" | tail -n1)
    body_text=$(printf '%s' "${response}" | head -n -1)

    if [[ "${http_code}" == "409" ]]; then
        # Conflict = already exists; return a sentinel so callers can fetch the
        # existing record instead of treating this as a hard error.
        printf '%s' "__CONFLICT__"
        return 0
    fi

    if [[ "${http_code}" -ge 400 ]]; then
        warn "POST ${path} → HTTP ${http_code}: ${body_text}"
        printf ''
        return 0
    fi

    # Unwrap the { "data": ... } envelope
    printf '%s' "${body_text}" | jq -c '.data // .'
}

api_get() {
    local path="$1"
    local response http_code body_text

    _build_auth_args
    response=$(curl -s -w "\n%{http_code}" \
        "${AUTH_ARGS[@]}" \
        "${API_BASE}${path}")

    http_code=$(printf '%s' "${response}" | tail -n1)
    body_text=$(printf '%s' "${response}" | head -n -1)

    if [[ "${http_code}" -ge 400 ]]; then
        warn "GET ${path} → HTTP ${http_code}"
        printf ''
        return 0
    fi

    printf '%s' "${body_text}"
}

# ---------------------------------------------------------------------------
# Idempotency helper — fetch an existing resource by a filter query param
# Returns the first item's .id from the list response, or empty string.
# ---------------------------------------------------------------------------

find_existing_id() {
    local path="$1"       # e.g. /roles
    local filter="$2"     # e.g. company_id=<id>&slug=ceo
    local result

    result=$(api_get "${path}?${filter}")
    printf '%s' "${result}" | jq -r '.items[0].id // empty' 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Step 1: Acquire auth token
# ---------------------------------------------------------------------------

info "Acquiring Keycloak service-account token..."
acquire_token

# ---------------------------------------------------------------------------
# Step 2: Create company "Acme Corp"
#
# CompanyCreate schema:
#   name (str), slug (str, pattern: ^[a-z0-9]+(?:-[a-z0-9]+)*$),
#   description (str|None), settings (CompanySettings)
#
# CompanySettings: timezone, default_language, human_approval_required
# (No token_budget fields — those live on Role, not Company.)
# ---------------------------------------------------------------------------

info "Creating company 'Acme Corp'..."

COMPANY_ID=""

COMPANY_BODY=$(jq -n '{
    "name": "Acme Corp",
    "slug": "acme",
    "description": "Sample company created by the seed script for development purposes.",
    "settings": {
        "timezone": "UTC",
        "default_language": "en",
        "human_approval_required": ["budget_increase", "agent_delete"]
    }
}')

COMPANY_RESPONSE=$(api_post "/companies" "${COMPANY_BODY}")

if [[ "${COMPANY_RESPONSE}" == "__CONFLICT__" ]]; then
    warn "Company 'acme' already exists — fetching existing record."
    EXISTING=$(api_get "/companies")
    COMPANY_ID=$(printf '%s' "${EXISTING}" | jq -r '.items[] | select(.slug == "acme") | .id' 2>/dev/null | head -1 || true)
    [[ -n "${COMPANY_ID}" ]] && ok "Using existing company: ${COMPANY_ID}" || die "Could not resolve existing company ID."
elif [[ -n "${COMPANY_RESPONSE}" ]]; then
    COMPANY_ID=$(printf '%s' "${COMPANY_RESPONSE}" | jq -r '.id // empty')
    [[ -n "${COMPANY_ID}" ]] && ok "Company created: ${COMPANY_ID}" || die "Company response contained no ID."
else
    die "Company creation failed — check Keycloak auth and agent-runtime logs."
fi

# ---------------------------------------------------------------------------
# Step 3: Create org roles
#
# RoleCreate schema:
#   name (str), slug (str), company_id (str), description (str|None),
#   level (int >= 0), reports_to_role_id (str|None),
#   permissions (list[str]), tool_access (dict), max_headcount (int >= 1),
#   headcount_type ("agent"|"human"|"mixed")
#
# Hierarchy: CEO (1) → CTO (2), CFO (2) → PM (3) → Dev/Designer/QA (4)
# We must create parents before children because the API validates
# reports_to_role_id references immediately on write.
# ---------------------------------------------------------------------------

info "Creating org roles..."

declare -A ROLE_IDS  # keyed by slug

create_role() {
    local slug="$1"
    local name="$2"
    local description="$3"
    local level="$4"
    local reports_to_slug="${5:-}"   # empty = top of hierarchy
    local permissions_json="${6:-[]}"
    local tool_access_json="${7:-{}}"
    local max_headcount="${8:-1}"
    local headcount_type="${9:-agent}"

    # Resolve reports_to_role_id from earlier-created roles
    local reports_to_id="null"
    if [[ -n "${reports_to_slug}" && -n "${ROLE_IDS[${reports_to_slug}]:-}" ]]; then
        reports_to_id="\"${ROLE_IDS[${reports_to_slug}]}\""
    fi

    local body
    body=$(jq -n \
        --arg name "${name}" \
        --arg slug "${slug}" \
        --arg company_id "${COMPANY_ID}" \
        --arg description "${description}" \
        --argjson level "${level}" \
        --argjson reports_to "${reports_to_id}" \
        --argjson permissions "${permissions_json}" \
        --argjson tool_access "${tool_access_json}" \
        --argjson max_headcount "${max_headcount}" \
        --arg headcount_type "${headcount_type}" \
    '{
        name: $name,
        slug: $slug,
        company_id: $company_id,
        description: $description,
        level: $level,
        reports_to_role_id: $reports_to,
        permissions: $permissions,
        tool_access: $tool_access,
        max_headcount: $max_headcount,
        headcount_type: $headcount_type
    }')

    local response role_id
    response=$(api_post "/roles" "${body}")

    if [[ "${response}" == "__CONFLICT__" ]]; then
        warn "  Role '${slug}' already exists — looking up ID."
        role_id=$(find_existing_id "/roles" "company_id=${COMPANY_ID}")
        # find_existing_id returns first role; search specifically by slug from list
        local all_roles
        all_roles=$(api_get "/roles?company_id=${COMPANY_ID}&limit=100")
        role_id=$(printf '%s' "${all_roles}" | jq -r --arg s "${slug}" '.items[] | select(.slug == $s) | .id' 2>/dev/null | head -1 || true)
    else
        role_id=$(printf '%s' "${response}" | jq -r '.id // empty' 2>/dev/null || true)
    fi

    if [[ -n "${role_id}" ]]; then
        ROLE_IDS["${slug}"]="${role_id}"
        ok "  Role '${name}' (level ${level}): ${role_id}"
    else
        warn "  Could not create or find role '${slug}' — dependent roles may fail."
    fi
}

# Level 1 — top of the hierarchy; no reports_to
create_role "ceo" "Chief Executive Officer" \
    "Company leader — strategic direction and final authority." \
    1 "" \
    '["company:read","company:write","budget:approve","agent:manage"]' \
    '{"search":true,"project":true,"chat":true,"documentation":true,"analytics":true}' \
    1 "agent"

# Level 2 — report to CEO
create_role "cto" "Chief Technology Officer" \
    "Technology direction and engineering leadership." \
    2 "ceo" \
    '["company:read","budget:read","agent:manage","code:review"]' \
    '{"search":true,"project":true,"chat":true,"documentation":true,"code":true}' \
    1 "agent"

create_role "cfo" "Chief Financial Officer" \
    "Financial planning, reporting, and budget approval." \
    2 "ceo" \
    '["company:read","budget:read","budget:write","analytics:read"]' \
    '{"search":true,"analytics":true,"documentation":true,"chat":true}' \
    1 "agent"

# Level 3 — reports to CTO
create_role "pm" "Product Manager" \
    "Product roadmap, backlog prioritisation, and delivery." \
    3 "cto" \
    '["project:read","project:write","task:manage","agent:read"]' \
    '{"search":true,"project":true,"chat":true,"documentation":true}' \
    1 "mixed"

# Level 4 — all report to PM
create_role "developer" "Software Developer" \
    "Feature development, bug fixes, and code review." \
    4 "pm" \
    '["project:read","task:read","task:write","code:read","code:write"]' \
    '{"search":true,"project":true,"chat":true,"documentation":true,"code":true}' \
    5 "agent"

create_role "designer" "UX/UI Designer" \
    "User research, wireframes, and visual design." \
    4 "pm" \
    '["project:read","task:read","task:write","design:read","design:write"]' \
    '{"search":true,"project":true,"chat":true,"documentation":true}' \
    3 "agent"

create_role "qa" "QA Engineer" \
    "Test planning, automated tests, and release sign-off." \
    4 "pm" \
    '["project:read","task:read","task:write","code:read"]' \
    '{"search":true,"project":true,"chat":true,"documentation":true,"code":true}' \
    3 "agent"

ok "All org roles created"

# ---------------------------------------------------------------------------
# Step 4: Create agents
#
# AgentCreate schema:
#   name (str), slug (str), company_id (str), role_id (str|None),
#   llm_config (LLMConfig), system_prompt (str|None),
#   capabilities (list[str]), tool_permissions (dict),
#   token_budget_daily (int|None), token_budget_monthly (int|None)
#
# LLMConfig: provider ("anthropic"|"openai"|"ollama"), model (str),
#            temperature (0.0-2.0), max_tokens (1-200000)
# ---------------------------------------------------------------------------

info "Creating agents..."

CEO_AGENT_ID=""
DEV_AGENT_ID=""

create_agent() {
    local name="$1"
    local slug="$2"
    local role_slug="$3"
    local provider="$4"
    local model="$5"
    local system_prompt="$6"
    local capabilities_json="$7"
    local token_budget_daily="$8"
    local token_budget_monthly="$9"

    local role_id="null"
    if [[ -n "${role_slug}" && -n "${ROLE_IDS[${role_slug}]:-}" ]]; then
        role_id="\"${ROLE_IDS[${role_slug}]}\""
    fi

    local body
    body=$(jq -n \
        --arg name "${name}" \
        --arg slug "${slug}" \
        --arg company_id "${COMPANY_ID}" \
        --argjson role_id "${role_id}" \
        --arg provider "${provider}" \
        --arg model "${model}" \
        --arg system_prompt "${system_prompt}" \
        --argjson capabilities "${capabilities_json}" \
        --argjson token_budget_daily "${token_budget_daily}" \
        --argjson token_budget_monthly "${token_budget_monthly}" \
    '{
        name: $name,
        slug: $slug,
        company_id: $company_id,
        role_id: $role_id,
        llm_config: {
            provider: $provider,
            model: $model,
            temperature: 0.7,
            max_tokens: 4096
        },
        system_prompt: $system_prompt,
        capabilities: $capabilities,
        tool_permissions: {},
        token_budget_daily: $token_budget_daily,
        token_budget_monthly: $token_budget_monthly
    }')

    local response agent_id
    response=$(api_post "/agents" "${body}")

    if [[ "${response}" == "__CONFLICT__" ]]; then
        warn "  Agent '${slug}' already exists."
        local all_agents
        all_agents=$(api_get "/agents?company_id=${COMPANY_ID}&limit=100")
        agent_id=$(printf '%s' "${all_agents}" | jq -r --arg s "${slug}" '.items[] | select(.slug == $s) | .id' 2>/dev/null | head -1 || true)
    else
        agent_id=$(printf '%s' "${response}" | jq -r '.id // empty' 2>/dev/null || true)
    fi

    if [[ -n "${agent_id}" ]]; then
        ok "  Agent '${name}': ${agent_id}"
        printf '%s' "${agent_id}"
    else
        warn "  Agent '${name}' creation failed — skipping."
        printf ''
    fi
}

CEO_AGENT_ID=$(create_agent \
    "Alex (CEO Agent)" \
    "alex-ceo" \
    "ceo" \
    "anthropic" \
    "claude-opus-4-5" \
    "You are Alex, the CEO of Acme Corp. You set strategic direction, approve budgets, and communicate the company vision. Be concise, data-driven, and decisive." \
    '["search","project","chat","documentation","analytics"]' \
    100000 \
    3000000)

DEV_AGENT_ID=$(create_agent \
    "Dev Bot (Developer Agent)" \
    "dev-bot" \
    "developer" \
    "anthropic" \
    "claude-sonnet-4-6" \
    "You are Dev Bot, a software developer at Acme Corp. You handle code review, write features, triage bugs, and keep the codebase clean. Be technical, precise, and pragmatic." \
    '["search","project","chat","documentation","code"]' \
    50000 \
    1500000)

ok "All agents created"

# ---------------------------------------------------------------------------
# Step 5: Create sample tasks
#
# TaskCreate schema:
#   title (str), description (str|None), company_id (str),
#   assigned_to (str|None), assigned_type ("agent"|"human"|None),
#   priority ("urgent"|"high"|"medium"|"low"), due_at (datetime|None),
#   tags (list[str]), parent_task_id (str|None),
#   sync_to_plane (bool), metadata (dict)
#
# Tasks are created with status="backlog" by default (set by the model).
# "todo" requires a PATCH/PUT after creation — TaskCreate has no status field.
# ---------------------------------------------------------------------------

info "Creating sample tasks..."

create_task() {
    local title="$1"
    local description="$2"
    local priority="$3"
    local tags_json="$4"
    local assigned_to="${5:-null}"
    local assigned_type="${6:-null}"

    # Wrap optional assignment — null stays null in JSON
    local assigned_to_json assigned_type_json
    if [[ "${assigned_to}" == "null" ]]; then
        assigned_to_json="null"
        assigned_type_json="null"
    else
        assigned_to_json="\"${assigned_to}\""
        assigned_type_json="\"${assigned_type}\""
    fi

    local body
    body=$(jq -n \
        --arg title "${title}" \
        --arg description "${description}" \
        --arg company_id "${COMPANY_ID}" \
        --arg priority "${priority}" \
        --argjson tags "${tags_json}" \
        --argjson assigned_to "${assigned_to_json}" \
        --argjson assigned_type "${assigned_type_json}" \
    '{
        title: $title,
        description: $description,
        company_id: $company_id,
        priority: $priority,
        tags: $tags,
        assigned_to: $assigned_to,
        assigned_type: $assigned_type,
        sync_to_plane: false,
        metadata: {}
    }')

    local response task_id
    response=$(api_post "/tasks" "${body}")

    # Tasks have no unique slug constraint so conflicts don't occur; any failure
    # is surfaced as a warning and we continue seeding the remaining tasks.
    task_id=$(printf '%s' "${response}" | jq -r '.id // empty' 2>/dev/null || true)

    if [[ -n "${task_id}" ]]; then
        ok "  Task '${title}': ${task_id}"
    else
        warn "  Task '${title}' creation failed — continuing."
    fi
}

# Unassigned backlog tasks
create_task \
    "Set up project repository" \
    "Initialise the Git repository, configure branch protection rules, and set up the CI pipeline skeleton." \
    "high" \
    '["infra","backend"]'

create_task \
    "Write API documentation" \
    "Document all /api/v1 endpoints in the OpenAPI spec with examples, error codes, and field descriptions." \
    "medium" \
    '["documentation","backend"]'

create_task \
    "Create landing page" \
    "Design and implement the public marketing landing page for agentcompany.io." \
    "low" \
    '["frontend","design"]'

# Tasks pre-assigned to agents (if agents were created)
if [[ -n "${DEV_AGENT_ID}" ]]; then
    create_task \
        "Design system architecture" \
        "Produce an architecture decision record (ADR) for the agent-runtime service, covering DB schema, Redis usage, and event bus topology." \
        "high" \
        '["architecture","backend"]' \
        "${DEV_AGENT_ID}" "agent"

    create_task \
        "Implement user authentication" \
        "Wire up Keycloak OIDC login flow in the Next.js web-ui, including token refresh and protected route guards." \
        "high" \
        '["auth","frontend"]' \
        "${DEV_AGENT_ID}" "agent"
else
    create_task \
        "Design system architecture" \
        "Produce an architecture decision record (ADR) for the agent-runtime service, covering DB schema, Redis usage, and event bus topology." \
        "high" \
        '["architecture","backend"]'

    create_task \
        "Implement user authentication" \
        "Wire up Keycloak OIDC login flow in the Next.js web-ui, including token refresh and protected route guards." \
        "high" \
        '["auth","frontend"]'
fi

ok "All tasks created"

# ---------------------------------------------------------------------------
# Step 6: Create Meilisearch indexes
#
# Meilisearch's PUT /indexes is idempotent — safe to call every run.
# The index names mirror what agent-runtime's search service expects.
# ---------------------------------------------------------------------------

info "Creating Meilisearch indexes..."

_meili_create_index() {
    local uid="$1"
    local primary_key="${2:-id}"

    # Build auth args as an array — safe with arbitrary key material
    local meili_auth=()
    [[ -n "${MEILISEARCH_MASTER_KEY}" ]] && meili_auth=("-H" "Authorization: Bearer ${MEILISEARCH_MASTER_KEY}")

    local response http_code body_text
    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        "${meili_auth[@]}" \
        -d "$(jq -n --arg uid "${uid}" --arg pk "${primary_key}" '{"uid":$uid,"primaryKey":$pk}')" \
        "${MEILI_BASE}/indexes")

    http_code=$(printf '%s' "${response}" | tail -n1)
    body_text=$(printf '%s' "${response}" | head -n -1)

    if [[ "${http_code}" == "201" || "${http_code}" == "202" ]]; then
        ok "  Meilisearch index '${uid}' created."
    elif [[ "${http_code}" == "409" ]]; then
        ok "  Meilisearch index '${uid}' already exists."
    else
        warn "  Could not create Meilisearch index '${uid}' (HTTP ${http_code}): ${body_text}"
    fi
}

_meili_create_index "agents" "id"
_meili_create_index "tasks"  "id"

ok "Meilisearch indexes ready"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "============================================================"
echo " Seed data summary"
echo "============================================================"
echo ""
printf "  %-22s %s\n" "Company ID:"       "${COMPANY_ID:-not created}"
printf "  %-22s %s\n" "CEO Agent ID:"     "${CEO_AGENT_ID:-not created}"
printf "  %-22s %s\n" "Dev Agent ID:"     "${DEV_AGENT_ID:-not created}"
echo ""
echo "  Org roles:  CEO, CTO, CFO, PM, Developer, Designer, QA"
echo "  Tasks:      5 sample tasks created (backlog)"
echo ""
echo "  Platform:   ${BASE_URL}/app"
echo "  API docs:   ${BASE_URL}/api/docs"
echo ""
