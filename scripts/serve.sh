#!/usr/bin/env bash
# Launch the warm, long-running server. Run from the repo root inside WSL2.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
echo "Serving on 0.0.0.0:${PORT} (WSL2). Reach it from the phone via the Windows Tailscale IP."
exec python3 -m uvicorn server.main:app --host 0.0.0.0 --port "${PORT}"
