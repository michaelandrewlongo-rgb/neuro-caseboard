# Design — WS-6: Keyed nightly live blind-judge CI job

- **Date:** 2026-06-16
- **Status:** Approved (locked by LOOP_PROMPT §7 WS-6); implementation complete
- **Branch:** `worktree-loop+output-quality`
- **Loop:** Output-Quality (`caseboard case`), Pass 6 of 6

## 1. Context & problem

The live blind judges (`eval/live_text_judge.py`, `eval/live_image_judge.py`) are the real quality
signal, but they run by hand and need a credentialed LLM + vision provider — so the loop's
text/image gains (WS-2 corpus `[n]`, WS-3 completeness, WS-4 the real-anatomy plate) have been graded
**DEFERRED**. WS-6 wires them as a keyed, non-required workflow so quality is tracked every loop, not
by hand — without ever blocking a PR.

## 2. Decisions

- **Modeled on `optional-integration.yml`:** `workflow_dispatch` + a nightly `schedule` cron,
  `permissions: contents: read`, secrets-gated. It is **never** required and **never** runs in
  `ci.yml`.
- **No-ops cleanly without secrets.** A first `gate` step checks `CASEBOARD_LLM_PROVIDER` +
  `GOOGLE_CLOUD_PROJECT`; if absent it sets `configured=false` and every later step is conditioned on
  `configured == 'true'` → a green, do-nothing job. (The judges themselves return exit 2 when
  unconfigured; the gate means that path is never reached on a hosted runner without secrets.)
- **Runs on the held-out `eval` split.** The judges take `--ids`; the workflow computes the eval-split
  ids from `eval/cases.json` (`split == "eval"`) and passes them — **no source change to the
  judges** (LOOP_PROMPT §7).
- **Budget + artifacts.** The image judge keeps its `--budget 3.0` hard-stop; both judges' dated
  reports upload via `actions/upload-artifact@v5`.
- **`eval/LIVE_BASELINE.json` is informational.** It records the prior loop's measured live scores +
  this loop's targets; it never blocks a PR (the offline `quality_gate.py` is the hard bar). Measured
  numbers are backfilled after a keyed run.

## 3. Detailed design (files)

- `.github/workflows/live-judge.yml` (new): the gated job above (vertex install `.[dev,vertex]`, ADC
  auth via `google-github-actions/auth@v2` + `GOOGLE_CREDENTIALS`, eval-id computation, text + image
  judges with `--tag nightly`, artifact upload).
- `eval/LIVE_BASELINE.json` (new): text {coverage, overall, accuracy, red-flag bleed} + image
  {overall, pass, side/level, corridor, structures-at-risk} as `{prior, target}` pairs.
- `docs/ci.md`: a "Keyed nightly workflow — live-judge.yml" section (how to run, secrets, where
  reports land, local-equivalent commands).

## 4. Acceptance criteria (LOOP_PROMPT §7)

- `live-judge.yml` exists, is `workflow_dispatch`able + scheduled, secrets-gated, and no-ops
  gracefully without secrets (both judges already exit cleanly when unconfigured; the gate makes the
  whole job a clean no-op).
- `docs/ci.md` documents how to run it and where reports land; `LIVE_BASELINE.json` committed.
- Required CI (`ci.yml`) unchanged; 0 regressions.

## 5. Testing strategy

No source changes → no new unit tests. Validate: the workflow is valid YAML; the eval-id snippet
yields the 18 eval ids; the skip path is structurally a no-op (every judge step gated on
`configured == 'true'`); `ci.yml` untouched; the full offline suite is unchanged (475/1).

## 6. EVAL

This *is* the live-eval delivery: a keyed run executes `live_text_judge.py` +
`live_image_judge.py --backend vertex` on the eval split. Targets (tracked in `LIVE_BASELINE.json`):
text coverage ≥ 85%, overall ≥ 8.6/10, accuracy ≥ 8/10; image overall ≥ 8/10, pass ≥ 11/12, side/level
12/12, corridor 9–10 preserved. The keyed numbers are backfilled when credentials are available.

## 7. Risks

- **Cannot validate the keyed path here** (no provider secrets). Mitigation: the skip path is
  validated; the judge invocations mirror the documented manual commands; the image judge's budget
  hard-stop bounds cost.
- **`on:` YAML boolean quirk** (PyYAML parses bare `on:` as `True`). Mitigation: matches the repo's
  existing `ci.yml` / `optional-integration.yml` convention; GitHub's own parser handles it.

## 8. Out of scope

Making the live judge a required gate (it is explicitly informational); any source change to the
judges; backfilling measured live numbers (needs credentials).
