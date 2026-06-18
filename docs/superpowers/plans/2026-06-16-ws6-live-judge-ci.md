# Plan — WS-6: Keyed nightly live blind-judge CI job

Spec: `docs/superpowers/specs/2026-06-16-ws6-live-judge-ci-design.md`. CI config + baseline + docs
(no source changes → no new unit tests; validate structurally).

## Tasks

1. **Verify the judges' skip behavior.** Both `live_text_judge.py` / `live_image_judge.py` return
   exit 2 when unconfigured → the workflow must GATE, not run-and-fail. (Confirmed.)
2. **Workflow.** `.github/workflows/live-judge.yml`: `workflow_dispatch` + nightly cron,
   `permissions: contents: read`, secrets-gated `gate` step → every judge step `if configured`,
   eval-id computation from `cases.json`, text + image judges (`--budget`, `--tag nightly`), artifact
   upload (`upload-artifact@v5`).
3. **Baseline.** `eval/LIVE_BASELINE.json` — prior measured + this loop's targets (informational).
4. **Docs.** `docs/ci.md` "Keyed nightly workflow" section.
5. **Verify.** Valid YAML; eval-id snippet → 18 ids; skip path is a clean no-op; `ci.yml` unchanged;
   full offline suite unchanged (475/1); no merge markers.
6. **Record.** LOOP_LOG line + loop-complete summary.

## Non-goals
Making the live judge required; source changes to the judges; backfilling keyed numbers.
