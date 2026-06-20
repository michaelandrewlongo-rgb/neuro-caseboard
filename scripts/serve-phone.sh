#!/usr/bin/env bash
# Build the SPA if missing, then serve GUI+API on 0.0.0.0 so a phone can reach it.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${1:-8001}"
if [ ! -f web/dist/index.html ]; then
  echo "web/dist not found — building the SPA (npm --prefix web run build)…"
  npm --prefix web run build
fi
exec python3 -m api.serve_phone --port "$PORT"
