# Ask-Pathway UX Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix five UX defects found in a live pilot of the Ask pathway — junk (non-anatomical) figures ranking #1, a dishonest/frozen-feeling loader, a redundant Citation-Audit donut above the answer, two competing corpus-search inputs, and a wasteful re-disambiguation on variant picks.

**Architecture:** Three-layer engine (`caseprep/` → `neuro_core/` retrieval+figures → `neuro_caseboard/` orchestration) behind a FastAPI wrapper (`api/server.py`) and a React SPA (`web/`). Backend logic changes land in `neuro_core/figure_guards.py` and the disambiguation seam (`neuro_core/query.py` + `neuro_caseboard/qa.py`), threaded through `api/server.py`. Web changes follow the repo's established pattern: pure logic is extracted to `web/src/lib/*.ts` and unit-tested with vitest (the harness is node-only — no jsdom/testing-library), while the `.tsx` wiring is verified by `npm run build` (tsc typecheck).

**Tech Stack:** Python 3 + pytest (LanceDB hybrid retrieval, dataclasses); FastAPI + Pydantic; React 19 + TypeScript + Vite + Tailwind v4; vitest 4.

## Global Constraints

- **Topic-agnostic:** no hardcoded clinical phrases or book names in any logic (especially the figure filter) — filters must be driven by generic caption-text/metadata signals only.
- **Every logic change ships with a test** (pytest under the harness paths, or vitest).
- **Web contrast (two-token model):** colored TEXT on light surfaces must use the `-ink` tokens (e.g. `text-primary-ink`), never `text-primary` / `text-success` / `text-amber` (those are for `bg-*` / `border-*` fills only).
- **Python tests run under:** `cd <worktree> && PYTHONPATH=vendor/caseprep python3 -m pytest -q tests/neuro_core tests/test_qa.py tests/test_retrieve.py tests/test_pipeline.py` (full suite is ~17 min — never invoke it; never pytest-xdist). Scope to single files during the loop.
- **Web tests/build:** `cd <worktree>/web && npm run test` (vitest) and `npm run build` (tsc typecheck + vite). `node_modules` is symlinked and present. There is NO jsdom/testing-library — back web changes with pure-function vitest specs in `web/src/lib/`.
- **Use existing test patterns:** match neighboring tests in `tests/neuro_core/` and `web/src/lib/*.test.ts`.
- **Worktree:** all work happens in `/home/michael/PROJECTS/neuro-caseboard/.project-loop/wt` on branch `loop/ask-ux-fixes`.

---

### Task 1: Junk-figure filter (non-anatomical title/divider/blank pages)

A book TITLE PAGE ranked #1 (and was the first enlargeable figure) on "surgical approaches to a vestibular schwannoma"; its own Gemini caption read *"Title page with no anatomical structures, surgical instruments, or patient positioning shown."* The signal is already in the caption. Add a **topic-agnostic** guard that drops figures whose caption marks the page as a non-anatomical publishing artifact, driven only by generic caption text — never a clinical phrase or book name. Wire it into `figure_offtarget` at the very top so it runs on BOTH the Q&A (`guards="strict"`) and board (`guards="full"`) paths and regardless of topic; `Engine._collect_figures` already calls `figure_offtarget(..., guards="strict")` on the fused figure output, so this is the single choke point for the Ask lane.

**Files:**
- Modify: `neuro_core/figure_guards.py` (add `nonanatomical_figure`; call it at the top of `figure_offtarget`, currently at lines 145-217)
- Test: `tests/neuro_core/test_figure_guards.py`

**Interfaces:**
- Produces: `nonanatomical_figure(caption: str) -> bool` — True for a non-anatomical title/divider/blank/contents page or an explicit "no anatomy shown" caption.
- `figure_offtarget(caption, topic, book="", context="", *, guards="full") -> bool` gains an additional reason to return True (signature unchanged).

- [x] **Step 1: Write the failing test**

Append to `tests/neuro_core/test_figure_guards.py` (update the existing top import to also import `nonanatomical_figure`):

