#!/usr/bin/env bash
# Pull-based self-hosted rollout for the box (run by a systemd timer / cron; see docs/cd.md).
# Pulls the latest image, redeploys, health-gates on /api/health .engine, and ROLLS BACK to the
# prior image if the engine reports unavailable (a broken image) — NOT for merely-degraded data
# lanes (corpus/cards false just means volumes aren't mounted, which is expected).
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${CASEBOARD_PORT:-8001}"
HEALTH_URL="http://127.0.0.1:${PORT}/api/health"
SERVICE="caseboard"
TIMEOUT_SECS="${DEPLOY_HEALTH_TIMEOUT:-180}"

# --- pure decision fn: given health JSON (or empty on unreachable), is the deploy healthy? ---
engine_ok() {  # reads JSON on stdin; exit 0 iff top-level "engine": true
  python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
sys.exit(0 if d.get("engine") is True else 1)
'
}

poll_health() {  # exit 0 once engine:true within TIMEOUT_SECS, else 1
  local deadline=$(( $(date +%s) + TIMEOUT_SECS ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if curl -fsS --max-time 8 "$HEALTH_URL" 2>/dev/null | engine_ok; then
      return 0
    fi
    sleep 5
  done
  return 1
}

if [ "${1:-}" = "--selftest" ]; then
  # ponytail: one runnable check on the rollback DECISION (the only non-trivial logic here).
  echo '{"engine": true,  "corpus": false}' | engine_ok        && echo "ok: engine true -> keep"
  echo '{"engine": false, "corpus": true }' | engine_ok        && { echo "FAIL: engine false judged healthy"; exit 1; } || echo "ok: engine false -> rollback"
  echo ''                                   | engine_ok        && { echo "FAIL: unreachable judged healthy"; exit 1; } || echo "ok: unreachable -> rollback"
  echo "selftest passed"; exit 0
fi

# Capture the currently-running image id for rollback (empty on first deploy).
PREV_IMAGE="$(docker compose images -q "$SERVICE" 2>/dev/null | head -n1 || true)"
if [ -n "$PREV_IMAGE" ]; then
  PREV_IMAGE="$(docker inspect --format '{{.Image}}' "$(docker compose ps -q "$SERVICE")" 2>/dev/null || echo "$PREV_IMAGE")"
fi

echo ">> pulling latest image"
docker compose pull "$SERVICE"
echo ">> deploying"
docker compose up -d "$SERVICE"

if poll_health; then
  echo ">> deploy healthy (engine available)"
  exit 0
fi

echo "!! engine unavailable after ${TIMEOUT_SECS}s — rolling back" >&2
if [ -n "$PREV_IMAGE" ]; then
  CASEBOARD_IMAGE="$PREV_IMAGE" docker compose up -d "$SERVICE"
  if poll_health; then
    echo ">> rolled back to prior image ($PREV_IMAGE); engine available" >&2
  else
    echo "!! rollback to $PREV_IMAGE also unhealthy — manual intervention needed" >&2
  fi
else
  echo "!! no prior image to roll back to (first deploy); leaving new image up for diagnosis" >&2
fi
exit 1
