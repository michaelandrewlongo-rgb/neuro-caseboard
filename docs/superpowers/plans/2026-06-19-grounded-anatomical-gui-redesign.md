# Grounded Anatomical GUI Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.
>
> **project-loop note:** Each checkbox below is ONE subagent-sized deliverable = one IMPLEMENT increment. The loop's VERIFY phase runs the harness (`npm --prefix web run build` + `npm --prefix web run lint`) after each step, and the subagent commits its work with a message prefixed `loop step <N>: <step text>`. Do NOT add separate "verify"/"commit" checkboxes — they are machine-handled.

**Goal:** Recreate the "Neuro·Caseboard" web SPA (`web/`) in the dark "Grounded Anatomical" aesthetic from the design handoff — a premium clinical-telemetry look on a warm charcoal ground with an anatomical palette (arterial crimson, venous teal, tissue ochre, clinical sage, muted plum) — across all surfaces (Landing, Ask, Dossier, Cards, shared chrome), presentation-only.

**Architecture:** Token-first redesign. Swap the `index.css` `@theme` tokens + fonts once, then re-skin each surface to consume them, then add two dependency-free SVG chart primitives (RiskRadar, EvidenceGauge) reused across surfaces, then the bespoke Circle-of-Willis hero SVG. The engine/API layer (`/api/ask`, `/api/build`, `/api/cards`, `/api/health`) and all data flows in `web/src/lib/api.ts` are **unchanged** — only presentation and new presentational state (route active state, evidence filter, hovered-metric key, clock tick) are added.

**Tech Stack:** React 19, Vite 8, TypeScript, Tailwind v4 (`@theme` CSS-variable tokens), shadcn-style primitives in `components/ui.tsx`, `cn()`/tailwind-merge (`lib/utils.ts`), `react-markdown` (answer bodies), `motion` (animation). Fonts: Geist + JetBrains Mono via Google Fonts.

## Global Constraints

- **Presentation-only.** Do NOT modify `web/src/lib/api.ts` request/response logic, the engine, or the FastAPI layer. Preserve every existing data flow and the honest-degradation states (`unavailable` / `not built` / `error`) — re-skin them, never remove them. A down lane must still say so; never fabricate data.
- **One styling system.** Tailwind v4 utilities + the `@theme` tokens only. Do NOT ship the `.dc.html` files directly and do NOT introduce a second styling system (no styled-components, no CSS modules). Use the existing `cn()` util and `ui.tsx` primitives.
- **Reference, don't copy-paste markup:** design references live at `.project-loop/design_handoff/` — `README.md` (token + screen spec), `Neuro Landing.dc.html` (Circle-of-Willis SVG + ECG band), `Neuro Dossier.dc.html` (radar + gauge generator code in its `<script data-dc-script>` block, plus provenance tooltips). Only the chart SVG math and the Circle-of-Willis `<svg>` are lifted near-verbatim (wrapped as React components).
- **On-dark text color rule:** colored *text* must use the "On-dark text" / Bright variants, NOT the base accent (base hues fail contrast on `#0e0b0c`): crimson text `#ff7363`, teal text `#6fc0b8`, ochre text `#e0a86a`. Base accents are for fills/borders/strokes. Button text on the crimson fill is `#ffffff`.
- **Exact palette (verbatim from README):** Ground `#0e0b0c`; text primary `#f1ece6`, body `#ece7e1`, secondary `#a79e98`, muted `#897d77`. Crimson `#d8413a` (bright `#ff7363`, deep `#a01f2b`), teal `#3f9690` (bright `#58b8b0`, deep `#2c6b66`), ochre `#d89a3f` (bright `#ecae5e`), sage `#5fa86f`, plum `#a98bc4`, brick/critical `#c0564f`. Primary gradient `linear-gradient(135deg,#d8413a,#ff7363)`.
- **Accent-per-surface mapping:** Ask = crimson, Dossier/citations/links/active-nav = teal, Cards/verify = ochre, Supported = sage, Contemporary-literature lane = plum, Quarantined/critical = brick.
- **Radii (rounded — the old theme forced squares):** cards/panels 16–18px, buttons/inputs/badges 8–13px, chips/pills 7–9px (status pills `999px`). Set `--radius-sm:8px; --radius-md:11px; --radius-lg:16px; --radius-xl:18px`.
- **Fonts:** Geist (display/UI) + JetBrains Mono (labels/data/mono, all-caps eyebrows ~9–11px, letter-spacing 0.12–0.22em). Replaces DM Sans / Space Mono.
- **Accessibility:** keyboard-accessible interactive popovers (provenance tooltips); honor `prefers-reduced-motion` on all keyframe animations; maintain the existing `sr-only` status labels.
- **Harness (the gate for every task):** from the repo root, `npm --prefix web run build` (runs `tsc -b && vite build`) AND `npm --prefix web run lint` must both exit 0. There are no per-component unit tests; the build (typecheck + bundle) + eslint IS the test. Every task ends green on both.

