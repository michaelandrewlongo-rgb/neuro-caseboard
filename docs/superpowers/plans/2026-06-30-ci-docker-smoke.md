# CI Docker Smoke + Auto-Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a required `docker-smoke` CI job that builds the image and probes `/api/health` on every PR, then flip CD to auto-deploy on every master merge.

**Architecture:** Two YAML file edits — a new parallel job appended to `ci.yml`, and a trigger change + header update in `cd.yml`. No Python, no new scripts, no new dependencies.

**Tech Stack:** GitHub Actions, `docker/setup-buildx-action@v3`, `docker/build-push-action@v6`, bash, Python (health-probe JSON parse, already on ubuntu-latest).

## Global Constraints

- Do not touch `ci.yml`'s existing `sanity`, `test`, `package` jobs — append only.
- `docker-smoke` must run in parallel with `test` and `package` (no `needs:` on those jobs).
- Gate only on `engine: true` — `synth/corpus/cards_index` being false in CI is expected and correct.
- No real secrets in CI (placeholders only); no data volumes mounted.
- `cd.yml` keeps `workflow_dispatch` for manual versioned releases.
- Working branch: create `ci/docker-smoke` off master.

---

### Task 1: Add `docker-smoke` job to `ci.yml`

**Files:**
- Modify: `.github/workflows/ci.yml` (append job after `package`)

**Interfaces:**
- Produces: required status check named `docker smoke (build + /api/health)` visible in GitHub branch protection

- [ ] **Step 1: Validate current YAML parses cleanly (baseline)**

```bash
python3 -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text()); print('OK')"
```

Expected: `OK`

- [ ] **Step 2: Append the `docker-smoke` job to `ci.yml`**

Open `.github/workflows/ci.yml`. At the very end of the file (after the closing lines of the `package` job), add:

```yaml

  # ---------------------------------------------------------------------------
  # PROVES: the Dockerfile builds and the server starts. Gates on engine:true
  # from /api/health — the same predicate cd-pull-deploy.sh uses for rollback.
  # No real secrets needed; no data volumes mounted. corpus/synth/cards being
  # false is expected (no index in CI) and is NOT a failure.
  # ---------------------------------------------------------------------------
  docker-smoke:
    name: docker smoke (build + /api/health)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: docker/setup-buildx-action@v3
      - name: Build image (no push)
        uses: docker/build-push-action@v6
        with:
          context: .
          push: false
          load: true
          tags: neuro-caseboard:smoke
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - name: Smoke — boot container + probe /api/health engine:true
        run: |
          docker run -d --name smoke -p 8001:8001 \
            -e SYNTH_PROVIDER=openrouter \
            -e OPENROUTER_API_KEY=ci-smoke-placeholder \
            -e OPENROUTER_MODEL=z-ai/glm-5.2 \
            -e GOOGLE_CLOUD_PROJECT=ci-smoke \
            -e EMBED_DEVICE=cpu \
            -e GPU_GUARD=false \
            neuro-caseboard:smoke
          for i in $(seq 1 12); do
            sleep 5
            r=$(curl -fsS http://localhost:8001/api/health 2>/dev/null || true)
            echo "attempt $i: $r"
            if echo "$r" | python3 -c \
              'import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get("engine") is True else 1)' \
              2>/dev/null; then
              echo "smoke passed"
              docker stop smoke
              exit 0
            fi
          done
          echo "::error::smoke test timed out (engine never true)"
          docker logs smoke
          docker stop smoke || true
          exit 1
```

- [ ] **Step 3: Validate the edited YAML parses cleanly**

```bash
python3 -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text()); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Verify job name matches what branch protection will see**

The job's `name:` field must match the required status check string exactly. Confirm it reads:

```
docker smoke (build + /api/health)
```

That is the string you will enter in GitHub Settings → Branches → master → require status checks.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add docker-smoke required job (build + /api/health gate)"
```

---

### Task 2: Flip `cd.yml` to master-branch-triggered

**Files:**
- Modify: `.github/workflows/cd.yml` (trigger block + header comment)

**Interfaces:**
- Consumes: nothing from Task 1
- Produces: CD auto-fires on every master push; version label becomes `master` (SHA tag preserved for rollback pinning); `latest` tag unchanged (what `cd-pull-deploy.sh` tracks)

- [ ] **Step 1: Validate current YAML parses cleanly (baseline)**

