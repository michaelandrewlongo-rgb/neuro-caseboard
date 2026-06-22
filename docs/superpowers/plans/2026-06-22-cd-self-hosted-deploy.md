# CD: Versioned Containerized Self-Hosted Deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Each top-level `- [ ]` is ONE reviewable deliverable (project-loop dispatches one subagent + one VERIFY per checkbox). Implement the whole task named on the checkbox, using the spec beneath it; do not split a task across increments.

**Goal:** Turn the single-origin serve flow (`api.server:app` serving the built React SPA on `0.0.0.0:8001`) into a versioned, containerized, automated self-hosted deployment — Dockerfile + compose + GHCR via a tag-triggered `cd.yml` + a pull-based self-hosted rollout with health-gated rollback — plus the missing web CI gate. CD runs AFTER the existing required CI is green; it does not touch `ci.yml`.

**Architecture:** A 3-stage Docker build (node:20 builds `web/dist` → python:3.12-slim builds a venv with `.[vertex,models]` → slim runtime that copies the venv + `api/` + `web/dist` and runs uvicorn). `docker-compose.yml` mounts the private corpus/index/figures + ADC json as **read-only** volumes and injects secrets/env at runtime — nothing private is ever baked in. `cd.yml` (tag `v*` / dispatch) builds + pushes to GHCR tagged by version AND sha, secret-gated to a green no-op when CD isn't configured. The intermittent WSL2 box runs `scripts/cd-pull-deploy.sh` on a timer (pull-based — the box initiates), which redeploys and **rolls back to the prior image** if `/api/health` reports `engine:false`.

**Tech Stack:** Docker multi-stage, docker compose v2, GitHub Actions, GHCR (`ghcr.io`), FastAPI/uvicorn, Vite/React, bash.

## Global Constraints

Copied verbatim from the spec — every task implicitly includes these:

- **LLM provider is VERTEX, not Anthropic.** Synthesis uses `google-genai`, `GOOGLE_CLOUD_PROJECT`, and ADC. There is **NO `ANTHROPIC_API_KEY`**. Reuse the secret names `live-judge.yml` uses: `CASEBOARD_LLM_PROVIDER`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CREDENTIALS`.
- **Live data lives OUTSIDE the repo, is private + multi-GB — NEVER bake it into the image.** Mount read-only at runtime: corpus PDFs (`CORPUS_DIR`, host `/home/michael/textbook_pdfs`), LanceDB index (`/home/michael/neuro-textbook-rag/index`), figure assets (`/home/michael/neuro-textbook-rag/assets/figures`). The index is queried in place.
- **NEVER bake secrets into the image.** ADC json + `NCBI_API_KEY` are injected at run (volume/env), never `COPY`ed.
- **caseprep is vendored in-tree** (`vendor/caseprep`). Install the project itself only (`pip install .[vertex,models]`); never `pip install` an external caseprep.
- **Required CI deliberately omits torch; the SERVE image is a different target** and legitimately includes `.[models]` (sentence-transformers + open-clip-torch) for query-time embedding against the index, plus `.[vertex]`.
- **WSL2 networking:** serving binds `0.0.0.0:8001` and must stay phone-reachable (mirrored networking / `scripts/wsl-portproxy.ps1`). Don't regress `docs/SERVE_ON_PHONE.md`.
- **Do NOT touch or duplicate the required PR gate in `.github/workflows/ci.yml`.** CD triggers AFTER CI is green.
- Repo: `ghcr.io/michaelandrewlongo-rgb/neuro-caseboard` (the GHCR image namespace = `ghcr.io/${{ github.repository }}` lowercased).
- Serve entrypoint = `uvicorn api.server:app --host 0.0.0.0 --port 8001`. `/api/health` returns 200 with honest booleans `engine` / `synth` / `corpus` / `cards_index` / `ncbi_key`; **`engine:false` = broken image (rollback trigger); `corpus:false`/`cards_index:false` = volumes-not-mounted = expected degradation (NOT a rollback trigger).**

---

### Task 1: Fix the pre-existing web lint error (unblocks the harness)

**Files:**
- Modify: `web/src/lib/srs.ts:29`

**Why first:** the loop harness is `npm --prefix web run lint / test / build`. Baseline lint **fails** with one pre-existing error (`29:35 'lapses' is never reassigned. Use 'const' instead  prefer-const`) that no workflow ever caught. Until it's fixed, every VERIFY fails on lint. Tiny, isolated, independently shippable.

- [x] **Task 1** — Change the `let lapses` declaration at `web/src/lib/srs.ts:29` to `const lapses` (the variable is never reassigned). Do not change behavior.
  - Verify: `npm --prefix web run lint` exits 0 (no errors). `npm --prefix web run test` still 20 pass. `npm --prefix web run build` still succeeds.
  - Commit: `loop step 0: fix web lint (prefer-const in srs.ts) so the web gate is green`

---

### Task 2: Web CI gate workflow (`.github/workflows/web.yml`)

**Files:**
- Create: `.github/workflows/web.yml`

**Rationale:** the web bundle (4 vitest suites + `tsc -b && vite build`) has zero CI coverage today. The spec says add a web job and make it a required workflow. We add a **separate** workflow (NOT editing `ci.yml`, per the global constraint) so it can be marked a required check alongside the python jobs.

- [x] **Task 2** — Create `.github/workflows/web.yml` exactly:

```yaml
name: web