```python
from neuro_core.figure_guards import nonanatomical_figure


def test_nonanatomical_figure_drops_title_divider_blank_pages():
    # the exact pilot caption: a title page ranked #1 on a vestibular-schwannoma query
    assert nonanatomical_figure(
        "Title page with no anatomical structures, surgical instruments, "
        "or patient positioning shown") is True
    assert nonanatomical_figure("Part III divider page") is True
    assert nonanatomical_figure("This page intentionally left blank") is True
    assert nonanatomical_figure("Table of contents") is True
    assert nonanatomical_figure("Copyright page") is True
    # a real operative-anatomy caption is kept
    assert nonanatomical_figure(
        "Left retrosigmoid exposure of the cerebellopontine angle with the "
        "facial and vestibulocochlear nerves") is False
    # a caption that mentions 'structures' POSITIVELY is kept (no absence claim)
    assert nonanatomical_figure(
        "Neurovascular structures of the cerebellopontine angle are shown") is False


def test_figure_offtarget_drops_nonanatomical_page_topic_agnostically():
    junk = ("Title page with no anatomical structures, surgical instruments, "
            "or patient positioning shown")
    # dropped on BOTH the Q&A (strict) and board (full) paths, for unrelated topics
    assert figure_offtarget(junk, "surgical approaches to a vestibular schwannoma",
                            guards="strict") is True
    assert figure_offtarget(junk, "C1-C2 atlantoaxial fixation", guards="full") is True
    # a genuine CPA plate on the same question is still kept
    assert figure_offtarget(
        "Left cerebellopontine angle: AICA between the facial and vestibulocochlear nerves",
        "surgical approaches to a vestibular schwannoma", guards="strict") is False
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt && PYTHONPATH=vendor/caseprep python3 -m pytest -q tests/neuro_core/test_figure_guards.py::test_nonanatomical_figure_drops_title_divider_blank_pages`
Expected: FAIL with `ImportError: cannot import name 'nonanatomical_figure' from 'neuro_core.figure_guards'` (collection error).

- [x] **Step 3: Write minimal implementation**

In `neuro_core/figure_guards.py`, add these module-level constants and function immediately before `def figure_offtarget(` (after the `_SPINE_BOOKS` / `_CRANIAL_BOOKS` block):

```python
# Topic-agnostic publishing-artifact guard. Non-anatomical front/divider/blank pages
# (title pages, section dividers, tables of contents, copyright/dedication pages) and
# captions that explicitly state no anatomy/instruments are shown get retrieved and can
# rank #1 on a figure query. The signal is generic CAPTION TEXT — never a clinical phrase
# or a book name — so this stays fully topic-agnostic.
_NONANATOMICAL_PAGE = (
    "title page", "half title", "table of contents", "list of contents",
    "copyright page", "dedication page", "frontispiece", "list of contributors",
    "section divider", "part divider", "chapter divider", "divider page",
    "intentionally left blank", "blank page", "this page intentionally",
)
# An explicit ABSENCE claim: "no <anatomy/structures/instruments/landmarks/positioning/
# content> ... shown/depicted/present/visible/illustrated/identified". The leading \bno\b
# word-boundary avoids matching substrings like "neurovascular" or "anosmia".
_NO_CONTENT_SHOWN = re.compile(
    r"\bno\b[^.]*\b(?:anatom\w*|structures?|instruments?|landmarks?|positioning|content)\b"
    r"[^.]*\b(?:shown|depicted|present|visible|illustrated|identified)\b",
    re.IGNORECASE,
)


def nonanatomical_figure(caption: str) -> bool:
    """Topic-agnostic: True when a caption marks the page as a non-anatomical publishing
    artifact (title/divider/blank/contents/copyright page) or explicitly states it shows
    no anatomical/surgical content. Driven only by generic caption signals — never a
    clinical phrase or a book name."""
    cap = (caption or "").lower()
    if any(p in cap for p in _NONANATOMICAL_PAGE):
        return True
    return bool(_NO_CONTENT_SHOWN.search(cap))
```

Then add the call at the very top of `figure_offtarget`, immediately after the three `cap`/`top`/`bk` lowercasing lines and before the `if guards == "full" and any(x in cap for x in _DIAGNOSTIC_IMAGE):` check:

```python
    if nonanatomical_figure(caption):
        return True                          # non-anatomical title/divider/blank page (topic-agnostic)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt && PYTHONPATH=vendor/caseprep python3 -m pytest -q tests/neuro_core/test_figure_guards.py`
Expected: PASS (the two new tests plus all pre-existing guard tests stay green — the new check only adds a drop reason for artifact captions).

- [x] **Step 5: Commit**

```bash
cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt
git add neuro_core/figure_guards.py tests/neuro_core/test_figure_guards.py
git commit -m "feat(figures): drop non-anatomical title/divider/blank pages from the figure lane"
```

---

### Task 2: Loader honesty — correct estimate + live elapsed counter

The pilot measured real Ask latency at ~114s, but the loader promises "30–80 seconds" and reaches its final checklist step in ~13s (4 steps × 3200ms) then sits frozen ~100s. A prior loop (`docs/superpowers/plans/2026-06-23-loader-honesty.md`) already made the checklist **monotonic** (clamp, never wrap) and removed the "Vertex" leak — **do NOT undo that**. The two remaining gaps: (1) the wrong time estimate, and (2) the frozen feel. Fix by (a) correcting the copy to ~2 minutes, (b) adding a live elapsed-time stopwatch so the panel visibly advances every second, and (c) pacing the checklist steps over a longer interval so the final step is not reached in 13s.

**Files:**
- Modify: `web/src/lib/loaderSteps.ts` (add pure `formatElapsed`)
- Modify: `web/src/components/PipelineLoader.tsx` (live elapsed counter + optional `stepIntervalMs` prop)
- Modify: `web/src/components/ask/AskLoader.tsx` (honest estimate copy + paced interval)
- Test: `web/src/lib/loaderSteps.test.ts`

