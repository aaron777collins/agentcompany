#!/usr/bin/env bash
# setup.sh — bootstrap the AgentCompany development environment
#
# What this script does:
#   1. Verifies Docker and docker compose are available
#   2. Copies .env.example → .env if .env does not already exist
#   3. Generates cryptographically random secrets for every CHANGE_ME placeholder
#   4. Creates host directories that must exist before containers start
#   5. Pulls all Docker images (so the first `up` is fast)
#   6. Starts all services with `docker compose up -d`
#   7. Waits for each service to report healthy
#   8. Prints the access URLs

set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
ENV_EXAMPLE="${REPO_ROOT}/.env.example"

info()  { printf '\033[0;34m[INFO]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[0;32m[ OK ]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[0;33m[WARN]\033[0m  %s\n' "$*"; }
die()   { printf '\033[0;31m[FAIL]\033[0m  %s\n' "$*" >&2; exit 1; }

# Generate a hex secret of the requested byte length
gen_secret() {
    local bytes="${1:-32}"
    openssl rand -hex "${bytes}"
}

# Replace a CHANGE_ME marker in .env with a generated secret
replace_secret() {
    local var_name="$1"
    local byte_len="${2:-32}"
    local secret
    secret="$(gen_secret "${byte_len}")"
    # Use a delimiter that will not appear in the secret value
    sed -i "s|^${var_name}=CHANGE_ME$|${var_name}=${secret}|" "${ENV_FILE}"
}

# ---------------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------------

info "Checking prerequisites..."

command -v docker >/dev/null 2>&1 || die "docker is not installed. Install it from https://docs.docker.com/get-docker/"

# Support both `docker compose` (v2 plugin) and `docker-compose` (v1 standalone)
if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
else
    die "docker compose is not available. Install the Docker Compose plugin: https://docs.docker.com/compose/install/"
fi

DOCKER_VERSION=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
ok "Docker ${DOCKER_VERSION} found"
ok "Compose command: ${COMPOSE_CMD}"

# ---------------------------------------------------------------------------
# 2. Copy .env.example → .env
# ---------------------------------------------------------------------------

if [[ ! -f "${ENV_FILE}" ]]; then
    info "Creating .env from .env.example..."
    cp "${ENV_EXAMPLE}" "${ENV_FILE}"
    ok ".env created"
else
    warn ".env already exists — skipping copy (run 'rm .env' and re-run to regenerate)"
fi

# ---------------------------------------------------------------------------
# 3. Generate random secrets
# ---------------------------------------------------------------------------

info "Generating secrets for any remaining CHANGE_ME placeholders..."

# Only generate if the placeholder is still present (idempotent)
if grep -q "^POSTGRES_PASSWORD=CHANGE_ME$" "${ENV_FILE}"; then
    replace_secret "POSTGRES_PASSWORD" 24
    ok "POSTGRES_PASSWORD generated"
fi

if grep -q "^REDIS_PASSWORD=CHANGE_ME$" "${ENV_FILE}"; then
    replace_secret "REDIS_PASSWORD" 24
    ok "REDIS_PASSWORD generated"
fi

if grep -q "^MINIO_ROOT_PASSWORD=CHANGE_ME$" "${ENV_FILE}"; then
    replace_secret "MINIO_ROOT_PASSWORD" 24
    ok "MINIO_ROOT_PASSWORD generated"
fi

if grep -q "^KEYCLOAK_ADMIN_PASSWORD=CHANGE_ME$" "${ENV_FILE}"; then
    replace_secret "KEYCLOAK_ADMIN_PASSWORD" 20
    ok "KEYCLOAK_ADMIN_PASSWORD generated"
fi

if grep -q "^OUTLINE_SECRET_KEY=CHANGE_ME$" "${ENV_FILE}"; then
    replace_secret "OUTLINE_SECRET_KEY" 32
    ok "OUTLINE_SECRET_KEY generated"
fi

if grep -q "^OUTLINE_UTILS_SECRET=CHANGE_ME$" "${ENV_FILE}"; then
    replace_secret "OUTLINE_UTILS_SECRET" 32
    ok "OUTLINE_UTILS_SECRET generated"
fi

if grep -q "^OUTLINE_OIDC_CLIENT_SECRET=CHANGE_ME$" "${ENV_FILE}"; then
    replace_secret "OUTLINE_OIDC_CLIENT_SECRET" 32
    ok "OUTLINE_OIDC_CLIENT_SECRET generated"
fi

if grep -q "^MEILISEARCH_MASTER_KEY=CHANGE_ME$" "${ENV_FILE}"; then
    replace_secret "MEILISEARCH_MASTER_KEY" 32
    ok "MEILISEARCH_MASTER_KEY generated"
fi

if grep -q "^AGENT_RUNTIME_SECRET_KEY=CHANGE_ME$" "${ENV_FILE}"; then
    replace_secret "AGENT_RUNTIME_SECRET_KEY" 32
    ok "AGENT_RUNTIME_SECRET_KEY generated"
fi

