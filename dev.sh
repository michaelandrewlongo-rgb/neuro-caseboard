#!/usr/bin/env bash
# Single local dev command: boots the FastAPI engine wrapper (:8001) and the Vite SPA (:5173)
# together. No auth, no cloud, no Docker. Open http://localhost:5173 when it's up.
#
#   ./dev.sh
#
# Env overrides: API_PORT (default 8001), CORPUS_DIR (default /home/michael/textbook_pdfs),
# BRIEFING_SYNTH_CONCURRENCY (default 2) and BRIEFING_SYNTH_RETRIES (default 3) — conservative
# values that dodge the Vertex-Flash throttle so briefings come back fully (not degraded).
# Port 8001 (not 8000) avoids a Windows WinNAT excluded-port-range that blocks 8000 on WSL2.
set -euo pipefail
cd "$(dirname "$0")/web"
exec npm run dev