# The web bundle (React/Vite SPA) gate. Mirrors ci.yml's "required, offline, deterministic"
# philosophy for the frontend: eslint + vitest + a real production build. No keys, no engine,
# no corpus. Add this as a required status check on master alongside the python jobs.

on:
  pull_request:
  push:
    branches: [master]

concurrency:
  group: web-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  web:
    name: web (lint + test + build)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: web/package-lock.json
      - name: Install (clean, lockfile-pinned)
        run: npm ci
      - name: Lint
        run: npm run lint
      - name: Unit tests (vitest)
        run: npm run test
      - name: Production build (tsc + vite)
        run: npm run build
```

  - Verify: `python -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('.github/workflows/web.yml').read_text()); print('web.yml OK')"` (if PyYAML unavailable, `docker run --rm -v "$PWD":/w -w /w rhysd/actionlint:latest .github/workflows/web.yml` or visual review). The three commands already pass locally after Task 1.
  - Commit: `loop step 1: add web CI gate workflow (lint + vitest + build)`

---

### Task 3: `.dockerignore` + multi-stage `Dockerfile`

**Files:**
- Create: `.dockerignore`
- Create: `Dockerfile`

**Interfaces (relied on by Tasks 4–8):**
- Image runs `uvicorn api.server:app` on `0.0.0.0:8001`; `WORKDIR /app`; venv on `PATH=/opt/venv/bin`.
- `web/dist` at `/app/web/dist` (also `NEURO_CASEBOARD_WEB_DIST=/app/web/dist`), so `/` serves the SPA.
- `HEALTHCHECK` hits `/api/health` via python urllib (slim has no curl).

- [x] **Task 3** — Create `.dockerignore`:

```gitignore
.git
**/__pycache__
**/*.pyc
.venv
.ci-venv
.pytest_cache
dist
build
*.egg-info
web/node_modules
web/dist
node_modules
.project-loop
evaluation/runs
docs/superpowers/plans
.claude
# secrets / credentials must never enter the build context
.env
**/.env
*.pem
**/application_default_credentials.json
**/*adc*.json
.config
```