**Interfaces:**
- Consumes: `advanceStep`, `stepStates` (existing, unchanged).
- Produces: `formatElapsed(totalSeconds: number) -> string` ("M:SS"); `PipelineLoader` prop `stepIntervalMs?: number` (default 3200).

- [x] **Step 1: Write the failing test**

Append to `web/src/lib/loaderSteps.test.ts` (add `formatElapsed` to the existing import from `./loaderSteps`):

```typescript
import { formatElapsed } from "./loaderSteps"

describe("formatElapsed (live loader stopwatch)", () => {
  it("formats sub-minute as 0:SS with a zero-padded seconds field", () => {
    expect(formatElapsed(0)).toBe("0:00")
    expect(formatElapsed(7)).toBe("0:07")
  })
  it("rolls over into minutes", () => {
    expect(formatElapsed(83)).toBe("1:23")
    expect(formatElapsed(114)).toBe("1:54")
  })
  it("floors fractional seconds and clamps negatives to 0:00", () => {
    expect(formatElapsed(12.9)).toBe("0:12")
    expect(formatElapsed(-5)).toBe("0:00")
  })
})
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt/web && npx vitest run src/lib/loaderSteps.test.ts`
Expected: FAIL — `formatElapsed is not a function` / no matching export.

- [x] **Step 3: Write minimal implementation (pure helper)**

Append to `web/src/lib/loaderSteps.ts`:

