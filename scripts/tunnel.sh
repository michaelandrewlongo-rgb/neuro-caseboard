#!/usr/bin/env bash
# Expose the local server publicly via a Cloudflare quick tunnel. Run AFTER
# ./scripts/serve.sh, from the repo root inside WSL2. Requires cloudflared.
set -euo pipefail
cd "$(dirname "$0")/.."

# Safety: never expose a naked (passcode-less) server to the public internet.
if ! grep -qE '^APP_PASSCODE=.+' .env 2>/dev/null; then
  echo "Refusing to tunnel: set APP_PASSCODE=<something> in .env first (the URL is public)."
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