---

## File Structure

- `web/src/index.css` — token/`@theme` swap, font import, remove brutalist square-corner + hard-shadow rules, add palette helpers + shared keyframes. (Task 1.)
- `web/src/components/NavBar.tsx` — glass top bar, diamond logo, nav pills, command field, ENGINE-ONLINE health pill, avatar. (Task 2.)
- `web/src/components/charts/RiskRadar.tsx`, `web/src/components/charts/EvidenceGauge.tsx` — NEW reusable SVG charts. (Task 3.)
- `web/src/pages/Build.tsx` + `web/src/components/build/DossierView.tsx` + `web/src/components/build/EvidenceBar.tsx` → restyle; NEW `web/src/components/build/PlanningMetrics.tsx`. (Tasks 4, 5.)
- `web/src/pages/Ask.tsx` + `web/src/components/ask/{AnswerView,FigureGrid,SourcesList,LiteratureBlock}.tsx`; NEW `web/src/components/ask/{CitationAudit,StructuresRadar}.tsx`; `web/src/lib/citations.tsx`. (Task 6.)
- `web/src/pages/Cards.tsx` + `web/src/components/cards/CardItem.tsx`. (Task 7.)
- `web/src/pages/Home.tsx` + NEW `web/src/components/CircleOfWillis.tsx`. (Task 8.)
- `web/src/components/{PipelineLoader,HealthPanel}.tsx` + `web/src/components/ask/AskLoader.tsx`. (Task 9.)

Shared primitives in `web/src/components/ui.tsx` may gain palette-aware variants but must stay backward-compatible with current call sites.

---

### Task 1: Token & typography foundation (`index.css`)

**Files:** Modify `web/src/index.css`. Reference `.project-loop/design_handoff/README.md` (§Design Tokens).

**Produces (token names every later task consumes):** `--color-background:#0e0b0c`, `--color-foreground:#f1ece6`, `--color-card:#14100f`, `--color-primary:#d8413a`, `--color-primary-foreground:#ffffff`, `--color-secondary:#3f9690`, `--color-secondary-foreground:#04110f`, `--color-accent:#d89a3f`, `--color-muted:rgba(255,255,255,0.04)`, `--color-muted-foreground:#978d86`, `--color-border:rgba(255,255,255,0.09)`, `--color-ring:#d8413a`, `--color-success:#5fa86f`, `--color-amber:#d89a3f`, `--color-signal:#c0564f`, `--radius-sm:8px/--radius-md:11px/--radius-lg:16px/--radius-xl:18px`, `--font-sans`/`--font-display`="Geist", `--font-mono`="JetBrains Mono".

- [x] **Task 1 — Token swap.** In `web/src/index.css`: add the Google Fonts import (`@import url("https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap");` at top). Replace the `@theme` font + color + radius tokens with the exact values in **Produces** above (copy hex verbatim from README §"Mapping into web/src/index.css"). Set `:root { color-scheme: dark; }`. **Remove** the brutalist `* { border-radius: 0 !important }` rule, the `--radius: 0` overrides, and the hard offset-shadow rules. Add `::selection { background: rgba(216,65,58,.28); color:#fff; }`. Keep the `.tnum` helper. Add the body ambient radial-glow background (crimson `rgba(190,45,50,.13)`, teal `rgba(60,120,116,.08)`, ochre `rgba(175,120,55,.06)`) and the shared keyframes surfaces will use (`signal-rise`, `nl-rise`, status-dot `pulse`, ECG `scroll`, Circle-of-Willis `nl-flow`/`nl-node`/`nl-sweep`/`nl-float`), each guarded by `@media (prefers-reduced-motion: reduce)`. End state: app builds and globally shifts to the dark ground (per-surface work follows).

---

### Task 2: Shared chrome — NavBar (`NavBar.tsx`)

**Files:** Modify `web/src/components/NavBar.tsx`. Reference README §"Shared chrome"; `Neuro Dossier.dc.html` top bar.
**Consumes:** Task 1 tokens; existing `/api/health` fetch in `lib/api.ts` (do not change its signature); existing React Router routes (`/ask`, `/build`, `/cards`).