```bash
python3 -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/cd.yml').read_text()); print('OK')"
```

Expected: `OK`

- [ ] **Step 2: Replace the `on:` trigger block and update the header comment**

In `.github/workflows/cd.yml`, replace the top comment + `on:` block:

Old:
```yaml
# Runs AFTER the required CI is green — it does not re-run or duplicate ci.yml's PR gate. Triggers
# only on a version tag (v*) or a manual dispatch. Builds the SPA + serve image and pushes it to
# GHCR tagged by version AND git sha (+ latest). Secret/variable-gated: with CD_ENABLED unset it is
# a clean, green no-op (mirrors live-judge.yml). The actual rollout is PULL-based — the self-hosted
# box's cd-pull-deploy.sh timer picks up the new image (see docs/cd.md); CD does not push to the box.

on:
  push:
    tags: ["v*"]
  workflow_dispatch:
    inputs:
      version:
        description: "Version tag to build/push (e.g. v0.2.0)"
        required: true
```

New:
```yaml
# Runs AFTER the required CI is green — it does not re-run or duplicate ci.yml's PR gate. Triggers
# on every push to master (auto-deploy) or a manual dispatch (versioned release). Builds the SPA +
# serve image and pushes to GHCR tagged by sha + latest (branch push) or version + sha + latest
# (dispatch). Secret/variable-gated: with CD_ENABLED unset it is a clean, green no-op. The actual
# rollout is PULL-based — the self-hosted box's cd-pull-deploy.sh timer picks up the new image
# (see docs/cd.md); CD does not push to the box.

on:
  push:
    branches: [master]
  workflow_dispatch:
    inputs:
      version:
        description: "Version label to build/push (e.g. v0.2.0)"
        required: true
```

- [ ] **Step 3: Validate the edited YAML parses cleanly**

```bash
python3 -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/cd.yml').read_text()); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/cd.yml
git commit -m "ci: flip CD trigger to master-branch auto-deploy (tag gate no longer needed)"
```

---

### Task 3: PR, CI verification, and branch protection

**Files:** None — this task is GitHub UI + observation.

- [ ] **Step 1: Push branch and open PR**

```bash
git push -u origin ci/docker-smoke
gh pr create --title "ci: docker-smoke required gate + auto-deploy on master merge" --body "$(cat <<'EOF'
## Summary
- Adds `docker-smoke` required CI job: builds the image, boots it with placeholder env vars, polls `/api/health` for `engine: true` within 60 s
- Flips `cd.yml` trigger from `v*` tags → every master push (auto-deploy); cron pull-deploy on the box is unchanged
- First run will be cold (~20 min Docker build); layer cache warms for subsequent PRs

## Test plan
- [ ] All 4 existing CI jobs pass (sanity, test ×2, package)
- [ ] New `docker smoke (build + /api/health)` job passes — check Actions log for `smoke passed`
- [ ] CD `build + push image to GHCR` job fires after merge (not before — CD only triggers on master, not PRs)
- [ ] After merge: add `docker smoke (build + /api/health)` as 5th required status check in GitHub Settings → Branches → master → Require status checks
EOF
)"
```

- [ ] **Step 2: Watch CI — confirm smoke job passes**

```bash
gh run watch --repo michaelandrewlongo-rgb/neuro-caseboard
```

Look for `docker smoke (build + /api/health)` in the job list. Check its log for:
```
smoke passed
```

If it times out, check `docker logs smoke` in the Actions output for startup errors.

- [ ] **Step 3: Merge**

```bash
gh pr merge --squash
```

- [ ] **Step 4: Confirm CD auto-fires on the master push**

```bash
gh run list --repo michaelandrewlongo-rgb/neuro-caseboard --limit 5
```

You should see a `CD` run triggered by `push` to `master` (not a tag). It will build and push `:master`, `:<sha>`, and `:latest` to GHCR.

- [ ] **Step 5: Add the required status check in GitHub UI**

Go to: `https://github.com/michaelandrewlongo-rgb/neuro-caseboard/settings/branches`

Edit the `master` protection rule → "Require status checks to pass before merging" → search for and add:

```
docker smoke (build + /api/health)
```

This check only appears in the search after it has run at least once (Step 2 above satisfies this).

- [ ] **Step 6: Verify protection rule**

Open any future PR — confirm the checks list shows 5 required checks including the new docker smoke check.
