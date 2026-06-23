# Plan — P1 #4: collapse empty Dossier hero panels (reclaim above-the-fold space)

**Goal:** The Dossier hero is a 3-col "Telemetry grid" `[Risk Topology | Evidence Integrity | Planning
Metrics]`. Risk Topology (`Build.tsx` ~361-391, hardcoded "No risk-topology data from engine") and
Planning Metrics (`<PlanningMetrics/>` at ~485, renders its own "Not available") have NO backing data
in `BuildResponse` and never will until the engine emits those fields — so 2/3 of prime space is dead
boxes. Fix = COLLAPSE/HIDE them when empty (the bug's stated alternative), reflowing to show the real
Evidence Integrity panel. **Do NOT fabricate** risk/planning numbers — clinical estimates with no
ground truth would violate the project's honest-grounding invariant (and the components' own comments
say so). Forward-compatible: panels reappear if the engine ever populates them.

---

- [x] **Step 1 — Collapse empty hero panels + reflow the telemetry grid (frontend only)**
  - `web/src/components/build/PlanningMetrics.tsx`: when `!hasAnyData`, `return null` instead of
    rendering the "Not available / No planning data from engine" box. Keep the data-present rendering
    unchanged (forward-compat). Export a pure `planningHasData(props): boolean` for testing + reuse.
  - `web/src/lib/heroPanels.ts` (NEW, pure): `heroGridColumns(visible: number): string` mapping the
    count of rendered hero panels → a CSS `gridTemplateColumns` string (3 → "1.15fr 1fr 1.05fr";
    2 → "1fr 1fr"; 1 → "minmax(0, 460px)" so the lone Evidence panel doesn't stretch full-width;
    0 → "" ). Small, deterministic, unit-testable.
  - `web/src/pages/Build.tsx`:
    - Compute `showRisk` (false until `BuildResponse` carries risk-topology data — no such field today,
      so a `const showRisk = false` gated on a future field is fine; the point is the block no longer
      renders) and `showPlanning = planningHasData(...)` (also false today).
    - Render the Risk Topology block only when `showRisk`; render `<PlanningMetrics/>` only when
      `showPlanning` (or let it self-collapse via its `null` return — but to also reflow the grid,
      gate it here). Always render Evidence Integrity (real data).
    - Set the grid's `gridTemplateColumns` from `heroGridColumns(count of visible panels)` so the
      remaining panel(s) fill the space instead of leaving empty columns. Current state → only Evidence
      Integrity renders, constrained width, left-aligned; no dead boxes above the fold.
  - `web/src/lib/heroPanels.test.ts` (NEW): assert the column template for counts 0/1/2/3 and that
    `planningHasData` is false for all-undefined props, true when any metric is set.
  - Keep the existing web suite green; `npm --prefix web run build` (tsc) must pass.
  - **Verify:** `npm --prefix web run test` (incl. new spec) + `npm --prefix web run build`.

**Note:** the backlog listed `compile.py`/`model.py` as targets for the "populate from engine" option;
that path is intentionally NOT taken (no honest data to populate; fabrication is unsafe in a clinical
tool). This slice is the "collapse when empty" option, frontend-only.

---

## Review Findings (PR #59, slice-4 increment 6) — VERDICT: APPROVE (no MUSTs)

Reviewer verified empirically: vitest 31 pass, build green, gating consistent (visiblePanels matches
rendered blocks), planningHasData both branches correct, heroGridColumns edge cases safe, no contrast
regression (panels on dark surface, no text-primary/success/amber), honesty invariant intact.

- [x] review: [SHOULD] `PlanningMetrics.tsx` exporting `planningHasData` (a non-component value) trips
  `react-refresh/only-export-components` (lint, not a CI gate; HMR/DX only). Fix = move `planningHasData`
  into `heroPanels.ts` (the existing pure-helper module) and repoint the test import. Cleaner than an
  eslint-disable; consolidates both layout helpers. DONE (2f4b960): `npm run lint` now clean; vitest 31,
  build green. heroPanels.ts gained a structural `PlanningFields` interface so it needs no React import.
- [x] review: [NIT] Build.tsx comments (369/381/506) + PlanningMetrics.tsx:288 say panels "reappear
  automatically once its gate flips true" — but both gates are hardcoded constants (`showRisk=false`,
  `planningHasData({})`), so nothing flips without a code edit. Reword to "reappears once a real field is
  wired into this gate" so the placeholder isn't implied to be live-connected. DONE (2f4b960).