Then create `Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1
# Multi-stage SERVE image for neuro-caseboard. This is the runtime/serve target — DISTINCT from
# required CI (which deliberately omits torch). It legitimately includes .[models] (sentence-
# transformers + open-clip-torch) for query-time embedding against the LanceDB index, plus
# .[vertex] (google-genai) for Vertex synthesis. NO corpus, NO index, NO secrets are baked in;
# those are mounted/injected at runtime by docker-compose.yml.

# ---- Stage 1: build the React/Vite SPA -> /web/dist ----
FROM node:20-slim AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build            # tsc -b && vite build -> /web/dist

# ---- Stage 2: build a venv with the package + heavy runtime extras ----
FROM python:3.12-slim AS py-build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /src
# Most deps ship manylinux wheels (lancedb, pymupdf, numpy, pillow, torch, open-clip,
# sentence-transformers). build-essential is added defensively in case pip must compile a sdist;
# if the build proves it unneeded, the implementer may drop it to shrink the build stage.
# ponytail: build-essential kept for a clean first build; drop if `pip install` uses only wheels.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*
# Only the files pip needs to build/install the package (pyproject packages= list + readme +
# the in-tree vendored caseprep). NOT api/ (run from workdir) and NOT web (built in stage 1).
COPY pyproject.toml README.md ./
COPY neuro_caseboard ./neuro_caseboard
COPY neuro_core ./neuro_core
COPY vendor ./vendor
RUN python -m venv /opt/venv \
 && . /opt/venv/bin/activate \
 && pip install --upgrade pip \
 && pip install ".[vertex,models]"

# ---- Stage 3: slim runtime ----
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    NEURO_CASEBOARD_WEB_DIST=/app/web/dist \
    SYNTH_PROVIDER=vertex
WORKDIR /app
COPY --from=py-build /opt/venv /opt/venv
COPY api ./api
COPY --from=web-build /web/dist ./web/dist
EXPOSE 8001
# /api/health always returns 200 with honest booleans; a 200 proves the server + endpoint are up.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=8)" || exit 1
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8001"]
```

  - Verify (the subagent MUST run these and only commit on success):
    1. `docker build -t neuro-caseboard:dev .` → completes; note the final image id.
    2. `docker image inspect neuro-caseboard:dev --format '{{.Size}}'` → record bytes (goal evidence).
    3. Boot with NO data volumes (degraded path): `docker run -d --rm -p 8001:8001 -e GOOGLE_CLOUD_PROJECT=dummy --name cb-dev neuro-caseboard:dev`; wait for boot; `curl -s localhost:8001/api/health` → expect HTTP 200 JSON with `"engine": true` (image is sound) and `"corpus": false` (no index mounted — honest degradation). `curl -s -o /dev/null -w '%{http_code}' localhost:8001/` → `200` (SPA served) or `503` only if dist missing (must be `200`). Then `docker stop cb-dev`.
    - If `engine:false`, the image is broken — diagnose (missing COPY / import error in the venv) before committing.
  - Commit: `loop step 2: multi-stage serve Dockerfile + .dockerignore (web build + venv + uvicorn)`

---

### Task 4: `docker-compose.yml` (read-only data volumes + injected secrets)

**Files:**
- Create: `docker-compose.yml`

**Interfaces consumed:** the image from Task 3 (`ghcr.io/...:latest` or local `build: .`); env names from `neuro_core/config.py` (`INDEX_DIR` gates `corpus`; `ASSETS_DIR` = figures; `CORPUS_DIR` = re-index only; `SYNTH_PROVIDER`/`GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION`/`VERTEX_MODEL`); `GOOGLE_APPLICATION_CREDENTIALS` (read by `api.server._adc_present()`); `NCBI_API_KEY` (literature lane).
**Produces:** `scripts/cd-pull-deploy.sh` (Task 5) drives `docker compose pull/up`; honors `CASEBOARD_IMAGE` to pin/rollback.

- [x] **Task 4** — Create `docker-compose.yml`:

```yaml
# Single-process serve of the Caseboard GUI+API. Live data + secrets are MOUNTED read-only at
# runtime — NEVER baked into the image. All host paths are env-overridable (machine defaults shown).
# Phone reachability (bind 0.0.0.0) still needs WSL2 mirrored networking / wsl-portproxy.ps1 — see
# docs/SERVE_ON_PHONE.md.
services:
  caseboard:
    image: ${CASEBOARD_IMAGE:-ghcr.io/michaelandrewlongo-rgb/neuro-caseboard:latest}
    build: .                                  # `docker compose build` locally; the box uses `pull`
    ports:
      - "${CASEBOARD_PORT:-8001}:8001"        # 0.0.0.0:8001 -> phone-reachable
    restart: unless-stopped
    environment:
      SYNTH_PROVIDER: vertex
      CASEBOARD_LLM_PROVIDER: ${CASEBOARD_LLM_PROVIDER:-vertex}
      GOOGLE_CLOUD_PROJECT: ${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT in the box .env}
      GOOGLE_CLOUD_LOCATION: ${GOOGLE_CLOUD_LOCATION:-us-central1}
      VERTEX_MODEL: ${VERTEX_MODEL:-gemini-2.5-pro}
      GOOGLE_APPLICATION_CREDENTIALS: /secrets/adc.json
      CORPUS_DIR: /data/corpus
      INDEX_DIR: /data/index
      ASSETS_DIR: /data/figures
      NCBI_API_KEY: ${NCBI_API_KEY:-}
      GPU_GUARD: "false"                       # CPU container: never block on GPU readiness
      EMBED_DEVICE: ${EMBED_DEVICE:-cpu}
    volumes:
      - ${CORPUS_DIR:-/home/michael/textbook_pdfs}:/data/corpus:ro
      - ${INDEX_DIR:-/home/michael/neuro-textbook-rag/index}:/data/index:ro
      - ${ASSETS_DIR:-/home/michael/neuro-textbook-rag/assets/figures}:/data/figures:ro
      - ${GOOGLE_CREDENTIALS_FILE:-${HOME}/.config/gcloud/application_default_credentials.json}:/secrets/adc.json:ro
```

  - Verify:
    1. `docker compose config -q` → exits 0 (compose file valid; interpolation resolves with a dummy `GOOGLE_CLOUD_PROJECT=dummy` in env).
    2. Boot test: `GOOGLE_CLOUD_PROJECT=dummy docker compose up -d --build`; `curl -s localhost:8001/api/health | python -m json.tool` → record. If the **real** host index path exists, expect `"corpus": true`; if not, `"corpus": false` with detail "textbook index not built" (honest). `engine` MUST be `true`. `docker compose down`.
    - **Known risk to check:** LanceDB querying a `:ro`-mounted index. If queries fail because LanceDB needs to write a lock/version file, note it in `docs/cd.md` and (only if required) document switching the index mount to `:rw` or adding a writable `tmpfs` for its lock dir — but keep `:ro` as the default per the spec; surface the finding either way.
  - Commit: `loop step 3: docker-compose with read-only corpus/index/figures + injected ADC/secrets`

