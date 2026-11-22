#!/usr/bin/env bash
# =============================================================================
# SentinelFlow — restore a PostgreSQL backup (SF-508)
# =============================================================================
# Usage:
#   deploy/backup/pg_restore.sh <dump-file>                 # restore test
#   deploy/backup/pg_restore.sh <dump-file> --into <db>     # into another DB
#   deploy/backup/pg_restore.sh <dump-file> --replace       # REAL restore
#
# Default (restore test): creates an empty database `sentinelflow_restore_test`,
# restores into it, prints row counts of the main tables and the elapsed time,
# then drops it. The production database is not touched.
#
# --replace drops and recreates the production database from the dump. Stop the
# API first (docker compose ... stop api) and take a fresh backup; see
# deploy/README.md "Yedekten dönme".
# =============================================================================
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-sentinelflow-postgres}"

usage() { sed -n '5,8p' "$0"; exit 2; }
[ $# -ge 1 ] || usage
dump="$1"; shift
[ -f "$dump" ] || { echo "no such file: $dump" >&2; exit 2; }

mode=test
target=sentinelflow_restore_test
case "${1:-}" in
  "") ;;
  --into) [ -n "${2:-}" ] || usage; mode=into; target="$2" ;;
  --replace) mode=replace; target="" ;;
  *) usage ;;
esac

psql_c() {  # run SQL against the maintenance database `postgres`
  docker exec -i "$PG_CONTAINER" sh -c 'psql -v ON_ERROR_STOP=1 -q --username="$POSTGRES_USER" --dbname=postgres' <<<"$1"
}

if [ "$mode" = replace ]; then
  target="$(docker exec "$PG_CONTAINER" sh -c 'printf %s "$POSTGRES_DB"')"
  if docker ps --format '{{.Names}}' | grep -qx sentinelflow-api; then
    echo "sentinelflow-api is running; stop it before --replace" >&2
    exit 1
  fi
  read -r -p "Replace database '$target' with $(basename "$dump")? Type the database name: " answer
  [ "$answer" = "$target" ] || { echo "aborted"; exit 1; }
fi

case "$target" in *[!a-z0-9_]*|"") echo "invalid database name: $target" >&2; exit 2 ;; esac

started=$(date +%s)
psql_c "DROP DATABASE IF EXISTS \"$target\" WITH (FORCE);"
psql_c "CREATE DATABASE \"$target\";"
docker exec -i "$PG_CONTAINER" sh -c \
  "pg_restore --username=\"\$POSTGRES_USER\" --dbname=\"$target\" --no-owner --exit-on-error" \
  < "$dump"
elapsed=$(( $(date +%s) - started ))

echo "restored $(basename "$dump") into '$target' in ${elapsed}s"
docker exec -i "$PG_CONTAINER" sh -c "psql -q --username=\"\$POSTGRES_USER\" --dbname=\"$target\"" <<'SQL'
SELECT relname AS table, n_live_tup AS rows
FROM pg_stat_user_tables ORDER BY relname;
SQL
# pg_stat counters fill in lazily; exact counts for the tables that matter:
docker exec -i "$PG_CONTAINER" sh -c "psql -q -At --username=\"\$POSTGRES_USER\" --dbname=\"$target\"" <<'SQL'
SELECT 'users=' || count(*) FROM users;
SELECT 'alerts=' || count(*) FROM alerts;
SELECT 'cases=' || count(*) FROM cases;
SQL

if [ "$mode" = test ]; then
  psql_c "DROP DATABASE \"$target\";"
  echo "dropped restore-test database '$target'"
fi