```typescript
/** Format an elapsed-seconds count as M:SS for the live loader stopwatch (e.g. 83 -> "1:23").
    Floors fractional seconds and clamps negatives to "0:00". */
export function formatElapsed(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${r.toString().padStart(2, "0")}`
}
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt/web && npx vitest run src/lib/loaderSteps.test.ts`
Expected: PASS.

- [x] **Step 5: Wire the live counter + paced interval into PipelineLoader**

In `web/src/components/PipelineLoader.tsx`, update the import and component. Add `formatElapsed` to the loaderSteps import:

```typescript
import { advanceStep, formatElapsed } from "@/lib/loaderSteps"
```

Add the `stepIntervalMs` prop and a 1s elapsed ticker; replace the step-timer interval and the footer estimate paragraph:

```tsx
export default function PipelineLoader({
  steps,
  estimate,
  bars = 6,
  eyebrow = "Processing · Pipeline",
  srText,
  stepIntervalMs = 3200,
}: {
  steps: string[]
  estimate: string
  bars?: number
  eyebrow?: string
  srText?: string
  stepIntervalMs?: number
}) {
  const [i, setI] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((p) => advanceStep(p, steps.length)), stepIntervalMs)
    return () => clearInterval(t)
  }, [steps.length, stepIntervalMs])
  useEffect(() => {
    const t = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [])
```

Replace the existing footer paragraph (the `<p className="mt-5 font-mono text-xs text-muted-foreground" aria-hidden>{estimate}</p>`) with an estimate + live stopwatch row:

```tsx
      <p
        className="mt-5 flex items-center justify-between gap-3 font-mono text-xs text-muted-foreground"
        aria-hidden
      >
        <span>{estimate}</span>
        <span className="tnum shrink-0">Elapsed {formatElapsed(elapsed)}</span>
      </p>
```

(The stopwatch is `aria-hidden`; the existing `sr-only` summary remains the screen-reader announcement, so we don't spam assistive tech every second.)

- [x] **Step 6: Make the AskLoader estimate honest and pace the steps**

Replace the body of `web/src/components/ask/AskLoader.tsx` (`ASK_STEPS` stays as-is):

```tsx
export default function AskLoader() {
  return (
    <PipelineLoader
      steps={ASK_STEPS}
      estimate="Usually about 2 minutes — retrieval, citation-grounded synthesis, and a live PubMed lookup."
      eyebrow="Ask · Corpus Retrieval"
      srText="Working on your answer — searching the corpus, synthesizing a cited answer, and scanning recent literature. This usually takes about 2 minutes."
      stepIntervalMs={20000}
    />
  )
}
```

(20s pacing means the four steps span ~60s instead of ~13s, the final step stays `● active` (pulsing, never marked `✓` done early), and the live stopwatch keeps the panel visibly advancing for the full ~114s.)

- [x] **Step 7: Verify the full web harness and commit**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt/web && npm run test && npm run build`
Expected: vitest all-green (incl. the new `formatElapsed` block); build succeeds (no tsc errors).

```bash
cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt
git add web/src/lib/loaderSteps.ts web/src/lib/loaderSteps.test.ts \
        web/src/components/PipelineLoader.tsx web/src/components/ask/AskLoader.tsx
git commit -m "feat(ask-loader): honest ~2min estimate + live elapsed stopwatch, paced steps"
```

---

### Task 3: Result hierarchy — lead with the answer, collapse the redundant Citation Audit

The answer currently renders BELOW a large Citation-Audit donut that merely restates the status line directly above it ("29 CITATIONS · 17 TEXTBOOK CORPUS · 12 PUBMED LITERATURE"). Lead with the answer; remove the duplicate standalone status line; move the donut to a collapsed `<details>` BELOW the answer/sources, with a one-line summary that reuses the single `citationSummary` source of truth.

**Files:**
- Create: `web/src/lib/askLayout.ts`
- Create: `web/src/lib/askLayout.test.ts`
- Modify: `web/src/pages/Ask.tsx` (remove the top status-line + eager audit block; render a collapsed audit at the bottom of `ResultView`)

**Interfaces:**
- Consumes: `citationSummary(corpus, literature)` (existing).
- Produces: `auditSummaryLabel(corpus: number, literature: number) -> string` — the collapsed `<summary>` text.

- [x] **Step 1: Write the failing test**

Create `web/src/lib/askLayout.test.ts`:

```typescript
import { describe, it, expect } from "vitest"
import { auditSummaryLabel } from "./askLayout"

describe("auditSummaryLabel (collapsed Citation Audit summary)", () => {
  it("composes the lane-honest count line so there is ONE source of truth", () => {
    expect(auditSummaryLabel(17, 12)).toBe(
      "Citation audit — 29 citations · 17 textbook corpus · 12 PubMed literature")
  })
  it("handles a corpus-only response", () => {
    expect(auditSummaryLabel(16, 0)).toBe(
      "Citation audit — 16 citations from your textbook corpus")
  })
  it("handles an empty response", () => {
    expect(auditSummaryLabel(0, 0)).toBe("Citation audit — No citations in this response")
  })
})
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt/web && npx vitest run src/lib/askLayout.test.ts`
Expected: FAIL — cannot resolve `./askLayout` / no `auditSummaryLabel` export.

- [x] **Step 3: Write minimal implementation (pure helper)**

Create `web/src/lib/askLayout.ts`:

```typescript
import { citationSummary } from "@/lib/citationSummary"

/** The Citation Audit donut and the old standalone status line restated the SAME counts.
    We keep ONE source of truth (citationSummary) and surface it as the collapsed <details>
    summary BELOW the answer, so the result leads with the answer instead of the telemetry. */
export function auditSummaryLabel(corpus: number, literature: number): string {
  return `Citation audit — ${citationSummary(corpus, literature)}`
}
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt/web && npx vitest run src/lib/askLayout.test.ts`
Expected: PASS.

- [x] **Step 5: Re-order the Ask result (Ask.tsx)**

In `web/src/pages/Ask.tsx`:

1. Update imports — drop the direct `citationSummary` import, add `auditSummaryLabel`:

```tsx
import { CitationAudit } from "@/components/ask/CitationAudit"
import { auditSummaryLabel } from "@/lib/askLayout"
```

2. DELETE the entire eager top block that renders the status line + audit ABOVE the loader (the JSX currently guarded by `{resp?.kind === "answer" && !loading && (` … `)}` containing the `<p>` with `citationSummary(...)` and the `<div className="sm:max-w-md"><CitationAudit .../></div>`).

3. In `ResultView`, replace the `kind === "answer"` return block with one that leads with the answer and collapses the audit below:

```tsx
  // kind === "answer" — lead with the answer; the Citation Audit is secondary (it restates
  // counts the sources already carry), so it is collapsed below the answer and sources.
  return (
    <div className="flex flex-col gap-6">
      <AnswerView text={resp.answer} />
      <FigureGrid figures={resp.figures} />
      <SourcesList citations={resp.citations} />
      {resp.literature && <LiteratureBlock literature={resp.literature} />}
      <details className="surface p-4">
        <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          {auditSummaryLabel(resp.citations.length, resp.literature?.citations.length ?? 0)}
        </summary>
        <div className="mt-4 sm:max-w-md">
          <CitationAudit citations={resp.citations} literature={resp.literature} />
        </div>
      </details>
    </div>
  )
```

(Contrast: the summary uses `text-muted-foreground`, a token — no `text-primary`/`text-success`/`text-amber` on a light surface. `CitationAudit` is unchanged.)

- [x] **Step 6: Verify the full web harness and commit**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt/web && npm run test && npm run build`
Expected: vitest all-green (incl. `askLayout`); build succeeds (confirms no dangling `citationSummary` import and the JSX compiles).

```bash
cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt
git add web/src/lib/askLayout.ts web/src/lib/askLayout.test.ts web/src/pages/Ask.tsx
git commit -m "feat(ask): lead with the answer, collapse the redundant Citation Audit below it"
```

---

### Task 4: Duplicate search inputs — one canonical corpus input

The global nav "Ask the corpus… ⌘K" command field competes and overlaps with the Ask page's own input on mobile. Make ONE canonical: hide the nav command field while on `/ask` (the page owns the input). ⌘K still navigates to `/ask` from elsewhere.

**Files:**
- Create: `web/src/lib/navSearch.ts`
- Create: `web/src/lib/navSearch.test.ts`
- Modify: `web/src/components/NavBar.tsx` (gate the command-field button on the route)

**Interfaces:**
- Produces: `shouldShowNavSearch(pathname: string) -> boolean` — false on the Ask route, true elsewhere.

- [x] **Step 1: Write the failing test**

Create `web/src/lib/navSearch.test.ts`:

```typescript
import { describe, it, expect } from "vitest"
import { shouldShowNavSearch } from "./navSearch"

describe("shouldShowNavSearch (one canonical corpus input)", () => {
  it("hides the nav command field on the Ask route (the page owns the input)", () => {
    expect(shouldShowNavSearch("/ask")).toBe(false)
  })
  it("hides it on nested Ask routes too", () => {
    expect(shouldShowNavSearch("/ask/anything")).toBe(false)
  })
  it("shows it on every other route", () => {
    expect(shouldShowNavSearch("/")).toBe(true)
    expect(shouldShowNavSearch("/build")).toBe(true)
    expect(shouldShowNavSearch("/cards")).toBe(true)
  })
})
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt/web && npx vitest run src/lib/navSearch.test.ts`
Expected: FAIL — cannot resolve `./navSearch` / no `shouldShowNavSearch` export.

- [x] **Step 3: Write minimal implementation (pure helper)**

Create `web/src/lib/navSearch.ts`:

```typescript
/** The Ask page owns a full-width corpus search input, so the global nav "Ask the corpus… ⌘K"
    command field is redundant (and overlaps it on mobile) while on /ask. One canonical input:
    hide the nav command field on the Ask route. ⌘K still navigates to /ask from elsewhere. */
export function shouldShowNavSearch(pathname: string): boolean {
  return !pathname.startsWith("/ask")
}
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt/web && npx vitest run src/lib/navSearch.test.ts`
Expected: PASS.

- [x] **Step 5: Gate the command field in NavBar.tsx**

In `web/src/components/NavBar.tsx`:

1. Extend the router import and add the helper import:

```tsx
import { NavLink, useNavigate, useLocation } from "react-router-dom"
import { shouldShowNavSearch } from "@/lib/navSearch"
```

2. Read the current path inside `NavBar`, next to `const navigate = useNavigate()`:

```tsx
  const navigate = useNavigate()
  const { pathname } = useLocation()
```

3. Wrap the existing `{/* ── Center: "Ask the corpus" command field … ── */}` `<button …>…</button>` in the route gate, keeping a flex spacer so the right-hand cluster stays right-aligned when the field is hidden:

```tsx
        {/* ── Center: "Ask the corpus" command field — hidden on /ask (page owns the input) ── */}
        {shouldShowNavSearch(pathname) ? (
          <button
            type="button"
            onClick={() => navigate("/ask")}
            className={cn(
              "mx-auto flex max-w-[280px] flex-1 items-center gap-2.5 px-3.5 py-2 text-left",
              "transition-colors duration-150 hover:border-[rgba(255,255,255,.16)]",
            )}
            style={{
              background: "rgba(255,255,255,.04)",
              border: "1px solid rgba(255,255,255,.09)",
              borderRadius: "8px",
            }}
            aria-label="Open Ask — search the corpus (⌘K)"
          >
            {/* …existing search glyph, label, and ⌘K kbd unchanged… */}
          </button>
        ) : (
          <div className="mx-auto flex-1" aria-hidden />
        )}
```

(Keep the existing inner SVG glyph, `<span>Ask the corpus…</span>`, and `<kbd>⌘K</kbd>` exactly as they are.)

- [x] **Step 6: Verify the full web harness and commit**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt/web && npm run test && npm run build`
Expected: vitest all-green (incl. `navSearch`); build succeeds.

```bash
cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt
git add web/src/lib/navSearch.ts web/src/lib/navSearch.test.ts web/src/components/NavBar.tsx
git commit -m "feat(nav): hide the global corpus command field on /ask (one canonical input)"
```

---

### Task 5: Disambiguation latency — skip re-analysis on variant picks (LAST)

**Decision (stated explicitly): implement candidate (a) — skip the expensive gate + `analyze_fn` re-run when the incoming query is already a disambiguated variant rewrite — as an OPT-IN `skip_disambiguation` flag threaded from the variant-pick click down to `Engine._plan_query`.**

Trace: an ambiguous query goes `Ask.tsx run()` → `/api/ask` → `answer_question` → `_answer_question_woven` → `plan_retrieval` → `Engine._plan_query`, which retrieves, runs the cheap `ambiguity_gate`, then (on a trip) makes ONE LLM `analyze_fn` call and, on a high-confidence resolve, retrieves a SECOND time. On a low-confidence trip it returns a `Clarification`; the SPA renders variant buttons; clicking one calls `run(v.rewrite || v.label)`, which re-enters the *entire* pipeline — including a fresh gate + `analyze_fn` — even though a variant rewrite is **unambiguous by construction**.

**Why this is the smallest safe win, and what was rejected:**
- **Provably non-regressing on disambiguation quality.** The flag defaults `False`; every existing caller and the held-out disambiguation eval (which calls `query` / `_plan_query` / `select_figures` / `answer_question` with plain user questions and the flag unset) exercises the byte-identical existing path. Only the variant-pick re-entry sets it `True`.
- **Fixes a real correctness/UX risk**, not just latency: re-analyzing a variant rewrite can produce a *nested* clarification (pick a variant → asked to clarify again). Skipping it removes that risk and also drops one LLM `analyze` round-trip plus the redundant second `_retrieve` on the resolved-variant branch.
- **Honest scope:** this does NOT touch synthesis (the dominant cost), so the variant-pick saving is ~one LLM round-trip, NOT the full ~114s. Do not overclaim.
- **Rejected — candidate (b) (cache first-pass retrieval keyed by question):** the low-confidence clarify branch never retrieves per-variant, and the variant rewrite is a NEW question string never seen on the first pass, so a question-keyed cache yields no hit on the pick — no meaningful win for added state.
- **Deferred (out of scope, flagged):** on the clarify path, `_answer_question_woven`'s `with ThreadPoolExecutor(...) as ex:` block calls `shutdown(wait=True)` on `return plan`, so returning a `Clarification` still blocks on Lane B (PubMed) completing. Fixing this means restructuring the concurrency seam (threads can't be cancelled; reordering loses A‖B overlap on the common answer path) — riskier than this task's mandate, so it is recorded here as a follow-up, not implemented.

