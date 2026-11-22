#!/usr/bin/env bash
# =============================================================================
# SentinelFlow — daily PostgreSQL backup (SF-508)
# =============================================================================
# Writes a custom-format pg_dump of the production database, keeps the newest
# KEEP_DAILY dumps on the machine and, once a week, copies the newest dump off
# the machine (Oracle Object Storage, if OCI_BUCKET is set).
#
# Run by deploy/systemd/sentinelflow-backup.timer; can also be run by hand:
#   sudo deploy/backup/pg_backup.sh
#
# Settings (environment, all optional):
#   BACKUP_DIR         /var/backups/sentinelflow
#   KEEP_DAILY         7
#   PG_CONTAINER       sentinelflow-postgres
#   OFFSITE_WEEKDAY    7            (1 = Monday … 7 = Sunday, date +%u)
#   OCI_BUCKET         Object Storage bucket name; empty = no off-site copy
#   OCI_PREFIX         postgres/
#
# No password is needed or stored here: pg_dump runs inside the postgres
# container over its local socket with the container's own POSTGRES_* values.
# =============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/sentinelflow}"
KEEP_DAILY="${KEEP_DAILY:-7}"
PG_CONTAINER="${PG_CONTAINER:-sentinelflow-postgres}"
OFFSITE_WEEKDAY="${OFFSITE_WEEKDAY:-7}"
OCI_BUCKET="${OCI_BUCKET:-}"
OCI_PREFIX="${OCI_PREFIX:-postgres/}"

log() { printf '%s pg_backup: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

umask 077
mkdir -p "$BACKUP_DIR"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BACKUP_DIR/sentinelflow-$stamp.dump"
partial="$target.partial"
trap 'rm -f "$partial"' EXIT

started=$(date +%s)
docker exec "$PG_CONTAINER" sh -c \
  'pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --compress=6' \
  > "$partial"

# A custom-format dump starts with "PGDMP"; anything else is a failed dump.
if [ "$(head -c 5 "$partial")" != "PGDMP" ]; then
  log "ERROR: dump does not look like a pg_dump archive"
  exit 1
fi
mv "$partial" "$target"
trap - EXIT
log "wrote $target ($(du -h "$target" | cut -f1), $(( $(date +%s) - started ))s)"

# Keep the newest KEEP_DAILY dumps.
mapfile -t old < <(ls -1t "$BACKUP_DIR"/sentinelflow-*.dump 2>/dev/null | tail -n +"$((KEEP_DAILY + 1))")
for file in "${old[@]}"; do
  rm -f -- "$file"
  log "removed old backup $file"
done

# Weekly off-site copy.
if [ "$(date +%u)" = "$OFFSITE_WEEKDAY" ]; then
  if [ -z "$OCI_BUCKET" ]; then
    log "WARNING: OCI_BUCKET is not set; weekly off-site copy skipped"
  else
    oci os object put --bucket-name "$OCI_BUCKET" \
      --name "${OCI_PREFIX}$(basename "$target")" --file "$target" --no-overwrite
    log "copied $(basename "$target") to bucket $OCI_BUCKET"
  fi
fi
