#!/bin/bash
# Check health of all AgentCompany services.
# Exit code is 0 only if every registered service is healthy.
# Run with --plane to also check Plane sidecar services.

set -euo pipefail

echo "=== AgentCompany Health Check ==="

UNHEALTHY=0

check_service() {
    local name=$1
    local url=$2
    if curl -sf "$url" > /dev/null 2>&1; then
        echo "  [OK]   $name"
    else
        echo "  [FAIL] $name (UNHEALTHY)"
        UNHEALTHY=$((UNHEALTHY + 1))
    fi
}

# Core infrastructure
check_service "Traefik"        "http://localhost:8080/ping"
check_service "MinIO"          "http://localhost:9000/minio/health/live"
check_service "Meilisearch"    "http://localhost:7700/health"
check_service "Keycloak"       "http://localhost:8180/health"
check_service "Ollama"         "http://localhost:11434/api/tags"

# Application services
check_service "Agent Runtime"  "http://localhost:8000/health"
check_service "Web UI"         "http://localhost:3000"

# Collaboration services
check_service "Mattermost"     "http://localhost:8065/api/v4/system/ping"
check_service "Outline"        "http://localhost:3100"

# Plane sidecar (only checked when --plane flag is passed, because Plane is
# optional and started via a separate compose overlay)
if [[ "${1:-}" == "--plane" ]]; then
    echo ""
    echo "=== Plane Sidecar Health Check ==="
    check_service "Plane Web"      "http://localhost/plane/"
    check_service "Plane API"      "http://localhost/plane/api/"
    check_service "Plane Space"    "http://localhost/plane/spaces/"
    check_service "Plane Admin"    "http://localhost/plane/god-mode/"
fi

echo ""
if [[ $UNHEALTHY -eq 0 ]]; then
    echo "All services healthy."
    exit 0
else
    echo "$UNHEALTHY service(s) unhealthy."
    exit 1
fi