**Files:**
- Modify: `neuro_core/query.py` (`Engine._plan_query`, `Engine.retrieve_for_synthesis`, module `plan_retrieval`)
- Modify: `neuro_caseboard/qa.py` (`_answer_question_woven`, `answer_question`)
- Modify: `api/server.py` (`AskRequest`, `ask`)
- Modify: `web/src/lib/api.ts` (`askQuestion` sends the flag)
- Modify: `web/src/pages/Ask.tsx` (variant pick passes `skipDisambiguation: true`)
- Test: `tests/neuro_core/test_retrieve_for_synthesis.py` (engine bypass)
- Test: `tests/test_qa.py` (forwarding)

**Interfaces:**
- Produces: `Engine._plan_query(question, *, skip_disambiguation=False)`; `Engine.retrieve_for_synthesis(question, *, skip_disambiguation=False)`; `plan_retrieval(question, config=None, force=False, skip_disambiguation=False)`; `answer_question(question, *, config=None, force=False, lane_a=None, lane_b=None, skip_disambiguation=False)`; `_answer_question_woven(..., skip_disambiguation=False)`.
- Web: `askQuestion(question, signal?, skipDisambiguation=false)`; request body gains `skip_disambiguation: bool`.

- [x] **Step 1: Write the failing engine test**