- [x] **Task 2 — Rebuild the top bar.** Sticky glass top bar (glass-panel gradient + 1px light border + `backdrop-filter: blur(14px)`): crimson diamond logo (gradient `135deg,#d8413a,#ff7363` square with a rotated cutout) + wordmark + `TELEMETRY CONSOLE` mono tag; nav buttons Ask / Dossier / Cards with the active route as a **teal pill**; a center "Ask the corpus" command field showing a `⌘K` hint that navigates to `/ask` on click; a right-side `ENGINE ONLINE` status pill (sage, pulsing dot) wired to the existing `/api/health` state (show the honest degraded/offline state when health is not ok); an avatar. Use `cn()` + tokens; keep routing behavior intact; preserve existing `sr-only` labels.

---

### Task 3: Chart primitives (`charts/RiskRadar.tsx`, `charts/EvidenceGauge.tsx`)

**Files:** Create `web/src/components/charts/RiskRadar.tsx`, `web/src/components/charts/EvidenceGauge.tsx`. Reference the `radar(axes,size,withMit)` and `gauge(rings,size)` generators in `Neuro Dossier.dc.html` `<script data-dc-script>`; README §Charts.
**Produces (signatures used by Tasks 4/6/7):**
- `RiskRadar({ axes, size, withMit }: { axes: {k:string; risk:number; mit?:number}[]; size:number; withMit?:boolean })` — polar `angle(i)=-π/2+i·2π/n`, point `=center+cos/sin·R·(value/100)`, `R=size/2−30`; 4 grid rings `rgba(255,255,255,.07)`, spokes, risk polygon (radial crimson fill, stroke `#d8413a`, drop-shadow), optional dashed teal mitigation polygon, value dots, mono axis labels at `R·1.16`.
- `EvidenceGauge({ rings, size }: { rings: {r:number; frac:number; color:string; glow:string}[]; size:number })` — concentric; each ring = track circle (`rgba(255,255,255,.06)`, width 9) + value arc via `stroke-dasharray:\`${C*frac} ${C}\``, `transform: rotate(-90 cx cy)`, round linecap, `drop-shadow(0 0 5px glow)`. Center label = absolutely-positioned HTML overlay via a `label`/`children` prop, NOT baked into the SVG.

- [ ] **Task 3 — Port both SVG generators** as typed, dependency-free React components with the exact signatures above. No external chart lib. Keep them pure (props in, SVG out); center label via prop/children overlay. They must compile even before they have call sites.

---

### Task 4: Dossier surface (`Build.tsx`, `DossierView.tsx`, `EvidenceBar.tsx`→`PlanningMetrics`)

**Files:** Modify `web/src/pages/Build.tsx`, `web/src/components/build/DossierView.tsx`, `web/src/components/build/EvidenceBar.tsx`; create `web/src/components/build/PlanningMetrics.tsx`. Reference README §"2 · Dossier".
**Consumes:** `charts/RiskRadar`, `charts/EvidenceGauge` (Task 3); existing `BuildResponse` + `build_id` PDF download + rehearsal marks/`submitFeedback` in `lib/api.ts` (unchanged).

- [ ] **Task 4 — Rebuild the Dossier.** Case header: teal eyebrow `ACTIVE CASEBOARD · PRE-OP DOSSIER · v3`, H1 case title, mono attribute chips, "Export PDF" (ghost) + "Rehearse" (crimson) buttons (wired to existing handlers). Telemetry grid `1.15fr/1fr/1.05fr`: **Risk topology** `RiskRadar` (7 axes CN VII / CN VIII / Brainstem / AICA / CSF / Lower CN / Cerebellum, two polygons predicted-crimson + post-mitigation-teal-dashed); **Evidence integrity** `EvidenceGauge` (3 rings Supported-sage / Verify-ochre / Quarantine-brick, center count, legend); **Planning metrics** as new `PlanningMetrics.tsx` (labeled bars Facial-pres sage / Hearing-pres ochre / GTR teal + stat tiles EST OR TIME, CSF LEAK RISK brick) — restyle/replace the old `EvidenceBar`. Evidence filter segmented control ALL/SUPPORTED/VERIFY/QUARANTINE with counts (active teal); selecting dims non-matching claims to `opacity:.22` over `.3s` (new presentational `filter` state). Dossier body `1fr/372px`: section cards (gradient A/B letter badge, intro, claims) + right rail (Figures, Corpus sources, Contemporary literature plum). Claim card: left status bar + glow dot, status eyebrow (SUPPORTED sage / TO VERIFY ochre / QUARANTINED brick), claim text, accent-colored "Why:" label, checkbox sub-items (`accent-color:#3f9690`), teal `[n]` citation chips + "→ Fig n"; quarantined claims show "Held back:" note + no sources. Map onto real `BuildResponse` fields; preserve honest-degradation.

