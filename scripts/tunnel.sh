#!/usr/bin/env bash
# Public Cloudflare quick tunnel for neuro-caseboard.
# Starts the app on :PORT if it isn't already up, then opens the tunnel and
# prints the https://*.trycloudflare.com URL to share. Ctrl+C stops the tunnel.
#
#   ./scripts/tunnel.sh          # port 8001 (default)
#   ./scripts/tunnel.sh 8080     # some other port
#
# ponytail: quick tunnel = ephemeral URL, dies with this process / on reboot.
# For a permanent same-URL link, upgrade to a named tunnel (Cloudflare acct + domain).
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${1:-8001}"
CFD="$(command -v cloudflared || echo "$HOME/.local/bin/cloudflared")"

if ! curl -fsS -o /dev/null --max-time 3 "http://localhost:$PORT"; then
  echo "neuro-caseboard not up on :$PORT — starting it (logs: /tmp/caseboard-$PORT.log)…"
  ./scripts/serve-phone.sh "$PORT" >"/tmp/caseboard-$PORT.log" 2>&1 &
  for _ in $(seq 1 60); do
    if curl -fsS -o /dev/null --max-time 2 "http://localhost:$PORT"; then break; fi
    sleep 1
  done
  if ! curl -fsS -o /dev/null --max-time 2 "http://localhost:$PORT"; then
    echo "app failed to come up on :$PORT — check /tmp/caseboard-$PORT.log" >&2
    exit 1
  fi
fi

echo "app is up on :$PORT — opening Cloudflare tunnel (share the URL below; Ctrl+C to stop)…"
exec "$CFD" tunnel --url "http://localhost:$PORT"
