# Plan — P3 #12: Build toggles lack tooltips ("Corpus enrichment" / "LLM explorer")

**Bug:** The Build form's two option checkboxes — `Corpus enrichment` (`enrich`) and `LLM explorer`
(`useLlm`) at `Build.tsx:191-210` — are bare labels with NO explanation of what they do or the cost/benefit
of toggling them. A surgeon can't tell what turning them off changes.

**What they actually do (for accurate copy):**
- `enrich` → the Enricher stage: attaches retrieved corpus evidence to each question card. Off = the card
  scaffold without sourced evidence (faster).
- `useLlm` → the LLM-first Explorer: generates the case-specific question set with the LLM. Off = the
  deterministic question template (faster, less tailored). (Matches CLI `--no-llm`.)

**Fix (native + accessible + discoverable):** `title` on each label for hover (the backlog's ask),
`aria-describedby` → an `sr-only` description so the help reaches SR/keyboard users (the a11y lesson from
slices 9 & 11 — `title` alone is mouse-only), and a small muted "ⓘ" `cursor-help` indicator so users know
help exists. No behavior change.

---

- [x] **Step 1 — Discoverable, accessible help on the two Build toggles (frontend only)**
  - `web/src/pages/Build.tsx`, the toggle row (~190-211):
    - Define two help-copy constants near the top (with `HINTS`/`BUILD_STEPS`):
      ```ts
      const ENRICH_HELP = "Enrich each question card with retrieved corpus evidence (the Enricher stage). Off builds the card scaffold without attached sources — faster."
      const LLM_HELP = "Generate the case-specific question set with the LLM Explorer (richer, tailored). Off uses the deterministic question template — faster."
      ```
    - For EACH `<label>`: add `title={…HELP}`; on its `<input>` add `aria-describedby="enrich-help"` /
      `"llm-help"`; after the label text add a small muted indicator
      `<span aria-hidden className="cursor-help text-[11px] opacity-60">ⓘ</span>`; and render a sibling
      `<span id="enrich-help" className="sr-only">{ENRICH_HELP}</span>` (and `llm-help`) so the description
      is referenced by id but does NOT pollute the label's accessible NAME (keep the sr-only span OUTSIDE
      the `<label>`, as a sibling in the row `<div>`).
    - Keep the existing `checked`/`onChange`/`disabled`/`accent-primary` exactly. The `cursor-help`
      indicator + `title` make help discoverable; `aria-describedby` makes it announced.
    - Contrast: the row is `text-muted-foreground` on the dark form surface — no `-ink`/bright-token issue;
      the ⓘ is muted opacity, not a brand color.
  - **Verify:** `npm --prefix web run test` + `npm --prefix web run build` + `npm --prefix web run lint`.

**Scope guard:** #12 only — the two Build toggles. NOT the grounding copy (#13) or the ⌘K / pluralization /
HealthPanel-badge micro-items (#14); those are their own slices.

**Non-regression:** pure presentation/a11y — no change to `enrich`/`use_llm` behavior or the build call.
Copy is accurate to what each flag does (no overclaim). No engine/data change.