Append to `tests/neuro_core/test_retrieve_for_synthesis.py` (it already imports `Engine`, `RetrievalBundle`, `Clarification`, `Hit`, `Gate`, `QueryAnalysis`, `VariantRewrite`, and defines `_engine` / `FakeIndex`):

```python
def test_skip_disambiguation_bypasses_gate_and_analyze():
    # A variant rewrite is unambiguous by construction: skip_disambiguation must retrieve
    # and resolve directly, never calling the cheap gate OR the expensive analyze LLM pass.
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]
    calls = {"gate": 0, "analyze": 0}

    def gate(q, h):
        calls["gate"] += 1
        return Gate(tripped=True, axis="x")

    def analyze(q, h, sc):
        calls["analyze"] += 1
        raise AssertionError("analyze must not run on a resolved variant rewrite")

    index = FakeIndex(hits)
    eng = _engine(index, gate_fn=gate, analyze_fn=analyze)
    bundle = eng.retrieve_for_synthesis("unilateral FTP hemicraniectomy steps",
                                        skip_disambiguation=True)
    assert isinstance(bundle, RetrievalBundle)
    assert bundle.question == "unilateral FTP hemicraniectomy steps"
    assert bundle.variant is None
    assert index.called_with[0] == "unilateral FTP hemicraniectomy steps"  # retrieved once, on the rewrite
    assert calls == {"gate": 0, "analyze": 0}


def test_default_still_runs_gate_and_analyze():
    # Parity guard: without the flag, a gate trip still spends the analyze pass (existing behavior).
    hits = [Hit(id="a", book="B", chapter="C", page=1, text="t1")]
    calls = {"analyze": 0}
    vr1 = VariantRewrite("unilateral FTP hemicraniectomy", "uni rewrite")
    vr2 = VariantRewrite("bifrontal (Kjellberg) decompression", "bifrontal rewrite")

    def analyze(q, h, sc):
        calls["analyze"] += 1
        return QueryAnalysis(ambiguous=True, axis="x", variants=[vr1, vr2],
                             chosen=vr1, confidence=0.2)

    eng = _engine(FakeIndex(hits), gate_fn=lambda q, h: Gate(tripped=True, axis="x"),
                  analyze_fn=analyze)
    out = eng.retrieve_for_synthesis("decompressive craniectomy steps?")
    assert isinstance(out, Clarification)
    assert calls["analyze"] == 1
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt && PYTHONPATH=vendor/caseprep python3 -m pytest -q tests/neuro_core/test_retrieve_for_synthesis.py::test_skip_disambiguation_bypasses_gate_and_analyze`
Expected: FAIL with `TypeError: retrieve_for_synthesis() got an unexpected keyword argument 'skip_disambiguation'`.

