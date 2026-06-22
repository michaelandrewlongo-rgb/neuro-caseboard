# Continuous Delivery

This repo's CD is the other half of the pipeline from [`ci.md`](ci.md): CI proves a change is good
on every PR; **CD packages a tagged release as a container, publishes it to GHCR, and a self-hosted
box pulls and runs it**. CD runs *after* CI is green and never touches the required PR gate
(`.github/workflows/ci.yml`).

One principle mirrors CI: **the image never carries anything private**. No corpus, no LanceDB index,
no figure assets, no credentials are baked in — they are mounted/injected read-only at run time. The
image is just the engine + the built web console.

> Provider is **Vertex** (Gemini via `google-genai` + ADC), not Anthropic — there is no
> `ANTHROPIC_API_KEY`. The serve image is a *different target* from required CI: CI deliberately omits
> torch, but the serve image includes the `models` extra (sentence-transformers + open-clip-torch) for
> query-time embedding against the index, plus the `vertex` extra.

## The artifacts

| File | Role |
|------|------|
| `Dockerfile` | 3-stage serve image (below). |
| `.dockerignore` | Keeps `.git`, `node_modules`, `web/dist`, `.env`, ADC json, and `.project-loop` **out** of the build context — no secret or data can leak in. |
| `docker-compose.yml` | Runs the image with read-only data volumes + injected env/secrets, port 8001, `restart: unless-stopped`. All host paths are env-overridable. |
| `scripts/cd-pull-deploy.sh` | The box's pull-based rollout with a health-gated rollback. Run by a timer/cron. |
| `.github/workflows/web.yml` | Required web gate (lint + vitest + build) — the SPA had no CI before; CD ships the bundle, so it must be tested. |
| `.github/workflows/cd.yml` | Tag-triggered build + push to GHCR. |

## The container — multi-stage `Dockerfile`

| Stage | Base | What it does |
|-------|------|--------------|
| `web-build` | `node:20-slim` | `npm ci` + `npm run build` → `/web/dist` (the React/Vite console). |
| `py-build` | `python:3.12-slim` | Creates `/opt/venv` and `pip install ".[vertex,models]"` from the in-tree source (vendored caseprep included; no external install). |
| `runtime` | `python:3.12-slim` | Copies the venv + `api/` + `web/dist`; runs `uvicorn api.server:app --host 0.0.0.0 --port 8001`. `HEALTHCHECK` hits `/api/health` (via python urllib — slim has no curl). |

`uvicorn api.server:app` is the whole product: the engine at `/api/*`, the SPA at `/`. The image is
**large (~9.3 GB)** because torch + open-clip dominate. Since the container runs CPU-only
(`EMBED_DEVICE=cpu`), installing CPU-only torch wheels
(`pip install torch --index-url https://download.pytorch.org/whl/cpu`) would cut it ~3× — a worthwhile
follow-up for a faster pull on the box.

## The required PR gates

CD only fires on a tag, but two **required** PR workflows must stay green for a release to be sound:

- `ci.yml` (unchanged) — the python sanity/test/package gate. See [`ci.md`](ci.md).
- `web.yml` (new) — `npm ci` → `lint` → `test` → `build` on node 20. Add it to branch protection on
  `master` alongside the python checks (Settings → Branches → require status check **`web (lint + test + build)`**).

## `cd.yml` — what each stage does

Triggered by a `v*` tag push (`git tag v0.2.0 && git push --tags`) or **Run workflow** (manual
dispatch with a `version` input).

| Job | What it does |
|-----|--------------|
| **gate** | If the repo **variable** `CD_ENABLED` is not `true`, every later job is skipped → a clean, green **no-op** (mirrors `live-judge.yml`; forks / unconfigured repos never fail). |
| **web** | `lint` + `test` + `build` — a fast pre-build guard on the bundle being shipped. |
| **build-push** | Resolves the version (tag name or dispatch input) and the lowercased `ghcr.io/<owner>/<repo>` ref; a `./ci/install.sh ".[dev]"` fail-fast sanity; logs in to GHCR with the built-in `GITHUB_TOKEN`; `docker/build-push-action` builds and pushes the image tagged by **version**, **git sha**, and **latest** (with GHA layer cache). |

The actual rollout is **pull-based** — `cd.yml` stops at "image pushed". It never pushes to the box
(the box is an intermittent WSL2 host; a push that assumes a runner is always online would be
fragile).

## GitHub configuration

| Kind | Name | Purpose |
|------|------|---------|
| Variable | `CD_ENABLED` | Set to `true` (Settings → Secrets and variables → Actions → **Variables**) to enable CD. Absent/`false` ⇒ green no-op. |
| Token | `GITHUB_TOKEN` | Built-in; `cd.yml` declares `permissions: packages: write` so it can push to GHCR. No PAT needed for same-repo push. |

Secrets reused from `live-judge.yml` (`CASEBOARD_LLM_PROVIDER`, `GOOGLE_CLOUD_PROJECT`,
`GOOGLE_CREDENTIALS`) are **runtime** config for the engine on the box — they are *not* used by the
image build (nothing private is baked in).