---

### Task 5: Pull-based deploy + health-gated rollback (`scripts/cd-pull-deploy.sh`)

**Files:**
- Create: `scripts/cd-pull-deploy.sh` (executable)

**Mechanism choice:** the box is an intermittent WSL2 host, so we favor a **pull-based** rollout the box initiates (a systemd timer or cron runs this script every ~10 min) over a push that assumes a self-hosted runner is always online. The script pulls the latest image, captures the currently-running image id first, `up -d`, then polls `/api/health` and parses `.engine`: `engine:true` → keep; unreachable or `engine:false` → **roll back** to the captured prior image and `up -d` again, exiting non-zero.

**Interfaces:** consumes `docker-compose.yml` (Task 4); honors `CASEBOARD_IMAGE` to pin a rollback target.

- [x] **Task 5** — Create `scripts/cd-pull-deploy.sh` (and `chmod +x`):

```bash
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
  if CASEBOARD_IMAGE="$PREV_IMAGE" poll_health; then
    echo ">> rolled back to prior image ($PREV_IMAGE); engine available" >&2
  else
    echo "!! rollback to $PREV_IMAGE also unhealthy — manual intervention needed" >&2
  fi
else
  echo "!! no prior image to roll back to (first deploy); leaving new image up for diagnosis" >&2
fi
exit 1
```

  - Verify: `bash scripts/cd-pull-deploy.sh --selftest` → prints the three `ok:` lines and `selftest passed` (exit 0). `bash -n scripts/cd-pull-deploy.sh` (syntax). If `shellcheck` is available: `shellcheck scripts/cd-pull-deploy.sh` (advisory).
  - Commit: `loop step 4: pull-based cd-pull-deploy.sh with engine-health-gated rollback + selftest`

---

### Task 6: `cd.yml` — tag-triggered GHCR build/push, secret-gated no-op

**Files:**
- Create: `.github/workflows/cd.yml`

**Gating (mirrors `live-judge.yml`):** a `gate` job emits `configured`. When the repo variable `CD_ENABLED` is not `true`, every heavy job is skipped → a clean green no-op (so forks / unconfigured repos never fail). GHCR push uses the auto `GITHUB_TOKEN` (`packages: write`); no custom registry secret is needed.

- [x] **Task 6** — Create `.github/workflows/cd.yml`:

```yaml
name: CD

# Runs AFTER the required CI is green — it does not re-run or duplicate ci.yml's PR gate. Triggers
# only on a version tag (v*) or a manual dispatch. Builds the SPA + serve image and pushes it to
# GHCR tagged by version AND git sha. Secret/variable-gated: with CD_ENABLED unset it is a clean,
# green no-op (mirrors live-judge.yml). The actual rollout is PULL-based — the self-hosted box's
# cd-pull-deploy.sh timer picks up the new image (see docs/cd.md); CD does not push to the box.

on:
  push:
    tags: ["v*"]
  workflow_dispatch:
    inputs:
      version:
        description: "Version tag to build/push (e.g. v0.2.0)"
        required: true

permissions:
  contents: read
  packages: write

env:
  PIP_DISABLE_PIP_VERSION_CHECK: "1"

jobs:
  gate:
    name: Gate on CD config (clean no-op when unconfigured)
    runs-on: ubuntu-latest
    outputs:
      configured: ${{ steps.gate.outputs.configured }}
    steps:
      - id: gate
        run: |
          if [ "${{ vars.CD_ENABLED }}" = "true" ]; then
            echo "configured=true" >> "$GITHUB_OUTPUT"
          else
            echo "CD_ENABLED variable is not 'true' — CD is the keyed deploy path (skipping cleanly)."
            echo "configured=false" >> "$GITHUB_OUTPUT"
          fi

  web:
    name: web gate (lint + test + build)
    needs: gate
    if: needs.gate.outputs.configured == 'true'
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run test
      - run: npm run build

  build-push:
    name: build + push image to GHCR
    needs: [gate, web]
    if: needs.gate.outputs.configured == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: Resolve version + lowercased image ref
        id: meta
        run: |
          if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
            VERSION="${{ github.event.inputs.version }}"
          else
            VERSION="${GITHUB_REF_NAME}"
          fi
          IMAGE="ghcr.io/$(echo '${{ github.repository }}' | tr '[:upper:]' '[:lower:]')"
          echo "version=$VERSION" >> "$GITHUB_OUTPUT"
          echo "image=$IMAGE" >> "$GITHUB_OUTPUT"
      # Validate install metadata the same way CI's package job does (shared installer; caseprep
      # is bundled). Cheap guard that the serve image's pip target is sane before the long build.
      - name: Sanity — package install target resolves
        run: |
          python -m pip install --upgrade pip build >/dev/null
          python -m build >/dev/null && echo "sdist+wheel build OK"
      - uses: docker/setup-buildx-action@v3
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push (version + sha + latest)
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ${{ steps.meta.outputs.image }}:${{ steps.meta.outputs.version }}
            ${{ steps.meta.outputs.image }}:${{ github.sha }}
            ${{ steps.meta.outputs.image }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - name: Rollout note (pull-based)
        run: |
          echo "Pushed ${{ steps.meta.outputs.image }}:${{ steps.meta.outputs.version }} (+ sha, +latest)."
          echo "The self-hosted box's cd-pull-deploy.sh timer will roll it out and health-gate/rollback."
```

  - Verify: `python -c "import yaml,pathlib; [yaml.safe_load(pathlib.Path(p).read_text()) for p in ['.github/workflows/cd.yml']]; print('cd.yml OK')"` (or actionlint). Confirm `ci.yml` is byte-identical to master (`git diff master -- .github/workflows/ci.yml` is empty). Confirm the gate logic produces a no-op when `CD_ENABLED` is unset (read-through).
  - Commit: `loop step 5: cd.yml — tag v* -> GHCR build/push, web gate, secret-gated no-op`

---

### Task 7: `docs/cd.md` (runbook, mirroring `docs/ci.md`)

**Files:**
- Create: `docs/cd.md`