- [x] **Step 3: Implement the engine bypass (query.py)**

In `neuro_core/query.py`, change `_plan_query` to accept the flag and short-circuit:

```python
    def _plan_query(self, question, *, skip_disambiguation=False):
        """Shared disambiguation seam. Returns a Clarification (ask, no briefing) or
        a _Resolved (the question + passages to answer, possibly variant-resolved).
        Keeps prose (query) and figures (select_figures) on the SAME chosen variant.

        ``skip_disambiguation`` is set when the caller already resolved a variant (a
        variant rewrite is unambiguous by construction): retrieve and answer directly,
        skipping the gate + the LLM analyze pass. Default path is unchanged."""
        if skip_disambiguation:
            return _Resolved(question, self._retrieve(question), None)
        top = self._retrieve(question)
        gate = self.gate_fn(question, top)
        if not gate.tripped:
            return _Resolved(question, top, None)
        analysis = self.analyze_fn(question, top, self.synth_client)
        if not analysis.ambiguous:
            return _Resolved(question, top, None)
        if analysis.confidence < CLARIFY_THRESHOLD:
            return Clarification(question=question, variants=analysis.variants)
        resolved = analysis.chosen.rewrite
        return _Resolved(resolved, self._retrieve(resolved), analysis.chosen)
```

Thread it through `retrieve_for_synthesis`:

```python
    def retrieve_for_synthesis(self, question, *, skip_disambiguation=False):
        """Retrieve passages + figures without synthesizing (for the woven Ask path).
        Returns a Clarification (ambiguous, no answer) or a RetrievalBundle."""
        plan = self._plan_query(question, skip_disambiguation=skip_disambiguation)
        if isinstance(plan, Clarification):
            return plan
        figures, images = self._collect_figures(plan.question, plan.top)
        return RetrievalBundle(question=plan.question, hits=plan.top, figures=figures,
                               images=images, variant=plan.variant)
```

And the module-level `plan_retrieval`:

```python
def plan_retrieval(question, config=None, force=False, skip_disambiguation=False):
    config = config or load_config()
    if config.synth_provider == "local" and config.gpu_guard:
        ensure_gpu_ready(config, force=force)
    return get_engine(config).retrieve_for_synthesis(
        question, skip_disambiguation=skip_disambiguation)
```

- [x] **Step 4: Run the engine tests to verify they pass**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt && PYTHONPATH=vendor/caseprep python3 -m pytest -q tests/neuro_core/test_retrieve_for_synthesis.py`
Expected: PASS (both new tests plus the existing ones).

- [x] **Step 5: Write the failing forwarding test (qa.py)**

Append to `tests/test_qa.py` (mirrors `test_answer_question_routes_to_woven_when_flag_on`):

```python
def test_answer_question_forwards_skip_disambiguation(monkeypatch):
    monkeypatch.setenv("NEURO_CASEBOARD_SKIP_DOTENV", "1")
    monkeypatch.setenv("LITERATURE_WEAVE", "1")
    import neuro_caseboard.qa as qa
    captured = {}

    def _spy(*a, **k):
        captured.update(k)
        return "WOVEN"

    monkeypatch.setattr(qa, "_answer_question_woven", _spy)
    assert qa.answer_question("unilateral FTP rewrite", skip_disambiguation=True) == "WOVEN"
    assert captured.get("skip_disambiguation") is True
```

- [x] **Step 6: Run it to verify it fails**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt && PYTHONPATH=vendor/caseprep python3 -m pytest -q tests/test_qa.py::test_answer_question_forwards_skip_disambiguation`
Expected: FAIL with `TypeError: answer_question() got an unexpected keyword argument 'skip_disambiguation'`.

- [x] **Step 7: Thread the flag through qa.py**

In `neuro_caseboard/qa.py`, update `_answer_question_woven`'s signature and its internal `plan_a`:

```python
def _answer_question_woven(question, *, config=None, force=False, lit_config=None,
                           synth_client=None, plan_a=None, retrieve_b=None,
                           skip_disambiguation=False):
```

```python
    if plan_a is None:
        def plan_a():
            return plan_retrieval(question, config=config, force=force,
                                  skip_disambiguation=skip_disambiguation)
```

And `answer_question`'s signature + the woven delegation:

```python
def answer_question(question, *, config=None, force=False, lane_a=None, lane_b=None,
                    skip_disambiguation=False) -> QAResult:
```

```python
        if lit_config.weave:
            return _answer_question_woven(question, config=config, force=force,
                                          lit_config=lit_config,
                                          skip_disambiguation=skip_disambiguation)
```

