#!/usr/bin/env bash
# restore.sh — restore AgentCompany from a backup produced by backup.sh.
#
# Usage:
#   ./scripts/restore.sh <path-to-backup.tar.gz>
#   ./scripts/restore.sh backups/agentcompany-backup-2026-04-18T12-00-00.tar.gz
#
# What this script restores:
#   1. PostgreSQL — psql restores each .sql.gz dump found in postgres/
#   2. MinIO — mc mirror restores all bucket contents from minio/
#
# WARNING: This is DESTRUCTIVE. All existing data in the target databases
# and MinIO buckets will be replaced by the backup. Stop any active sessions
# and confirm before proceeding.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info()  { printf '\033[0;34m[INFO]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[0;32m[ OK ]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[0;33m[WARN]\033[0m  %s\n' "$*"; }
die()   { printf '\033[0;31m[FAIL]\033[0m  %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

BACKUP_FILE="${1:-}"

if [[ -z "${BACKUP_FILE}" ]]; then
    die "Usage: $0 <path-to-backup.tar.gz>"
fi

# Resolve relative paths from repo root so operators can pass just the filename
if [[ ! -f "${BACKUP_FILE}" ]] && [[ -f "${REPO_ROOT}/backups/${BACKUP_FILE}" ]]; then
    BACKUP_FILE="${REPO_ROOT}/backups/${BACKUP_FILE}"
fi

[[ -f "${BACKUP_FILE}" ]] || die "Backup file not found: ${BACKUP_FILE}"

# ---------------------------------------------------------------------------
# Confirmation prompt — this operation is destructive
# ---------------------------------------------------------------------------

echo ""
warn "DESTRUCTIVE OPERATION"
echo "  Restoring from: ${BACKUP_FILE}"
echo "  This will OVERWRITE all PostgreSQL databases and MinIO buckets."
echo "  All services should be stopped or in maintenance mode before proceeding."
echo ""
read -rp "Type 'yes' to confirm: " CONFIRM
[[ "${CONFIRM}" == "yes" ]] || die "Restore cancelled."

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------

if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck source=/dev/null
    set -o allexport; source "${ENV_FILE}"; set +o allexport
else
    warn ".env not found — relying on environment variables already set"
fi

POSTGRES_USER="${POSTGRES_USER:-agentcompany}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set (check your .env)}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-agentcompany}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD must be set (check your .env)}"

# ---------------------------------------------------------------------------
# Extract the archive to a temp directory
# ---------------------------------------------------------------------------

RESTORE_WORK="$(mktemp -d)"

cleanup() {
    rm -rf "${RESTORE_WORK}"
}
trap cleanup EXIT

info "Extracting backup..."
tar -xzf "${BACKUP_FILE}" -C "${RESTORE_WORK}"

# Show the manifest if present
if [[ -f "${RESTORE_WORK}/MANIFEST.txt" ]]; then
    echo ""
    cat "${RESTORE_WORK}/MANIFEST.txt"
    echo ""
fi

# ---------------------------------------------------------------------------
# 1. PostgreSQL restore
# ---------------------------------------------------------------------------

PG_DUMP_DIR="${RESTORE_WORK}/postgres"

if [[ -d "${PG_DUMP_DIR}" ]]; then
    info "Restoring PostgreSQL databases..."

    for dump_file in "${PG_DUMP_DIR}"/*.sql.gz; do
        [[ -f "${dump_file}" ]] || continue
        db="$(basename "${dump_file}" .sql.gz)"
        info "  Restoring ${db}..."

        # Pipe the compressed dump straight into psql inside the container.
        # The dump was produced with --clean --if-exists so it will DROP and
        # recreate all objects, which is why the database must already exist.
        if gunzip -c "${dump_file}" | docker exec -i agentcompany-postgres \
            psql \
            --username="${POSTGRES_USER}" \
            --dbname="${db}" \
            --quiet \
            2>&1; then
            ok "  ${db} restored"
        else
            warn "  Failed to restore ${db} — database may not exist yet. Run setup.sh first."
        fi
    done
else
    warn "No postgres/ directory found in backup — skipping PostgreSQL restore"
fi

# ---------------------------------------------------------------------------
# 2. MinIO restore
# ---------------------------------------------------------------------------

MINIO_BACKUP_DIR="${RESTORE_WORK}/minio"

if [[ -d "${MINIO_BACKUP_DIR}" ]]; then
    info "Restoring MinIO buckets..."

    if docker run --rm \
        --network agentcompany_internal \
        --volume "${MINIO_BACKUP_DIR}:/minio-backup:ro" \
        minio/mc:RELEASE.2024-01-16T16-07-38Z \
        /bin/sh -c "
            mc alias set local http://minio:9000 '${MINIO_ROOT_USER}' '${MINIO_ROOT_PASSWORD}' &&
            mc mirror --overwrite /minio-backup local
        " 2>&1; then
        ok "MinIO buckets restored"
    else
        warn "MinIO restore failed — MinIO may not be running."
    fi
else
    warn "No minio/ directory found in backup — skipping MinIO restore"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

echo ""
ok "Restore complete."
info "Restart all services to pick up the restored data:"
info "  docker compose restart"
