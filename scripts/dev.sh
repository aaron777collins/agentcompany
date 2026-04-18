#!/usr/bin/env bash
# dev.sh — start all services in development mode
#
# What this does:
#   1. Starts infrastructure services (postgres, redis, minio, keycloak, etc.)
#      via docker compose with health checks enforced.
#   2. Starts agent-runtime with uvicorn --reload so Python code changes are
#      picked up without a container restart.
#   3. Starts web-ui with `next dev` hot-reload via npm run dev.
#   4. Waits for both services to be ready, then opens the browser.
#
# Prerequisite: run ./scripts/setup.sh at least once to generate secrets and
# pull Docker images.  This script does NOT regenerate secrets.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

info()  { printf '\033[0;34m[dev]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[0;32m[dev]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[0;33m[dev]\033[0m  %s\n' "$*"; }
die()   { printf '\033[0;31m[dev]\033[0m  %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Validate prerequisites
# ---------------------------------------------------------------------------

[[ -f "${ENV_FILE}" ]] || die ".env not found. Run ./scripts/setup.sh first."
command -v docker  >/dev/null 2>&1 || die "docker is not installed."
command -v node    >/dev/null 2>&1 || die "node is not installed. Install Node.js 20+."
command -v npm     >/dev/null 2>&1 || die "npm is not installed."
command -v python3 >/dev/null 2>&1 || die "python3 is not installed."

# Resolve docker compose command
if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
else
    die "docker compose is not available."
fi

# ---------------------------------------------------------------------------
# Load .env so we can reference variables (e.g. port numbers) in this script
# ---------------------------------------------------------------------------

# shellcheck disable=SC1090
set -a
source "${ENV_FILE}"
set +a

TRAEFIK_HTTP_PORT="${TRAEFIK_HTTP_PORT:-80}"

# ---------------------------------------------------------------------------
# Trap: kill background processes on exit
# ---------------------------------------------------------------------------

AGENT_RUNTIME_PID=""
WEB_UI_PID=""

cleanup() {
    info "Shutting down development processes..."
    [[ -n "${AGENT_RUNTIME_PID}" ]] && kill "${AGENT_RUNTIME_PID}" 2>/dev/null || true
    [[ -n "${WEB_UI_PID}" ]] && kill "${WEB_UI_PID}" 2>/dev/null || true
    info "Done. Infrastructure containers are still running — use 'docker compose stop' to stop them."
}

trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# 1. Start infrastructure services (everything except agent-runtime and web-ui)
# ---------------------------------------------------------------------------

info "Starting infrastructure services..."
cd "${REPO_ROOT}"

# Start only the infrastructure services; agent-runtime and web-ui are run
# natively below so changes are picked up without rebuilding Docker images.
${COMPOSE_CMD} up -d \
    postgres redis minio minio-init \
    keycloak meilisearch mattermost outline \
    traefik plane-proxy

ok "Infrastructure services started"

# ---------------------------------------------------------------------------
# 2. Wait for critical infrastructure to be healthy
# ---------------------------------------------------------------------------

info "Waiting for postgres and redis to be healthy..."

wait_healthy() {
    local container="$1"
    local timeout="${2:-120}"
    local elapsed=0
    while [[ ${elapsed} -lt ${timeout} ]]; do
        local status
        status=$(docker inspect --format='{{.State.Health.Status}}' "${container}" 2>/dev/null || echo "missing")
        if [[ "${status}" == "healthy" ]]; then
            ok "${container} is healthy"
            return 0
        fi
        sleep 3
        elapsed=$(( elapsed + 3 ))
    done
    warn "${container} did not become healthy within ${timeout}s — continuing anyway"
}

wait_healthy "agentcompany-postgres" 90
wait_healthy "agentcompany-redis" 60

# ---------------------------------------------------------------------------
# 3. Start agent-runtime with uvicorn --reload
# ---------------------------------------------------------------------------

AGENT_RUNTIME_DIR="${REPO_ROOT}/services/agent-runtime"

if [[ ! -f "${AGENT_RUNTIME_DIR}/app/main.py" ]]; then
    warn "services/agent-runtime/app/main.py not found — skipping agent-runtime."
    warn "Scaffold the service and re-run dev.sh."
else
    info "Starting agent-runtime (uvicorn --reload)..."

    # Activate virtual environment if it exists; otherwise fall back to system
    # pip or warn the user.  The venv is created by setup.sh via `uv venv`.
    VENV="${AGENT_RUNTIME_DIR}/.venv"
    if [[ -d "${VENV}" ]]; then
        PYTHON="${VENV}/bin/python"
        UVICORN="${VENV}/bin/uvicorn"
    elif command -v uvicorn >/dev/null 2>&1; then
        PYTHON="python3"
        UVICORN="uvicorn"
    else
        die "uvicorn not found. Run: cd services/agent-runtime && pip install -r requirements.txt"
    fi

    # Export all variables from .env so uvicorn picks them up.
    # DATABASE_URL and friends are already in the environment from `source .env`.
    (
        cd "${AGENT_RUNTIME_DIR}"
        "${UVICORN}" app.main:app \
            --host 0.0.0.0 \
            --port 8000 \
            --reload \
            --reload-dir app \
            --log-level info
    ) &
    AGENT_RUNTIME_PID=$!
    ok "agent-runtime started (PID ${AGENT_RUNTIME_PID})"
fi

# ---------------------------------------------------------------------------
# 4. Install web-ui dependencies and start Next.js dev server
# ---------------------------------------------------------------------------

WEB_UI_DIR="${REPO_ROOT}/services/web-ui"

if [[ ! -f "${WEB_UI_DIR}/package.json" ]]; then
    warn "services/web-ui/package.json not found — skipping web-ui."
else
    if [[ ! -d "${WEB_UI_DIR}/node_modules" ]]; then
        info "Installing web-ui npm dependencies..."
        (cd "${WEB_UI_DIR}" && npm install)
    fi

    info "Starting web-ui (next dev)..."
    (
        cd "${WEB_UI_DIR}"
        NEXT_PUBLIC_API_URL="http://localhost:${TRAEFIK_HTTP_PORT}/api" \
        NEXT_PUBLIC_KEYCLOAK_URL="http://localhost:${TRAEFIK_HTTP_PORT}/auth" \
        NEXT_PUBLIC_KEYCLOAK_REALM="${KEYCLOAK_REALM:-agentcompany}" \
        NEXT_PUBLIC_KEYCLOAK_CLIENT_ID="${WEB_UI_KEYCLOAK_CLIENT_ID:-agentcompany-web}" \
        npm run dev
    ) &
    WEB_UI_PID=$!
    ok "web-ui started (PID ${WEB_UI_PID})"
fi

# ---------------------------------------------------------------------------
# 5. Wait for services to be ready, then open browser
# ---------------------------------------------------------------------------

info "Waiting for services to accept connections..."

wait_port() {
    local host="$1"
    local port="$2"
    local label="$3"
    local timeout="${4:-60}"
    local elapsed=0
    while [[ ${elapsed} -lt ${timeout} ]]; do
        if curl -sf "http://${host}:${port}" >/dev/null 2>&1; then
            ok "${label} is ready at http://${host}:${port}"
            return 0
        fi
        sleep 2
        elapsed=$(( elapsed + 2 ))
    done
    warn "${label} not responding after ${timeout}s — it may still be starting up"
}

wait_port "localhost" "8000" "agent-runtime" 60
wait_port "localhost" "3000" "web-ui" 60

# ---------------------------------------------------------------------------
# 6. Open browser
# ---------------------------------------------------------------------------

APP_URL="http://localhost:${TRAEFIK_HTTP_PORT}/app"

info "Opening browser at ${APP_URL}"
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${APP_URL}" >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then
    open "${APP_URL}" || true
else
    warn "Cannot open browser automatically. Navigate to: ${APP_URL}"
fi

# ---------------------------------------------------------------------------
# 7. Print summary and wait
# ---------------------------------------------------------------------------

echo ""
echo "============================================================"
echo " AgentCompany — development mode"
echo "============================================================"
echo ""
echo "  Web UI (Next dev):    http://localhost:3000"
echo "  Agent Runtime:        http://localhost:8000/docs"
echo "  Outline (wiki):       http://localhost:${TRAEFIK_HTTP_PORT}/docs"
echo "  Mattermost (chat):    http://localhost:${TRAEFIK_HTTP_PORT}/chat"
echo "  Keycloak (SSO):       http://localhost:${TRAEFIK_HTTP_PORT}/auth"
echo "  Traefik dashboard:    http://localhost:8080/dashboard/"
echo ""
echo "  agent-runtime PID:    ${AGENT_RUNTIME_PID:-not started}"
echo "  web-ui PID:           ${WEB_UI_PID:-not started}"
echo ""
echo "  Press Ctrl-C to stop agent-runtime and web-ui."
echo "  Infrastructure containers will keep running."
echo "  Run 'docker compose stop' to stop those too."
echo ""

# Keep the script alive so the trap can fire on Ctrl-C.
wait
