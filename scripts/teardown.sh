#!/usr/bin/env bash
# teardown.sh — gracefully shut down the AgentCompany environment
#
# Usage:
#   ./scripts/teardown.sh            # stop containers, preserve volumes
#   ./scripts/teardown.sh --purge    # stop containers AND delete all volumes + images

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

info()  { printf '\033[0;34m[INFO]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[0;32m[ OK ]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[0;33m[WARN]\033[0m  %s\n' "$*"; }
die()   { printf '\033[0;31m[FAIL]\033[0m  %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Resolve docker compose command
# ---------------------------------------------------------------------------

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
else
    die "docker compose is not available"
fi

cd "${REPO_ROOT}"

# ---------------------------------------------------------------------------
# Parse flags
# ---------------------------------------------------------------------------

PURGE=false

for arg in "$@"; do
    case "${arg}" in
        --purge)
            PURGE=true
            ;;
        --help|-h)
            echo "Usage: $0 [--purge]"
            echo ""
            echo "  --purge   Remove all volumes and locally built images after stopping."
            echo "            WARNING: All data will be lost. This cannot be undone."
            exit 0
            ;;
        *)
            die "Unknown argument: ${arg}. Use --help for usage."
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Confirm destructive operations
# ---------------------------------------------------------------------------

if ${PURGE}; then
    echo ""
    warn "You are about to PERMANENTLY DELETE all data volumes and locally built images."
    warn "This includes all database data, MinIO objects, and search indexes."
    echo ""
    read -r -p "Type 'yes-delete-everything' to confirm: " CONFIRM
    if [[ "${CONFIRM}" != "yes-delete-everything" ]]; then
        info "Aborted — no changes made."
        exit 0
    fi
fi

# ---------------------------------------------------------------------------
# Stop containers
# ---------------------------------------------------------------------------

info "Stopping services..."
$COMPOSE_CMD down --timeout 30
ok "Services stopped"

# ---------------------------------------------------------------------------
# Purge volumes and images (optional)
# ---------------------------------------------------------------------------

if ${PURGE}; then
    info "Removing volumes..."
    # Remove named volumes declared in docker-compose.yml
    VOLUMES=(
        agentcompany_postgres_data
        agentcompany_redis_data
        agentcompany_minio_data
        agentcompany_meilisearch_data
        agentcompany_mattermost_config
        agentcompany_mattermost_data
        agentcompany_mattermost_logs
        agentcompany_mattermost_plugins
        agentcompany_mattermost_client_plugins
        agentcompany_traefik_certs
    )

    for vol in "${VOLUMES[@]}"; do
        if docker volume inspect "${vol}" >/dev/null 2>&1; then
            docker volume rm "${vol}" && ok "Removed volume: ${vol}"
        else
            warn "Volume not found (already removed?): ${vol}"
        fi
    done

    info "Removing locally built images..."
    for img in agentcompany/agent-runtime:latest agentcompany/web-ui:latest; do
        if docker image inspect "${img}" >/dev/null 2>&1; then
            docker rmi "${img}" && ok "Removed image: ${img}"
        else
            warn "Image not found (already removed?): ${img}"
        fi
    done

    ok "Purge complete"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
if ${PURGE}; then
    info "AgentCompany has been stopped and all data has been deleted."
    info "Run './scripts/setup.sh' to start fresh."
else
    info "AgentCompany has been stopped. Data volumes are preserved."
    info "Run '${COMPOSE_CMD} up -d' to restart, or './scripts/teardown.sh --purge' to delete data."
fi
echo ""