- [ ] **Task 7** — Write `docs/cd.md` mirroring `docs/ci.md`'s structure and tone. It MUST cover:
  - **What each stage does:** the 3-stage Dockerfile (web build → venv with `.[vertex,models]` → slim uvicorn runtime); why the serve image includes torch though required CI omits it; `web.yml` as the new required web gate; `cd.yml` trigger (`v*` / dispatch) → web gate → build/push to GHCR (`version` + `sha` + `latest`); the pull-based rollout.
  - **GitHub config/secrets:** repo **variable** `CD_ENABLED=true` enables CD (else green no-op); GHCR push uses the built-in `GITHUB_TOKEN` (`packages: write`) — no extra registry secret. Note the Vertex secret names reused from `live-judge.yml` (`CASEBOARD_LLM_PROVIDER`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CREDENTIALS`) are for the *engine at runtime on the box*, not for the image build.
  - **One-time box setup:** `docker login ghcr.io` (PAT with `read:packages`); a box `.env` next to `docker-compose.yml` with `GOOGLE_CLOUD_PROJECT`, optional `NCBI_API_KEY`, and any path overrides (`INDEX_DIR`, `ASSETS_DIR`, `CORPUS_DIR`, `GOOGLE_CREDENTIALS_FILE`); the read-only volume mounts (corpus/index/figures + ADC json at `/secrets/adc.json`); a **systemd timer or cron** running `scripts/cd-pull-deploy.sh` every ~10 min (give both a sample `cron` line and a sample systemd `.service` + `.timer`). Cross-link `docs/SERVE_ON_PHONE.md` for the WSL2 0.0.0.0 reachability (mirrored networking / `wsl-portproxy.ps1`) — note CD does not change that.
  - **Health & rollback semantics:** `/api/health` `engine:false` = broken image → automatic rollback to the prior image; `corpus:false`/`cards_index:false` = volumes not mounted = expected degradation, not a rollback. Document the `:ro` LanceDB index caveat if Task 4 surfaced one.
  - **Manual rollback runbook:** how to pin a known-good tag — `CASEBOARD_IMAGE=ghcr.io/michaelandrewlongo-rgb/neuro-caseboard:<good-tag> docker compose up -d` — and how to list available tags (GHCR UI / `docker image ls`), plus `bash scripts/cd-pull-deploy.sh --selftest` to validate the gate logic.
  - Verify: file exists; internal links resolve (`docs/SERVE_ON_PHONE.md`, `docs/ci.md`); every shell snippet is copy-pasteable; no placeholders/TBDs.
  - Commit: `loop step 6: docs/cd.md — stages, GitHub config, one-time box setup, rollback runbook`

---

### Task 8: End-to-end local evidence (build → boot → health → image size)

**Files:**
- Modify: `.project-loop/SCORECARD.md` (append the captured evidence row) — and paste the evidence in the loop LOG.

**This is the goal's explicit "VERIFY before claiming done."** Evidence, not assertions.

- [ ] **Task 8** — Produce and record real evidence:
  1. `docker build -t neuro-caseboard:evidence .` → success.
  2. `docker image inspect neuro-caseboard:evidence --format '{{.Size}}'` → bytes; also `docker image ls neuro-caseboard:evidence` for the human-readable size. Record both.
  3. Boot via compose with whatever real host volumes exist (`GOOGLE_CLOUD_PROJECT=<real-or-dummy> docker compose up -d`). Capture `curl -s localhost:8001/api/health | python -m json.tool` verbatim. Capture `curl -s -o /dev/null -w '%{http_code}\n' localhost:8001/` (SPA at `/` → `200`).
  4. If the real corpus/index can't be mounted in this environment, **say so explicitly** and capture the **degraded** health output (`engine:true`, `corpus:false` with the honest "index not built" detail) — that still proves the image is sound; the data lanes light up only where the volumes exist.
  5. `docker compose down`.
  - Verify: the pasted `/api/health` shows `engine: true`; the SPA path returns `200`; image size recorded. Append a SCORECARD row with the numbers and a one-line note on whether real data was mounted or degraded.
  - Commit: `loop step 7: capture build/boot/health + image-size evidence (verify-before-done)`

---

## Self-Review

**1. Spec coverage:**
- Multi-stage Dockerfile (node build → python serve, no corpus/index/secrets, HEALTHCHECK /api/health) → Task 3. ✓
- docker-compose with ro corpus/index/figures + ADC + env (GOOGLE_CLOUD_PROJECT, CORPUS_DIR, INDEX_DIR, CASEBOARD_LLM_PROVIDER, NCBI_API_KEY) + port 8001 + restart unless-stopped + non-hardcoded paths → Task 4. ✓
- cd.yml on tag v* + workflow_dispatch(version); web vitest/eslint + python install + container build + GHCR push (version + sha); secret-gated no-op mirroring live-judge → Task 6. ✓
- Deploy mechanism = pull-based box-initiated rollout with post-deploy rollback on engine-unavailable → Task 5 (+ box timer documented in Task 7). ✓
- docs/cd.md mirroring docs/ci.md (stages, secrets, one-time box setup, rollback runbook) → Task 7. ✓
- Web CI gate (lint + test + build), as a required workflow (not editing ci.yml) → Task 2; pre-existing lint error fixed → Task 1. ✓
- VERIFY before done: build image, boot, health output, image byte size; degraded path if corpus unavailable → Task 8. ✓
- Constraints: Vertex not Anthropic; no baked data/secrets; vendored caseprep; .[vertex,models] serve target; WSL 0.0.0.0 + don't regress SERVE_ON_PHONE.md; don't touch ci.yml → Global Constraints + per-task. ✓

**2. Placeholder scan:** all file contents are complete and literal; no TBD/TODO. Task 7 (docs) is prose-specified with the exact items and snippets it must contain.

**3. Type/name consistency:** image ref `ghcr.io/michaelandrewlongo-rgb/neuro-caseboard` and env override `CASEBOARD_IMAGE` are consistent across Tasks 3–7; `/api/health.engine` is the single rollback signal in Tasks 3/5/7; `CD_ENABLED` gate is consistent in Tasks 6/7; serve command `uvicorn api.server:app --host 0.0.0.0 --port 8001` consistent in Tasks 3/4 and matches `api/serve_phone.py`/`scripts/serve-phone.sh`.
