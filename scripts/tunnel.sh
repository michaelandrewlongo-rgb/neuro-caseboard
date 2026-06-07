#!/usr/bin/env bash
# Expose the local server publicly via a Cloudflare quick tunnel. Run AFTER
# ./scripts/serve.sh, from the repo root inside WSL2. Requires cloudflared.
set -euo pipefail
cd "$(dirname "$0")/.."

# Safety: never expose a naked (passcode-less) server to the public internet.
# Resolve APP_PASSCODE the way the app does: shell env first, then .env with
# surrounding quotes/whitespace stripped — so APP_PASSCODE="" counts as EMPTY.
pc_val="${APP_PASSCODE:-}"
if [ -z "$pc_val" ] && [ -f .env ]; then
  pc_val=$(grep -E '^APP_PASSCODE=' .env | head -1 \
    | sed -E 's/^APP_PASSCODE=//; s/\r//g; s/^[[:space:]]+//; s/[[:space:]]+$//; s/^"(.*)"$/\1/')
fi
if [ -z "$pc_val" ]; then
  echo "Refusing to tunnel: set a non-empty APP_PASSCODE (in .env or your shell) — the URL is public."
  exit 1
fi
if ! curl -sf -m 3 localhost:8000/healthz >/dev/null; then
  echo "Server not responding on :8000 — start it first:  ./scripts/serve.sh"
  exit 1
fi
if ! command -v cloudflared >/dev/null; then
  echo "cloudflared not installed. One-time install:"
  echo '  mkdir -p ~/.local/bin && curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o ~/.local/bin/cloudflared && chmod +x ~/.local/bin/cloudflared'
  echo '  (ensure ~/.local/bin is on PATH)'
  exit 1
fi

echo "Opening a public Cloudflare tunnel to localhost:8000."
echo "Copy the https://<...>.trycloudflare.com URL printed below onto your phone."
exec cloudflared tunnel --url http://localhost:8000