---

### Task 5: Planning-metric provenance tooltips (keyboard-accessible)

**Files:** Modify `web/src/components/build/PlanningMetrics.tsx` (from Task 4). Reference README §Interactions "Planning-metric provenance tooltips".
**Consumes:** Task 4 `PlanningMetrics`; per-metric provenance data in `BuildResponse` (derivation sentence + source chips) — if a field is absent, degrade gracefully (no tooltip), do not fabricate.

- [ ] **Task 5 — Add the hover/focus popover.** Each metric row `position:relative; cursor:help` with a dotted-underline label; on hover **and keyboard focus** a glass popover (`rgba(13,17,24,.97)`, 1px border, blur, `opacity .16s`) appears above it with a `DERIVATION` mono eyebrow, the derivation sentence, and source chips (`[n]`, counts, ranges). Keyboard-accessible (focusable trigger, ESC/blur dismiss; Radix/Floating-UI or accessible CSS). Honor `prefers-reduced-motion`.

---

### Task 6: Ask surface (`Ask.tsx`, `AnswerView`, `FigureGrid`, `SourcesList`, `LiteratureBlock`, `citations.tsx`; new `CitationAudit`, `StructuresRadar`)

**Files:** Modify `web/src/pages/Ask.tsx`, `web/src/components/ask/{AnswerView,FigureGrid,SourcesList,LiteratureBlock}.tsx`, `web/src/lib/citations.tsx`; create `web/src/components/ask/{CitationAudit,StructuresRadar}.tsx`. Reference README §"1 · Ask".
**Consumes:** `charts/EvidenceGauge`, `charts/RiskRadar` (Task 3); existing `AskResponse` union (`answer | clarification | unavailable | error`) + abortable request in `lib/api.ts` (unchanged).

