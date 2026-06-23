# Plan — P3 #10: loading-state leaks (honest, monotonic step checklist)

**Three defects, one root cause.** Both loaders (`AskLoader`, `PipelineLoader`) cycle a SINGLE status line
on a 3200ms timer with `setI((p) => (p + 1) % steps.length)`:
1. **"Vertex" leak** — `AskLoader` STEP `"Synthesizing a cited answer · Vertex…"` exposes the internal
   provider name in the UI.
2. **Backward-cycling text** — the modulo **wraps**, so after the last stage it jumps back to the first
   ("Synthesizing…" → "Searching…"), reading as progress going backwards.
3. **Blank labels mid-run** — `BlurText key={i}` re-mounts every cycle and animates from invisible, so the
   single line flashes blank between stages.

**Fix (the backlog's "persistent step checklist tied to real progress"):** replace the single cycling
line with a CHECKLIST that advances **monotonically** (clamp, never wrap) and shows every stage at once —
earlier stages ✓done, current ● active, later ○ pending. Labels are static text (never blank); the order
never reverses; the provider name is gone.

**Honesty note:** the backend Ask/Build call is a single request with no per-stage progress events, so the
checklist is a *timed* approximation, not true telemetry — but it is HONEST: it never goes backward, never
marks a later stage done before an earlier one, and holds on the final stage until the response actually
arrives (rather than looping). True per-stage progress would need backend streaming — out of scope; noted.

---

- [x] **Step 1 — Pure step-state helpers + shared checklist, both loaders monotonic (frontend only)**
  - `web/src/lib/loaderSteps.ts` (NEW, pure, no React):
    - `advanceStep(current: number, total: number): number` = `Math.min(current + 1, Math.max(0, total - 1))`
      — monotonic clamp; at the last step it stays (never wraps to 0).
    - `type StepState = "done" | "active" | "pending"`.
    - `stepStates(total: number, current: number): StepState[]` — index `< current` → "done",
      `=== current` → "active", `> current` → "pending".
  - `web/src/lib/loaderSteps.test.ts` (NEW): `advanceStep` clamps at `total-1` and never returns 0 after
    the last step (the anti-backward guard); `stepStates(4, 2)` → `[done, done, active, pending]`; edge
    `stepStates(n, 0)` all-but-first pending; `advanceStep(total-1, total) === total-1`.
  - `web/src/components/StepChecklist.tsx` (NEW): presentational — `({ steps, current }: { steps: string[];
    current: number })` maps `stepStates` to rows: a state marker (✓ done / ● active with the existing
    pulse / ○ pending, dim) + the **static** step label (always rendered → never blank). Done rows
    slightly dimmed, active row full-strength, pending rows muted. `aria-hidden` on the decorative
    markers; the loaders keep their existing `sr-only` summary line.
  - `web/src/components/PipelineLoader.tsx`: timer uses `advanceStep` (not `% steps.length`); render
    `<StepChecklist steps={steps} current={i} />` in place of the single BlurText line. Add an optional
    `eyebrow?: string` (default `"Processing · Pipeline"`) and `srText?: string` prop so `AskLoader` can
    reuse it. Keep shimmer bars + estimate.
  - `web/src/components/ask/AskLoader.tsx`: drop the local cycling/BlurText; define
    `ASK_STEPS` WITHOUT "· Vertex" (`"Synthesizing a cited answer…"`), and render
    `<PipelineLoader steps={ASK_STEPS} estimate="Usually 30–80 seconds — retrieval, citation-grounded
    synthesis, and a live literature lookup." eyebrow="Ask · Corpus Retrieval" srText="Working on your
    answer — searching the corpus, synthesizing a cited answer, and scanning recent literature." />`.
    (Consolidates the two near-identical loaders; deletes the duplicated cycling logic.)
  - **Verify:** `npm --prefix web run test` (incl new loaderSteps spec) + `npm --prefix web run build`
    + `npm --prefix web run lint`.

**Non-regression:** reduced-motion guards (pulse / animate-pulse disabled) and the `sr-only` announcements
are preserved; no clinical content animates; the loaders are pure presentation — no data/engine change.
Scrubbing "Vertex" removes an infra-leak, consistent with the honest-surface invariant.
