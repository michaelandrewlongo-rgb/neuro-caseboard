# CI Docker Smoke + Auto-Deploy Design

**Date:** 2026-06-30
**Branch:** to be implemented on a new branch off master

## Goal

Close the gap between "CI green" and "container actually starts": add a `docker-smoke` required CI
job that builds the image and probes `/api/health` on every PR, then flip CD to auto-deploy on
every master merge instead of requiring a manual tag push.

## Context

Current CI (`ci.yml`) has three jobs: `sanity`, `test`, `package`. None of them build or run the
Docker image. A merge could be CI-green but break the container via a broken `Dockerfile`, a missing
dependency in the `[vertex,models]` serve extras, or a startup import error. The CD workflow
(`cd.yml`) was tag-triggered (`v*`) as a manual safety valve for exactly this reason. Once the
smoke job closes the gap, the tag gate is redundant.

## Design

### 1. New `docker-smoke` job in `ci.yml`

Runs in parallel with `test` and `package` on every PR and every push to `master`.

**Steps:**

1. `docker/setup-buildx-action@v3` — enables BuildKit.
2. `docker/build-push-action@v6` with `push: false`, `load: true`, `cache-from/to: type=gha,mode=max` — builds the image into the local Docker daemon using the GitHub Actions layer cache. No credentials needed (no push).
3. `docker run -d` with placeholder env vars (see below), no data volumes. The server will start, fail to find an index, and report `corpus: false` — that is expected and not a failure.
4. Poll `http://localhost:8001/api/health` every 5 s for up to 60 s. Gate on `engine: true` (same predicate as `cd-pull-deploy.sh`). On success: `docker stop`, exit 0. On timeout: dump `docker logs`, exit 1.

**Placeholder env vars (no real secrets needed):**

```
SYNTH_PROVIDER=openrouter
OPENROUTER_API_KEY=ci-smoke-placeholder
OPENROUTER_MODEL=z-ai/glm-5.2
GOOGLE_CLOUD_PROJECT=ci-smoke
EMBED_DEVICE=cpu
GPU_GUARD=false
```

`GOOGLE_APPLICATION_CREDENTIALS` is intentionally omitted — the ADC file isn't needed for the
health check, and a missing file is better than `/dev/null` (which causes the Google SDK to error
on parse, not silently degrade).

**Expected healthy response (no volumes mounted):**

```json
{ "engine": true, "synth": false, "corpus": false, "cards_index": false, "ncbi_key": false }
```

`engine: true` is the only gate. `synth/corpus/cards_index` being false just means secrets and
data aren't present in CI — that is correct and expected.

**Cache behavior:** `type=gha` is repo-scoped and readable across workflows. Once `docker-smoke`
warms the layer cache on a PR run, the CD `build-push` job on the subsequent master-merge push
hits the same cache. First run: ~20 min (cold). Subsequent runs: ~2–4 min (stable layers).

### 2. `cd.yml` trigger change

Change from tag-triggered to branch-triggered:

```yaml
on:
  push:
    branches: [master]
  workflow_dispatch:
    inputs:
      version:
        description: "Version tag/label to build/push (e.g. v0.2.0)"
        required: true
```

Version resolution in `build-push`: when triggered by a branch push, `GITHUB_REF_NAME` is
`master` — use that as the version label. The image is still tagged with the git SHA for
rollback pinning, and `latest` for the pull-deploy timer. The `workflow_dispatch` path is
unchanged for manual versioned releases.

Tags pushed per merge:
- `ghcr.io/michaelandrewlongo-rgb/neuro-caseboard:master`
- `ghcr.io/michaelandrewlongo-rgb/neuro-caseboard:<sha>`
- `ghcr.io/michaelandrewlongo-rgb/neuro-caseboard:latest` (what the cron pull-deploy tracks)

### 3. Branch protection update (manual step post-merge)

After the PR merges and the new job name appears in GitHub, add
`docker smoke (build + /api/health)` as a 5th required status check in
Settings → Branches → master → require status checks.

## What this closes

| Gap | Closed by |
|-----|-----------|
| Broken Dockerfile (syntax, COPY error) | `docker-smoke` build step |
| Missing dep in `[vertex,models]` serve extras | `docker-smoke` build step |
| Import error that only surfaces at server startup | `docker-smoke` health probe |
| Manual tag required to deploy | CD branch trigger |

## What this does NOT close

- Retrieval correctness (index not available in CI — covered by offline `quality_gate.py`)
- Credential validity (ADC/OpenRouter keys are placeholders in CI)
- Data-volume mount correctness (no corpus/index mounted in smoke)

These gaps are acceptable: the index is a static asset tested by the quality gate; credentials are
environment concerns, not code concerns.

## Files changed

- `.github/workflows/ci.yml` — add `docker-smoke` job
- `.github/workflows/cd.yml` — change trigger + version resolution

No other files change.