- [x] **Step 8: Run the qa test (and the scoped backend suite) to verify pass**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt && PYTHONPATH=vendor/caseprep python3 -m pytest -q tests/neuro_core/test_retrieve_for_synthesis.py tests/test_qa.py`
Expected: PASS (new forwarding test + all existing qa/engine tests).

- [x] **Step 9: Wire the API and the SPA**

In `api/server.py`, add the field to `AskRequest`:

```python
class AskRequest(BaseModel):
    question: str
    # Local single-user tool: default to bypassing the GPU-readiness guard so it "just runs".
    # A real GpuNotReadyError (e.g. genuinely out of memory) is still surfaced honestly.
    force: bool = True
    # Set by the SPA on a variant-pick re-entry: the question is already a disambiguated
    # variant rewrite (unambiguous by construction), so skip the gate + analyze pass.
    skip_disambiguation: bool = False
```

In the `ask` handler, pass it through:

```python
        result = answer_question(question, force=req.force,
                                 skip_disambiguation=req.skip_disambiguation)
```

In `web/src/lib/api.ts`, update `askQuestion` to accept and send the flag (keep the rest of the body/headers; add `skip_disambiguation` to the JSON payload):

```typescript
export async function askQuestion(question: string, signal?: AbortSignal,
                                  skipDisambiguation = false): Promise<AskResponse> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, skip_disambiguation: skipDisambiguation }),
    signal,
  })
  // …existing response handling unchanged…
```

In `web/src/pages/Ask.tsx`, let `run` accept an option and forward it, and have the variant pick set it:

```tsx
  async function run(q: string, opts?: { skipDisambiguation?: boolean }) {
    const text = q.trim()
    if (!text || loading) return
    ctrlRef.current?.abort()
    const ctrl = new AbortController()
    ctrlRef.current = ctrl
    setSubmitted(text)
    setQuestion(text)
    setResp(null)
    setNetError(null)
    setLoading(true)
    try {
      const r = await askQuestion(text, ctrl.signal, opts?.skipDisambiguation ?? false)
      if (!ctrl.signal.aborted) setResp(r)
    } catch (e) {
      const err = e as { name?: string; message?: string }
      if (err?.name !== "AbortError") setNetError(err?.message ?? String(e))
    } finally {
      if (!ctrl.signal.aborted) setLoading(false)
    }
  }
```

And the `ResultView` render call (a variant pick is an already-resolved rewrite):

```tsx
      {resp && !loading && (
        <ResultView resp={resp} onPickVariant={(q) => void run(q, { skipDisambiguation: true })} />
      )}
```

(The `onPickVariant(v.rewrite || v.label)` inside `ResultView`'s clarification branch is unchanged.)

- [x] **Step 10: Verify both harnesses and commit**

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt && PYTHONPATH=vendor/caseprep python3 -m pytest -q tests/neuro_core tests/test_qa.py tests/test_retrieve.py tests/test_pipeline.py`
Expected: PASS (scoped backend loop green).

Run: `cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt/web && npm run test && npm run build`
Expected: vitest all-green; build succeeds (confirms the `askQuestion` signature change and `run` option compile across callers).

```bash
cd /home/michael/PROJECTS/neuro-caseboard/.project-loop/wt
git add neuro_core/query.py neuro_caseboard/qa.py api/server.py \
        web/src/lib/api.ts web/src/pages/Ask.tsx \
        tests/neuro_core/test_retrieve_for_synthesis.py tests/test_qa.py
git commit -m "feat(ask): skip re-disambiguation on variant picks via opt-in skip_disambiguation"
```

---

## Self-Review

- **Spec coverage:** (1) junk-figure filter → Task 1; (2) loader honesty/frozen feel → Task 2; (3) result hierarchy → Task 3; (4) duplicate search inputs → Task 4; (5) disambiguation latency → Task 5. All five pilot defects mapped.
- **Topic-agnostic:** Task 1's `nonanatomical_figure` uses only generic publishing-artifact phrases and an absence-claim regex — no clinical phrases, no book names. ✓
- **Tests:** Task 1 pytest (`test_figure_guards.py`); Tasks 2-4 vitest pure-helper specs (`loaderSteps`/`askLayout`/`navSearch`); Task 5 pytest (`test_retrieve_for_synthesis.py` + `test_qa.py`). Every logic change is backed. ✓
- **Contrast:** new web text uses `text-muted-foreground` only; no `text-primary`/`-success`/`-amber` on light surfaces. ✓
- **Prior-work non-regression:** Task 2 keeps the monotonic checklist + `sr-only` summary and only adds the stopwatch + honest copy + pacing; it does not revert the 2026-06-23 loader-honesty work. ✓
- **Type consistency:** `skip_disambiguation` (snake_case) is consistent across `_plan_query` / `retrieve_for_synthesis` / `plan_retrieval` / `_answer_question_woven` / `answer_question` / `AskRequest`; `skipDisambiguation` (camelCase) is consistent across `askQuestion` / `run`. `formatElapsed`, `auditSummaryLabel`, `shouldShowNavSearch`, `nonanatomical_figure` are referenced with identical names in their tests and call sites. ✓
