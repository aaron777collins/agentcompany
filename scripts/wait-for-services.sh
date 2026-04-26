#!/usr/bin/env bash
# wait-for-services.sh — block until all AgentCompany services are healthy or timeout
#
# Usage:
#   ./scripts/wait-for-services.sh [max_wait_seconds]
#
# Default timeout is 120 seconds.  Set to 0 to wait forever.

set -euo pipefail

MAX_WAIT="${1:-120}"
ELAPSED=0
INTERVAL=3

# Colour helpers — degrade gracefully when stdout is not a tty
if [[ -t 1 ]]; then
    _BLUE='\033[0;34m'
    _GREEN='\033[0;32m'
    _RED='\033[0;31m'
    _YELLOW='\033[0;33m'
    _RESET='\033[0m'
else
    _BLUE='' _GREEN='' _RED='' _YELLOW='' _RESET=''
fi

info()  { printf "${_BLUE}[wait]${_RESET}  %s\n" "$*"; }
ok()    { printf "${_GREEN}[wait]${_RESET}  %s\n" "$*"; }
warn()  { printf "${_YELLOW}[wait]${_RESET}  %s\n" "$*"; }
fail()  { printf "${_RED}[wait]${_RESET}  %s\n" "$*" >&2; }

# ---------------------------------------------------------------------------
# Service definitions — each entry is a pipe-separated triple:
#   LABEL | DISPLAY_URL | CHECK_COMMAND
#
# The check command must exit 0 when the service is healthy.
# ---------------------------------------------------------------------------

# Keycloak sits behind Traefik at /auth but also listens on 8080 internally.
# We probe the internal port directly so we don't depend on Traefik being up.
declare -a SERVICES=(
    "PostgreSQL|postgres://localhost:5432|_check_postgres localhost 5432"
    "Redis|redis://localhost:6379|_check_redis localhost 6379"
    "Agent Runtime|http://localhost:8000/health|_check_http http://localhost:8000/health"
    "Keycloak|http://localhost:8180/auth/health/ready|_check_http http://localhost:8180/auth/health/ready"
    "Meilisearch|http://localhost:7700/health|_check_http http://localhost:7700/health"
)

# ---------------------------------------------------------------------------
# Check helpers — each sets a non-zero exit code when the service is not ready.
# We probe with multiple tools in order of preference so the script works
# inside minimal containers that may not have all tools installed.
# ---------------------------------------------------------------------------

_have() { command -v "$1" >/dev/null 2>&1; }

_check_postgres() {
    local host="$1" port="$2"
    if _have pg_isready; then
        pg_isready -h "${host}" -p "${port}" -q
    elif _have psql; then
        psql -h "${host}" -p "${port}" -U postgres -c "" >/dev/null 2>&1
    else
        # Fall back to a raw TCP connection check
        _check_tcp "${host}" "${port}"
    fi
}

_check_redis() {
    local host="$1" port="$2"
    if _have redis-cli; then
        # redis-cli ping returns "PONG" when healthy; no auth needed for a
        # plain liveness check (the server accepts PING without auth)
        redis-cli -h "${host}" -p "${port}" ping >/dev/null 2>&1
    else
        _check_tcp "${host}" "${port}"
    fi
}

_check_http() {
    local url="$1"
    if _have curl; then
        curl -sf --max-time 5 "${url}" >/dev/null 2>&1
    elif _have wget; then
        wget -qO- --timeout=5 "${url}" >/dev/null 2>&1
    else
        # Parse host:port from the URL and do a TCP probe
        local host port
        host=$(printf '%s' "${url}" | sed 's|https\?://||' | cut -d: -f1 | cut -d/ -f1)
        port=$(printf '%s' "${url}" | sed 's|https\?://||' | cut -d: -f2 | cut -d/ -f1)
        [[ -z "${port}" ]] && port=80
        _check_tcp "${host}" "${port}"
    fi
}

_check_tcp() {
    local host="$1" port="$2"
    if _have nc; then
        # -z: scan mode (no data), -w: timeout seconds
        nc -z -w 3 "${host}" "${port}" >/dev/null 2>&1
    elif _have bash; then
        # Bash's /dev/tcp pseudo-device works on most Linux systems
        (echo >/dev/tcp/"${host}"/"${port}") >/dev/null 2>&1
    else
        fail "No network tool available (curl, wget, nc, bash /dev/tcp). Cannot check ${host}:${port}."
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Per-service wait loop
# ---------------------------------------------------------------------------

wait_for_service() {
    local label="$1"
    local display_url="$2"
    local check_cmd="$3"
    local svc_elapsed=0

    printf "${_BLUE}[wait]${_RESET}  Waiting for %s (%s)" "${label}" "${display_url}"

    while true; do
        if eval "${check_cmd}" >/dev/null 2>&1; then
            printf "\n"
            ok "${label} is ready"
            return 0
        fi

        # Progress dot
        printf '.'

        sleep "${INTERVAL}"
        svc_elapsed=$(( svc_elapsed + INTERVAL ))

        # Honour the global timeout if set
        if [[ "${MAX_WAIT}" -gt 0 && "${svc_elapsed}" -ge "${MAX_WAIT}" ]]; then
            printf "\n"
            fail "Timed out waiting for ${label} after ${svc_elapsed}s"
            return 1
        fi
    done
}

# ---------------------------------------------------------------------------
# Main — wait for every service; collect failures and report at the end
# ---------------------------------------------------------------------------

info "Waiting for AgentCompany services (timeout=${MAX_WAIT}s, interval=${INTERVAL}s)"
echo ""

FAILED=()

for entry in "${SERVICES[@]}"; do
    IFS='|' read -r label display_url check_cmd <<< "${entry}"
    if ! wait_for_service "${label}" "${display_url}" "${check_cmd}"; then
        FAILED+=("${label}")
    fi
done

echo ""
echo "============================================================"
echo " Service readiness report"
echo "============================================================"
echo ""

ALL_OK=true
for entry in "${SERVICES[@]}"; do
    IFS='|' read -r label display_url check_cmd <<< "${entry}"
    # Check again for the final status line (cheap — services are already up)
    if eval "${check_cmd}" >/dev/null 2>&1; then
        printf "  ${_GREEN}OK${_RESET}   %s\n" "${label}"
    else
        printf "  ${_RED}FAIL${_RESET} %s\n" "${label}"
        ALL_OK=false
    fi
done

echo ""

if [[ "${ALL_OK}" == "true" ]]; then
    ok "All services are healthy"
    exit 0
else
    fail "One or more services did not become healthy within ${MAX_WAIT}s"
    fail "Failing services: ${FAILED[*]:-unknown}"
    exit 1
fi
