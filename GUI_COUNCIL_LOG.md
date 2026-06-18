# GUI Council Log — Neuro·Caseboard web console

Dated, evidence-backed record of each refinement cycle. Branch: `gui/council-refinement`
(worktree off `origin/master`). Stack: Vite :5174 → API :8001 (from this worktree).

---

## Cycle 0 — Baseline + unblock (2026-06-18)

### Pre-work (objective fixes, acted autonomously)

1. **Fixed a broken `origin/master` web build.** `web/src/pages/Build.tsx` imports
   `@/components/build/EvidenceBar` and `@/components/build/DossierView`, but those files were never
   in git — the root `.gitignore` pattern `build/` (meant for the Python build artifact) is
   unanchored, so it also matched `web/src/components/build/` and silently kept the components out of
   every commit. The merged master therefore failed Vite import-analysis on load and rendered an
   error overlay on **all four routes** (first capture attempt: every screenshot identical, no inputs).
   - Fix: anchored the ignore to `/build/` (root only) and restored both components into the worktree
     (recovered from the `web-react-bits-frontend` worktree, the only place they existed on disk).
   - Evidence: `gui-council/shots/` first run = error overlay; after fix = the real app renders, console clean.

2. **Integrated the NCBI key** into a gitignored, auto-loaded `.env` (separate request) — health now
   reports `ncbi_key: true`. See `config.py` `_load_dotenv_once()` + `.env.example`.

### Baseline measurement

- Captured all four surfaces at 1280w + 390w (default) plus loading states for ask/build/cards, with
  axe-core (WCAG 2.0/2.1/2.2 A+AA + best-practice). See `GUI_COUNCIL_SCORECARD.md`.
- **Console: clean everywhere.** **Responsive: no overflow** at either width.
- **Only serious violation type: `color-contrast`** — and every instance traces to one token,
  `--color-primary: #ff3333`, used as small red text on white and as a white-text fill (all 3.63:1).
- Other non-axe findings: home has no `<h1>` (BlurText renders `<p>`); `prefers-reduced-motion` not
  honored by BlurText/animate-pulse; no live region for the 30s–4min async results; minor token drift
  (1px `rounded-lg` borders vs the 2px square system).

### Council convergence (Cycle 1 candidate)

The accessibility-weighted highest-value increment is unambiguous and unanimous-by-evidence: **fix the
`#ff3333` contrast**. It is the *only* serious axe violation, appears on *every* surface and state, and
is a single token/primitive change. Because it touches brand palette/identity, it is gated on a
one-line user approval per the decision model (see session thread). Queued objective follow-ups (no
approval needed): home `<h1>`, reduced-motion guard, async live region, token-drift cleanup.

### Next bottleneck
Contrast (pending palette approval), then the reduced-motion + live-region a11y pair.

---

## Cycle 1 — Contrast fix (2026-06-18)

- **Flagged by:** accessibility (axe: 43 serious `color-contrast`), visual/brand, contrarian — unanimous.
- **Decision:** user approved **Path B** + **full autonomy** for the rest of the loop.
- **Change (two-token model):**
  - `--color-primary-foreground` `#ffffff → #000000` — black labels on the bright red fill (5.8:1).
    Fixes primary `Button`, active nav, figure refs, logo glyph in one token.
  - Added `--color-primary-ink #c8102e`, `--color-success-ink #15803d`, `--color-amber-ink #b45309`
    for colored **text on white** (≥5:1). Swapped every `text-primary/success/amber` → `*-ink`
    (eyebrows, card tags, links, code, `[n]`/figure markers, loader status, error headings, Stat,
    Dossier status marks). Bright `bg-*`/`border-*` fills untouched → brand identity preserved.
- **Verified:** `npm run build` 0 errors; re-capture → **serious contrast 43 → 0**; console clean;
  before/after `shots/baseline` vs `shots/cycle1` show identical layout, only red lettering deepened
  + active-nav label flipped to black.
- **Next bottleneck:** the lone remaining axe item (`page-has-heading-one`) + reduced-motion/live-region.

## Cycle 2 — Accessibility completion (2026-06-18)

- **Flagged by:** accessibility, UX (slow-call SR experience), first-time-user.
- **Changes:**
  - `BlurText` gained an `as` prop → Home title is a real `<h1>` (clears `page-has-heading-one`).
  - `BlurText` honors `prefers-reduced-motion` (motion/react `useReducedMotion`) → static text, no
    blur/translate. Global reduced-motion rule stops `.animate-pulse` shimmer/dot.
  - Skip-to-content link in `App.tsx`; `main#main` focusable landmark.
  - Loaders (`AskLoader`, `PipelineLoader`) → `role=status` + `aria-busy` + a stable sr-only summary;
    animated stages/shimmer marked `aria-hidden`.
  - Per-page persistent `aria-live="polite"` regions in Ask/Build/Cards announce result arrival
    ("Answer ready", "Dossier ready: …", "N cards found") after the 30s–4min calls.
- **Verified:** `npm run build` 0 errors; re-capture → **0 axe violations of any impact, all 11
  captures**; `verify.cjs` → h1 present, first Tab = skip link, reduced-motion static (0 spans),
  loader role=status+sr-only — ALL PASS.
- **Next bottleneck:** token-drift cleanup (1px `rounded-lg` borders vs the 2px square system); then
  Lighthouse capture + final report.

## Cycle 3 — Token-drift cleanup + Lighthouse (2026-06-18)

- **Flagged by:** visual/brand (token consistency), frontend engineer.
- **Changes:**
  - 1px `rounded-lg border` → `border-2 border-border` (2px square) in `SourcesList`, `CardItem`
    images, and the Ask clarification buttons — matching the brutalist primitives; dropped the dead
    `rounded-*` (global `radius:0`) and a no-op `hover:border-border`.
  - `Button` disabled state: `opacity-40` (washed out the now-black label to #999 on #ffadad = 1.6:1)
    → explicit `bg-muted` + `text-muted-foreground` (~11:1). Fixes the legibility of the loading
    "Asking…/Searching…/Building…" button and removed a flaky axe hit on the disabled control.
- **Verified:** `npm run build` 0 errors; re-capture → **0 axe violations** (all 11); Lighthouse
  **accessibility 100 on all 4 routes** (first batch read 93 due to a mid-HMR cold start — confirmed
  flaky; live DOM has exactly one `<main>`, clean re-runs all 100).
- **Stop condition met.** See scorecard. Remaining nice-to-haves: full manual screen-reader sweep;
  ~500KB JS bundle code-split (perf, not a11y).
