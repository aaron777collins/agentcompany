#!/usr/bin/env bash
# ollama-setup.sh — pull required models into the Ollama service on first boot.
#
# Designed to be idempotent: each model is only pulled if it is not already
# present in the local model registry, so re-running this script is safe.
#
# Usage (from the repo root):
#   ./scripts/ollama-setup.sh
#
# The script waits up to WAIT_TIMEOUT seconds for Ollama to become reachable
# before giving up so it can be called immediately after `docker compose up`.

set -euo pipefail

OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
WAIT_TIMEOUT="${OLLAMA_WAIT_TIMEOUT:-120}"

# Models to pull.
# - gemma3: primary agent reasoning model.
# - nomic-embed-text: compact embedding model used for vector search.
MODELS_TO_PULL=(
    "gemma3"
    "nomic-embed-text"
)

info()  { printf '\033[0;34m[INFO]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[0;32m[ OK ]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[0;33m[WARN]\033[0m  %s\n' "$*"; }
die()   { printf '\033[0;31m[FAIL]\033[0m  %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Wait for Ollama to become reachable
# ---------------------------------------------------------------------------

wait_for_ollama() {
    local elapsed=0
    local interval=5

    info "Waiting for Ollama at ${OLLAMA_BASE_URL} (timeout: ${WAIT_TIMEOUT}s)..."
    while [[ ${elapsed} -lt ${WAIT_TIMEOUT} ]]; do
        if curl -sf "${OLLAMA_BASE_URL}/api/tags" >/dev/null 2>&1; then
            ok "Ollama is reachable"
            return 0
        fi
        printf '  [%3ds] waiting for Ollama...\r' "${elapsed}"
        sleep "${interval}"
        elapsed=$(( elapsed + interval ))
    done

    die "Ollama did not become reachable within ${WAIT_TIMEOUT} seconds. Check: docker compose logs ollama"
}

# ---------------------------------------------------------------------------
# Check whether a model is already present in the local registry
# ---------------------------------------------------------------------------

model_exists() {
    local model="$1"
    # The /api/tags response is a JSON object with a "models" array.
    # Each element has a "name" field like "gemma3:latest".
    # Strip the tag for a prefix match so "gemma3" matches "gemma3:latest".
    curl -sf "${OLLAMA_BASE_URL}/api/tags" \
        | grep -q "\"name\":\"${model}" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Pull a model via the Ollama HTTP API
# ---------------------------------------------------------------------------

pull_model() {
    local model="$1"

    info "Pulling model: ${model}"
    # Stream the pull progress to stdout so the user can see download progress.
    # The API returns newline-delimited JSON; we print each status line.
    curl -sf -X POST "${OLLAMA_BASE_URL}/api/pull" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${model}\", \"stream\": true}" \
        | while IFS= read -r line; do
            status=$(printf '%s' "${line}" | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || true)
            [[ -n "${status}" ]] && printf '  %s\r' "${status}"
        done

    # Print a newline after the stream ends
    echo ""
    ok "Model pulled: ${model}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

wait_for_ollama

for model in "${MODELS_TO_PULL[@]}"; do
    if model_exists "${model}"; then
        ok "Model already present, skipping pull: ${model}"
    else
        pull_model "${model}"
    fi
done

echo ""
echo "============================================================"
echo " Ollama setup complete"
echo "============================================================"
echo ""
echo "  Models available:"
curl -sf "${OLLAMA_BASE_URL}/api/tags" \
    | grep -o '"name":"[^"]*"' \
    | sed 's/"name":"//;s/"//' \
    | sed 's/^/    /'
echo ""
