#!/usr/bin/env bash
# =============================================================================
# SentinelFlow — health, disk and memory check (SF-509)
# =============================================================================
# Run every 5 minutes by deploy/systemd/sentinelflow-healthcheck.timer.
# Checks, through the public HTTPS address (so certificate and proxy are
# covered too):
#   * GET /api/v1/system/health answers 200 with "status": "healthy"
#   * GET /api/v1/ml/models is protected (401 without a token) — the API is
#     reachable through the proxy and auth is on
# and on the machine:
#   * root filesystem usage below DISK_MAX_PERCENT
#   * available memory above MEM_MIN_PERCENT
#
# Results go to the journal (journalctl -u sentinelflow-healthcheck). On a
# failure, if ALERT_WEBHOOK_URL is set, a short JSON message is POSTed to it
# (e.g. a team chat incoming webhook or an ntfy topic). The message holds no
# secrets. This is the on-machine half; an external uptime monitor pointed
# at the same health URL covers the machine itself being down.
#
# Environment:
#   SENTINELFLOW_DOMAIN   required
#   ALERT_WEBHOOK_URL     optional
#   DISK_MAX_PERCENT      85
#   MEM_MIN_PERCENT       10
# Exit code: 0 all good, 1 at least one check failed.
# =============================================================================
set -uo pipefail

: "${SENTINELFLOW_DOMAIN:?SENTINELFLOW_DOMAIN is required}"
DISK_MAX_PERCENT="${DISK_MAX_PERCENT:-85}"
MEM_MIN_PERCENT="${MEM_MIN_PERCENT:-10}"
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"
BASE="${HEALTHCHECK_BASE_URL:-https://$SENTINELFLOW_DOMAIN}"

failures=()

health="$(curl -fsS --max-time 10 "$BASE/api/v1/system/health" 2>&1)" \
  || failures+=("health endpoint unreachable: ${health:0:120}")
if [ ${#failures[@]} -eq 0 ] && ! grep -q '"status":"healthy"' <<<"${health// /}"; then
  failures+=("health degraded: ${health:0:200}")
fi

code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/api/v1/ml/models")"
[ "$code" = "401" ] || failures+=("/api/v1/ml/models without token returned $code, expected 401")

disk="$(df --output=pcent / | tail -1 | tr -dc '0-9')"
[ "${disk:-100}" -lt "$DISK_MAX_PERCENT" ] || failures+=("disk / at ${disk}% (limit ${DISK_MAX_PERCENT}%)")

mem_total="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
mem_avail="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
mem_pct=$(( mem_avail * 100 / mem_total ))
[ "$mem_pct" -ge "$MEM_MIN_PERCENT" ] || failures+=("available memory ${mem_pct}% (minimum ${MEM_MIN_PERCENT}%)")

summary="disk=${disk}% mem_available=${mem_pct}% ml_models=$code"
if [ ${#failures[@]} -eq 0 ]; then
  echo "OK $summary"
  exit 0
fi

joined="$(printf '%s; ' "${failures[@]}")"
message="SentinelFlow $SENTINELFLOW_DOMAIN: ${joined%; }"
echo "FAIL $summary :: $message" >&2
if [ -n "$ALERT_WEBHOOK_URL" ]; then
  payload="$(python3 -c 'import json,sys; print(json.dumps({"text": sys.argv[1], "content": sys.argv[1]}))' "$message")"
  curl -fsS --max-time 10 -H 'Content-Type: application/json' -d "$payload" "$ALERT_WEBHOOK_URL" >/dev/null \
    || echo "could not deliver alert to ALERT_WEBHOOK_URL" >&2
fi
exit 1
