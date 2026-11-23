#!/usr/bin/env bash
# =============================================================================
# SentinelFlow — restore a PostgreSQL backup (SF-508)
# =============================================================================
# Usage:
#   deploy/backup/pg_restore.sh <dump-file>                 # restore test
#   deploy/backup/pg_restore.sh <dump-file> --into <db>     # into a NEW database
#   deploy/backup/pg_restore.sh <dump-file> --replace       # REAL restore
#
# Default (restore test): creates an empty database `sentinelflow_restore_test`,
# restores into it, prints row counts of the main tables and the elapsed time,
# then drops it. The production database is not touched.
#
# --into restores into a database that must not exist yet; it never drops
# anything and refuses the production database (use --replace for that).
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

prod_db="$(docker exec "$PG_CONTAINER" sh -c 'printf %s "$POSTGRES_DB"')"
[ -n "$prod_db" ] || { echo "cannot read POSTGRES_DB from $PG_CONTAINER" >&2; exit 1; }

if [ "$mode" = replace ]; then
  target="$prod_db"
  if docker ps --format '{{.Names}}' | grep -qx sentinelflow-api; then
    echo "sentinelflow-api is running; stop it before --replace" >&2
    exit 1
  fi
  read -r -p "Replace database '$target' with $(basename "$dump")? Type the database name: " answer
  [ "$answer" = "$target" ] || { echo "aborted"; exit 1; }
fi

case "$target" in *[!a-z0-9_]*|"") echo "invalid database name: $target" >&2; exit 2 ;; esac

if [ "$mode" != replace ]; then
  # Only --replace may touch the production database (it checks the API is
  # stopped and asks for the name). postgres/template* are never targets.
  case "$target" in
    "$prod_db"|postgres|template0|template1)
      echo "refusing to restore into '$target'; use --replace to restore the production database" >&2
      exit 1 ;;
  esac
fi

if [ "$mode" = into ]; then
  exists="$(docker exec -i "$PG_CONTAINER" sh -c 'psql -At --username="$POSTGRES_USER" --dbname=postgres'     <<<"SELECT 1 FROM pg_database WHERE datname = '$target';")"
  if [ -n "$exists" ]; then
    echo "database '$target' already exists; --into only creates a new database (pick another name or drop it yourself)" >&2
    exit 1
  fi
fi

started=$(date +%s)
if [ "$mode" != into ]; then
  psql_c "DROP DATABASE IF EXISTS \"$target\" WITH (FORCE);"
fi
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