- [ ] **Task 6 — Rebuild Ask.** Hero (eyebrow `ASK · CITED ANSWER ENGINE`, H1 "Ask the corpus", search field + crimson "Ask" button, example chips); status line ("N of M claims grounded…" from the real response); telemetry row `1fr/1fr`: **CitationAudit** (`EvidenceGauge` concentric, center "g/t · GROUNDED", sage/ochre legend, fed by the answer's grounded/verify counts) + **StructuresRadar** (`RiskRadar` crimson of anatomy named in the answer). Restyle `AnswerView`/`react-markdown` body to 15px/1.72 `#ece7e1`; render inline `[n]` citations as teal pills (bg `rgba(63,150,144,.12)`, text `#6fc0b8`) via `citations.tsx`; ochre "VERIFY" callout for flagged claims. Right rail: `FigureGrid` (dashed FIG placeholders → real `/api/figure` when `image_available`), Contemporary-literature lane (plum `[L#]`), `SourcesList` (teal `[n]` + book/chapter/page). Preserve clarification/unavailable/error states.

---

### Task 7: Cards surface (`Cards.tsx`, `CardItem.tsx`)

**Files:** Modify `web/src/pages/Cards.tsx`, `web/src/components/cards/CardItem.tsx`. Reference README §"3 · Cards".
**Consumes:** `charts/EvidenceGauge` (Task 3); existing `CardsResponse` + query/`k` in `lib/api.ts` (unchanged).

- [ ] **Task 7 — Rebuild Cards.** Hero (eyebrow `CARDS · BOARD-REVIEW DECK`, H1 "Search your card bank", subtitle, search + crimson "Search" + deck filter chips ALL DECKS-teal / SANS / ABNS / ★ HIGH-YIELD-ochre). Deck telemetry `1fr/1.1fr/1fr`: **Match strength** `EvidenceGauge` single teal ring (center "0.xx · COSINE" from real top score); **Deck coverage** bars (Tumor sage / Functional teal / Vascular ochre / Spine brick); **Deck status** tiles. Matched cards `grid 1fr/1fr`: each `CardItem` with teal deck badge, ★HIGH-YIELD ochre, match score (sage/ochre by strength), PROMPT, ANSWER (sage label), tag chips; plus a dashed "+ N more below threshold" tile. Map to real `CardsResponse`; preserve empty/error states.

---

### Task 8: Landing + Circle of Willis (`Home.tsx`, new `CircleOfWillis.tsx`)

**Files:** Modify `web/src/pages/Home.tsx`; create `web/src/components/CircleOfWillis.tsx`. Reference README §"0 · Landing"; `Neuro Landing.dc.html`.
**Consumes:** Task 1 tokens + keyframes; React Router for the CTA → `/ask`. (Two checkboxes: the SVG is a large self-contained deliverable, then the page composition.)

- [ ] **Task 8a — Lift the Circle-of-Willis SVG** into `CircleOfWillis.tsx` near-verbatim (defs, gradients, glow filter, vessel `<path>`s in `<g id="cowV">` drawn twice via `<use>` for bloom+crisp, flow-pulse paths, anastomosis nodes, micro-labels ACA/MCA/PCA/BA/VA). Move its `@keyframes` (`nl-flow`/`nl-node`/`nl-sweep`/`nl-float`) into `index.css` and reference by class. Vessel gradient `#ff7363→#e23b3b→#a01f2b`, flow highlight `#ffe6df`, nodes `radial-gradient(#fff→#ffb3a8→transparent)`. Component must compile and render standalone.
- [ ] **Task 8b — Rebuild Home/Landing.** Sticky glass nav; hero `grid 1.04fr/0.96fr` (copy left, `<CircleOfWillis/>` right, `min-height:80vh`): eyebrow `DECISION-SUPPORT FOR THE OPERATIVE FIELD`, H1 "Where millimeters decide everything." (62px/600; "everything." gradient `linear-gradient(120deg,#d8413a,#e8a24a 60%,#b3742a)` via `background-clip:text`), sub paragraph, crimson "Open the console" CTA → `/ask` + ghost "How grounding works". Standard band: horizontally-scrolling ECG line (monitor-green `rgba(95,168,111,.5)`, mask-faded edges, translateX keyframe) behind the centered "approximately right is wrong" statement with crimson/ochre/neutral emphasis spans. Three pathways: 3 cards (`translateY(-4px)` hover), Ask-crimson / Dossier-teal / Cards-ochre, teal "THREE PATHWAYS" eyebrow. Evidence states: 3 left-bordered cards Supported-sage / To-verify-ochre / Quarantined-brick, ochre eyebrow. Stats: 4 glass tiles with `background-clip:text` gradient numbers (12 crimson / 0 sage / 4 teal / 100% ochre). Final CTA card + footer.

---

### Task 9: Re-skin loaders / health / error states + accessibility pass

**Files:** Modify `web/src/components/PipelineLoader.tsx`, `web/src/components/ask/AskLoader.tsx`, `web/src/components/HealthPanel.tsx`. Reference README §"Loading / error / degradation" + §Interactions.
**Consumes:** Task 1 tokens/keyframes; existing loader/health props (unchanged).

- [ ] **Task 9 — Re-skin + a11y.** Re-skin `PipelineLoader`, `AskLoader`, `HealthPanel` to the palette (glass panels, mono eyebrows, accent dots) while preserving the honest "unavailable / not built / error" copy and behavior. Audit all keyframe animations added across the redesign for a `@media (prefers-reduced-motion: reduce)` guard. Confirm interactive elements (nav pills, filter segments, provenance tooltips, CTAs) are keyboard-reachable with visible focus rings (`--color-ring`), and that status pills keep `sr-only` text labels.

---

## Self-Review

- **Spec coverage:** Landing (Task 8), Ask (Task 6), Dossier (Task 4), Cards (Task 7), shared NavBar chrome (Task 2), charts RiskRadar+EvidenceGauge (Task 3), Circle-of-Willis (Task 8a), tokens/fonts/radii (Task 1), provenance tooltips (Task 5), loaders/health/error + reduced-motion + a11y (Task 9). All README screens, charts, tokens, and interactions map to a task.
- **Placeholder scan:** chart signatures, token hex, copy strings, and accent mappings are given verbatim; the only "see the source file" references are the legitimately-lifted chart math and Circle-of-Willis SVG, whose exact code lives in the cited `.dc.html` files.
- **Type consistency:** `RiskRadar({axes,size,withMit})` and `EvidenceGauge({rings,size})` signatures are identical everywhere they appear (Tasks 3/4/6/7). `PlanningMetrics` created in Task 4, extended in Task 5. New components (`CitationAudit`, `StructuresRadar`, `CircleOfWillis`) each created once.
- **Ordering:** tokens (1) precede all surfaces; charts (3) precede consumers (4/6/7); Circle-of-Willis keyframes added in Task 1 are consumed in Task 8.
- **Granularity:** 10 implementation checkboxes (Tasks 1–7, 8a, 8b, 9) = 10 IMPLEMENT increments, each independently build+lint-gated.