if grep -q "^AGENT_RUNTIME_KEYCLOAK_CLIENT_SECRET=CHANGE_ME$" "${ENV_FILE}"; then
    replace_secret "AGENT_RUNTIME_KEYCLOAK_CLIENT_SECRET" 32
    ok "AGENT_RUNTIME_KEYCLOAK_CLIENT_SECRET generated"
fi

# Warn about any remaining CHANGE_ME markers that the script doesn't know how to generate
REMAINING=$(grep "CHANGE_ME" "${ENV_FILE}" || true)
if [[ -n "${REMAINING}" ]]; then
    warn "The following variables still have CHANGE_ME placeholders:"
    echo "${REMAINING}" | sed 's/^/  /'
fi

# ---------------------------------------------------------------------------
# 4. Create required host directories
# ---------------------------------------------------------------------------

info "Creating required host directories..."

mkdir -p \
    "${REPO_ROOT}/docker/traefik" \
    "${REPO_ROOT}/docker/init-scripts" \
    "${REPO_ROOT}/services/agent-runtime" \
    "${REPO_ROOT}/services/web-ui"

ok "Directories ready"

# ---------------------------------------------------------------------------
# 5. Pull Docker images
# ---------------------------------------------------------------------------

info "Pulling Docker images (this may take a few minutes on first run)..."
cd "${REPO_ROOT}"

# Pull only the images for services that have pre-built images.
# Services with `build:` directives (agent-runtime, web-ui) are built below.
$COMPOSE_CMD pull \
    traefik postgres redis minio keycloak \
    outline mattermost meilisearch 2>&1 || warn "Some images failed to pull — will retry during 'up'"

ok "Images pulled"

# ---------------------------------------------------------------------------
# 6. Build custom service images
# ---------------------------------------------------------------------------

# Only build if a Dockerfile exists; the services may not yet be scaffolded
for svc in agent-runtime web-ui; do
    if [[ -f "${REPO_ROOT}/services/${svc}/Dockerfile" ]]; then
        info "Building ${svc}..."
        $COMPOSE_CMD build "${svc}"
        ok "${svc} built"
    else
        warn "services/${svc}/Dockerfile not found — skipping build (service will be absent)"
    fi
done

# ---------------------------------------------------------------------------
# 7. Start services
# ---------------------------------------------------------------------------

info "Starting services..."
cd "${REPO_ROOT}"
$COMPOSE_CMD up -d
ok "docker compose up -d completed"

# ---------------------------------------------------------------------------
# 8. Wait for services to become healthy
# ---------------------------------------------------------------------------

info "Waiting for services to become healthy (timeout: 5 minutes)..."

SERVICES=(postgres redis minio keycloak outline mattermost meilisearch)
TIMEOUT=300
INTERVAL=10
ELAPSED=0

while [[ ${ELAPSED} -lt ${TIMEOUT} ]]; do
    ALL_HEALTHY=true
    for svc in "${SERVICES[@]}"; do
        CONTAINER="agentcompany-${svc}"
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "${CONTAINER}" 2>/dev/null || echo "missing")
        if [[ "${STATUS}" != "healthy" ]]; then
            ALL_HEALTHY=false
            break
        fi
    done

    if ${ALL_HEALTHY}; then
        ok "All core services are healthy"
        break
    fi

    printf '  [%3ds] waiting...\r' "${ELAPSED}"
    sleep "${INTERVAL}"
    ELAPSED=$(( ELAPSED + INTERVAL ))
done

if ! ${ALL_HEALTHY}; then
    warn "Some services may not be healthy yet. Check with: docker compose ps"
fi

# Print final service status
echo ""
info "Service status:"
$COMPOSE_CMD ps

# ---------------------------------------------------------------------------
# 9. Print access URLs
# ---------------------------------------------------------------------------

# Read values from .env for display; fall back to defaults
HTTP_PORT=$(grep "^TRAEFIK_HTTP_PORT=" "${ENV_FILE}" | cut -d= -f2 || echo "80")
DASH_PORT=$(grep "^TRAEFIK_DASHBOARD_PORT=" "${ENV_FILE}" | cut -d= -f2 || echo "8080")

echo ""
echo "============================================================"
echo " AgentCompany is running!"
echo "============================================================"
echo ""
echo "  Web UI:          http://localhost:${HTTP_PORT}/app"
echo "  Agent Runtime:   http://localhost:${HTTP_PORT}/api/docs"
echo "  Outline (wiki):  http://localhost:${HTTP_PORT}/docs"
echo "  Mattermost:      http://localhost:${HTTP_PORT}/chat"
echo "  Keycloak:        http://localhost:${HTTP_PORT}/auth"
echo "  Meilisearch:     http://localhost:${HTTP_PORT}/search"
echo "  Traefik dash:    http://localhost:${DASH_PORT}/dashboard/"
echo "  MinIO console:   http://localhost:${HTTP_PORT}/minio-console"
echo ""
echo "  Logs:   docker compose logs -f"
echo "  Stop:   ./scripts/teardown.sh"
echo ""