## One-time box setup (the self-hosted WSL2 host)

1. **Log in to GHCR** (once; a PAT with `read:packages`):
   ```bash
   echo "$GHCR_PAT" | docker login ghcr.io -u <github-username> --password-stdin
   ```
2. **Place `docker-compose.yml`** (from this repo) on the box, and a **`.env` beside it** with the
   runtime config. `GOOGLE_CLOUD_PROJECT` is required (compose fails fast without it):
   ```dotenv
   GOOGLE_CLOUD_PROJECT=your-gcp-project
   # optional overrides (defaults shown point at this machine's real data):
   # CASEBOARD_IMAGE=ghcr.io/michaelandrewlongo-rgb/neuro-caseboard:latest
   # CASEBOARD_CORPUS_DIR=/home/michael/textbook_pdfs
   # CASEBOARD_INDEX_DIR=/home/michael/neuro-textbook-rag/index
   # CASEBOARD_FIGURES_DIR=/home/michael/neuro-textbook-rag/assets/figures
   # CASEBOARD_ADC_FILE=/home/michael/.config/gcloud/application_default_credentials.json
   # NCBI_API_KEY=...        # optional; keyless PubMed is rate-limited
   ```
   > Host volume-source vars are namespaced `CASEBOARD_*` so they can't collide with the container
   > env the app reads (`CORPUS_DIR`/`INDEX_DIR`/`ASSETS_DIR` are fixed to the `/data/*` mount points).
   > The ADC default is an explicit absolute path — `${HOME}` is unset under some Docker frontends.
3. **The read-only mounts** (the corpus PDFs, the LanceDB index, the figure assets, and the ADC json)
   come from those paths; the index is queried in place. `/api/health` reports `corpus: true` once the
   index dir is mounted.
4. **Phone reachability is unchanged** — the container binds `0.0.0.0:8001`, but a LAN phone still
   needs WSL2 mirrored networking or the port-proxy. See [`SERVE_ON_PHONE.md`](SERVE_ON_PHONE.md). CD
   does not alter that.
5. **Schedule the pull-based rollout.** The box initiates; `cd-pull-deploy.sh` is idempotent (if the
   pulled digest is unchanged it just confirms health). Either a **cron** line:
   ```cron
   */10 * * * * cd /path/to/deploy && /path/to/repo/scripts/cd-pull-deploy.sh >> /var/log/caseboard-deploy.log 2>&1
   ```
   or a **systemd timer** (`caseboard-deploy.service` + `.timer`):
   ```ini
   # /etc/systemd/system/caseboard-deploy.service
   [Unit]
   Description=Pull + redeploy neuro-caseboard (health-gated, auto-rollback)
   [Service]
   Type=oneshot
   WorkingDirectory=/path/to/deploy          # dir holding docker-compose.yml + .env
   ExecStart=/path/to/repo/scripts/cd-pull-deploy.sh
   ```
   ```ini
   # /etc/systemd/system/caseboard-deploy.timer
   [Unit]
   Description=Run caseboard pull-deploy every 10 minutes
   [Timer]
   OnBootSec=2min
   OnUnitActiveSec=10min
   [Install]
   WantedBy=timers.target
   ```
   ```bash
   sudo systemctl enable --now caseboard-deploy.timer
   ```

## Health & rollback semantics

`cd-pull-deploy.sh` pulls the latest image, captures the currently-running image first, `docker
compose up -d`, then polls `/api/health` and gates on the top-level **`engine`** boolean:

- **`engine: true`** → keep the new image. (`synth`/`corpus`/`cards_index` may be `false` — those mean
  a credential or a volume isn't present, i.e. *honest degradation*, **not** a broken image. They never
  trigger a rollback.)
- **`engine: false` or `/api/health` unreachable** → the image itself is broken (bad deps / import
  error). Roll back: re-pin the prior image (`CASEBOARD_IMAGE=<prev>`) and `up -d` again.

Validate the decision logic any time with:
```bash
bash scripts/cd-pull-deploy.sh --selftest   # asserts keep / rollback / unreachable
```

## Manual rollback runbook

```bash
# 1. See what's running and what tags exist locally
docker compose ps
docker image ls 'ghcr.io/michaelandrewlongo-rgb/neuro-caseboard'

# 2. Pin a known-good version (or git sha) and redeploy
CASEBOARD_IMAGE=ghcr.io/michaelandrewlongo-rgb/neuro-caseboard:v0.1.0 docker compose up -d

# 3. Confirm the engine is back
curl -s localhost:8001/api/health | python3 -m json.tool   # expect "engine": true
```
GHCR keeps every `version` and `sha` tag, so any prior build is always pinnable. To stop serving:
`docker compose down`.

## Caveat: read-only index

The index is mounted `:ro` and `/api/health` only checks that the index dir exists, so it reports
`corpus: true` on mount. If a future LanceDB version needs to write a lock/version file at query time
under a read-only mount, switch that one volume to `:rw` (or give it a writable `tmpfs` for locks);
keep everything else read-only.
