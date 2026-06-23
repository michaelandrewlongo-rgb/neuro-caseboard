# Plan — P3 #14: minor polish bundle (+ deferred #5/#6)

A scout located all items. **4 real fixes + 2 documented no-ops** (the backlog's premise was already
satisfied for two of them).

## No-ops (premise already satisfied — document, don't churn)
- **"1 papers" pluralization (frontend):** already guarded everywhere — `citationSummary.ts:6`
  (`total===1?"citation":"citations"`), `Cards.tsx:123,603` (`card${n===1?"":"s"}`), CitationAudit counts
  are parenthesized after uncountable nouns. The backend `_plural` covers audit reasons (PR #63). Nothing
  to fix on the frontend.
- **Engine-Online badge → HealthPanel:** already wired to live health. `NavBar`'s `<HealthPill>` derives
  from `deriveStatus(getHealth())` → `/api/health` (NavBar.tsx:48-52,148-165); `HealthPanel` reads the
  same `getHealth`/`/api/health`. NOT hardcoded. The only hardcoded "ENGINE" string is the unrelated
  `ENGINE · VERTEX` provider footnote (Home.tsx:671). An optional `useHealth()` DRY refactor is the only
  remaining change — not a bug, skipped (ponytail: no churn for its own sake).

---

- [x] **Step 1 — Make the ⌘K affordance true (wire Cmd/Ctrl+K → Ask)**
  - `NavBar.tsx:254-264` shows a `⌘K` `<kbd>` hint inside the "Ask the corpus…" button, but NO keydown
    handler exists anywhere → false affordance.
  - `web/src/lib/keys.ts` (NEW, pure): `isCmdK(e: { metaKey: boolean; ctrlKey: boolean; key: string }):
    boolean` = `(e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k"`.
  - `web/src/lib/keys.test.ts` (NEW): true for {metaKey,k}/{ctrlKey,k}/{metaKey,"K"}; false for plain "k",
    {metaKey,"j"}, {key:"k"} only.
  - `NavBar.tsx`: add a `useEffect` registering a `document` keydown listener — `if (isCmdK(e)) {
    e.preventDefault(); navigate("/ask") }` — with cleanup on unmount. (No command palette exists; wiring
    to the same navigation the button already does is the minimal honest fix — the hint now does what it
    promises.)

- [x] **Step 2 — Cerebrovascular onboarding chips (Ask + Build)**
  - `Ask.tsx:13-18` `HINTS`: append 1-2 cerebrovascular question examples (e.g.
    "anterior communicating artery perforators", "Spetzler-Martin AVM grading").
  - `Build.tsx:19-24` `HINTS`: append 1-2 cerebrovascular case examples distinct from the existing
    "right carotid endarterectomy" (e.g. "ruptured ACoA aneurysm clipping", "left temporal AVM resection").

- [x] **Step 3 — Figure lightbox body-scroll-lock (deferred from #5)**
  - `FigureGrid.tsx`: in `enlarge()` (~:96-99) add `document.body.style.overflow = "hidden"`; in the
    `<dialog onClose>` (~:115) restore `document.body.style.overflow = ""`. `onClose` is the single
    chokepoint for ESC / backdrop / × close paths, so one restore site covers all.

- [x] **Step 4 — Lane-appropriate jump-flash color (deferred from #6)**
  - `web/src/index.css` (after the existing `@keyframes citation-flash` + `[id^="src-"]:target`, :202-208):
    add `@keyframes citation-flash-lit { from { background-color: rgba(255,102,216,.30); } to {
    background-color: transparent; } }` and `[id^="src-literature-"]:target { animation: citation-flash-lit
    1.1s ease-out; }`. The more-specific `src-literature-` selector wins over the generic `src-` rule, so a
    literature source flashes plum (matching `LiteratureBlock`'s own `#ff66d8` accent) instead of
    textbook-blue. Keep the existing rule for `src-textbook-*`.

- **Verify:** `npm --prefix web run test` (incl new keys spec) + `npm --prefix web run build`
  + `npm --prefix web run lint` (separate, explicit exit codes).

**Non-regression:** all pure presentation/UX — no engine/data change, no fabrication. The ⌘K wiring makes
an existing hint honest; the chips are example text; scroll-lock + flash-color are deferred polish from
slices 5/6. Reduced-motion: `citation-flash-lit` is covered by the existing global `animation` reduced-
motion guard (same as `citation-flash`).
