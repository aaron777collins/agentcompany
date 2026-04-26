#!/usr/bin/env bash
# backup.sh — create a timestamped backup of all AgentCompany persistent data.
#
# What this script backs up:
#   1. PostgreSQL — pg_dump for each application database
#   2. MinIO — all bucket contents via `mc mirror`
#
# Output: a single tar.gz in BACKUP_DIR (default: ./backups/)
#   backups/agentcompany-backup-YYYY-MM-DDTHH-MM-SS.tar.gz
#
# Restore: ./scripts/restore.sh <path-to-backup.tar.gz>
#
# Prerequisites:
#   - The AgentCompany stack must be running (docker compose up)
#   - .env must exist and be sourced (or POSTGRES_PASSWORD / MINIO_ROOT_PASSWORD
#     must be set in the environment)

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
# Load environment
# ---------------------------------------------------------------------------

# Source .env so we pick up secrets without requiring the caller to export them.
# We intentionally do not export all variables to avoid polluting child processes.
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
# Backup directory setup
# ---------------------------------------------------------------------------

TIMESTAMP="$(date -u +%Y-%m-%dT%H-%M-%S)"
BACKUP_DIR="${REPO_ROOT}/backups"
BACKUP_WORK="${BACKUP_DIR}/.work-${TIMESTAMP}"
BACKUP_FILE="${BACKUP_DIR}/agentcompany-backup-${TIMESTAMP}.tar.gz"

mkdir -p "${BACKUP_WORK}/postgres" "${BACKUP_WORK}/minio"

# Cleanup the work directory on exit (success or failure)
cleanup() {
    rm -rf "${BACKUP_WORK}"
}
trap cleanup EXIT

info "Backup started: ${TIMESTAMP}"
info "Output file:    ${BACKUP_FILE}"

# ---------------------------------------------------------------------------
# 1. PostgreSQL dumps
# ---------------------------------------------------------------------------

# Databases to back up. If Plane is not running the `plane` dump will still be
# attempted; pg_dump will exit non-zero if the database doesn't exist, but we
# treat that as a warning rather than a hard failure.
PG_DATABASES=(agentcompany_core outline mattermost keycloak plane)

info "Dumping PostgreSQL databases..."

for db in "${PG_DATABASES[@]}"; do
    DUMP_FILE="${BACKUP_WORK}/postgres/${db}.sql.gz"
    info "  Dumping ${db}..."

    # pg_dump runs inside the postgres container; we stream the output through
    # gzip on the host to avoid writing an uncompressed file inside the container.
    if docker exec agentcompany-postgres \
        pg_dump \
            --username="${POSTGRES_USER}" \
            --no-password \
            --format=plain \
            --clean \
            --if-exists \
            "${db}" 2>/dev/null \
        | gzip > "${DUMP_FILE}"; then
        ok "  ${db} -> postgres/${db}.sql.gz"
    else
        # Database may not exist (e.g. plane when not running the sidecar)
        warn "  Skipping ${db} (database not found or pg_dump failed)"
        rm -f "${DUMP_FILE}"
    fi
done

# ---------------------------------------------------------------------------
# 2. MinIO mirror
# ---------------------------------------------------------------------------

info "Mirroring MinIO buckets..."

# Run mc inside a temporary container sharing the host Docker network so it
# can reach the minio container by service name.
if docker run --rm \
    --network agentcompany_internal \
    --volume "${BACKUP_WORK}/minio:/minio-backup" \
    minio/mc:RELEASE.2024-01-16T16-07-38Z \
    /bin/sh -c "
        mc alias set local http://minio:9000 '${MINIO_ROOT_USER}' '${MINIO_ROOT_PASSWORD}' &&
        mc mirror --overwrite local /minio-backup
    " 2>&1; then
    ok "MinIO buckets mirrored to minio/"
else
    warn "MinIO mirror failed — MinIO may not be running. Continuing without MinIO backup."
fi

# ---------------------------------------------------------------------------
# 3. Write a manifest so the restore script knows what's inside
# ---------------------------------------------------------------------------

cat > "${BACKUP_WORK}/MANIFEST.txt" <<EOF
AgentCompany Backup Manifest
Created:   $(date -u)
Timestamp: ${TIMESTAMP}
Host:      $(hostname)

Contents:
  postgres/   — pg_dump plain-text SQL (gzipped) for each database
  minio/      — mc mirror of all MinIO buckets
  MANIFEST.txt

Restore:
  ./scripts/restore.sh ${BACKUP_FILE##*/}
  (or provide the full path)
EOF

# ---------------------------------------------------------------------------
# 4. Pack everything into a tar.gz
# ---------------------------------------------------------------------------

info "Creating archive..."

# Archive the work directory but strip the leading ".work-<timestamp>/" prefix
# so the extracted layout is simply postgres/ minio/ MANIFEST.txt
tar -czf "${BACKUP_FILE}" \
    -C "${BACKUP_WORK}" \
    .

ok "Backup complete: ${BACKUP_FILE}"
info "Size: $(du -sh "${BACKUP_FILE}" | cut -f1)"
