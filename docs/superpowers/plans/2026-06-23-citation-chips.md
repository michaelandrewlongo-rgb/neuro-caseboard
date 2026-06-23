# Plan — P2 #6: citation rendering & navigation (combined-marker chips + jump flash)

**Two defects (from the live app):**
1. **Inconsistent markers** — a combined citation like `[2, 11]` renders as **unclickable plain text**,
   while single `[2]` renders as a clickable chip. Root cause: `provenance.ts::splitCitations` uses
   `SPLIT_RE = /(\[(?:L|C)?\d+\])/g`, which only matches a bracket wrapping ONE number. `[2, 11]` never
   matches → falls through as text. (The renderer `citations.tsx::chipify` is fine — it just never
   receives those markers.)
2. **No jump-confirmation flash** — clicking a chip sets the URL hash and scrolls to the source `<li>`
   (anchors `src-textbook-N` / `src-literature-N`, both already have `scroll-mt-20`), but nothing
   visually confirms where you landed.

**Approach (lazy + native):**
- **Marker parser**: broaden `splitCitations` to accept a bracket containing one OR MORE comma-separated
  citation tokens, emitting one marker per token. `[2, 11]` → two chips `2` `11`; `[L2, C3]` → mixed
  literature+card chips. Single `[2]` is just the 1-token case → same code path (consistency for free).
- **Flash**: pure CSS `:target` (no JS) — `[id^="src-"]:target { animation: citation-flash … }`. CSS
  animation declarations outrank inline styles in the cascade, so the keyframe background visibly
  overrides each `<li>`'s inline bg. Covers both lanes (`src-textbook-*`, `src-literature-*`).

---

- [x] **Step 1 — Combined-marker parsing in provenance.ts**
  - Replace `SPLIT_RE` with a group regex that captures a full bracket of comma-separated tokens:
    `/(\[\s*(?:L|C)?\d+(?:\s*,\s*(?:L|C)?\d+)*\s*\])/g`.
  - Rewrite `splitCitations`: for each split part, if it is a whole bracket group (test against an
    anchored `^…$` version), extract individual tokens (`/(?:L|C)?\d+/g`), `classifyMarker(`[${tok}]`)`
    each, and push one `{ marker }` segment per token; otherwise push `{ text: part }`. Single-marker
    behavior is unchanged (1 token). `classifyMarker` / `Marker` / `Segment` stay as-is.
  - `web/src/lib/provenance.test.ts` (extend): `splitCitations("see [2, 11] and [L3]")` → text "see ",
    marker n=2, marker n=11, text " and ", marker kind=literature n=3; also a no-space `[2,11]`; a mixed
    `[L2, C3]`; and a non-regression single `[5]`. Keep existing `classifyMarker` tests green.

- [x] **Step 2 — Jump-confirmation flash (pure CSS)**
  - `web/src/index.css`: add
    ```css
    @keyframes citation-flash { from { background-color: rgba(107,147,255,.40); } to { background-color: transparent; } }
    [id^="src-"]:target { animation: citation-flash 1.1s ease-out; }
    ```
    (Place near the other keyframes / global rules.) No component change needed — the `src-*` ids and
    `scroll-mt-20` already exist in `SourcesList.tsx` and `LiteratureBlock.tsx`.
  - **Known ceiling (ponytail comment):** `:target` won't re-fire when the SAME chip is clicked twice
    (hash unchanged). Covers the common click-different-citations case; JS re-trigger is the upgrade path.

- **Verify:** `npm --prefix web run test` (incl. extended provenance spec) + `npm --prefix web run build`
  + `npm --prefix web run lint` (clean).

**Non-regression:** single `[n]`/`[L#]`/`[C#]` chips unchanged; markdown structure untouched (`citify`
still only rewrites string children). No data-model/engine change — pure presentation. `[C#]` chips that
have no rendered card list still link as before (pre-existing; out of scope for #6).
