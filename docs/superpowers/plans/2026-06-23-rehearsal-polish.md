# Plan — P3 #11: rehearsal-mode polish (ambiguous ✗/★ mark attachment)

**Backlog #11 has two reported parts; rigorous scouting (see below) found only ONE is a real, in-scope,
deterministic bug.**

## Part A — "figures disappear from the right column on rehearsal" → investigated, NOT a fixable bug here
An Explore scout traced this end-to-end:
- **Toggling rehearsal is a NON-BUG.** The right-rail figures come from `allFigures =
  dossier.sections.flatMap(s => s.figures)` gated only on `allFigures.length > 0` (`DossierView.tsx:522`) —
  never on the `rehearsal` prop. Git confirms it was never gated on rehearsal. Toggling cannot empty the rail.
- **Serialization is symmetric + complete.** `_dossier_dict`→`_section_dict` includes `figures`
  (`api/server.py:434`); `_figitem_dict` emits all 7 fields `FigureCard` consumes. `/api/build` and
  `/api/feedback` call the identical `_dossier_dict`. No omission, no key collision (`fig_id` is board-global).
- **The only path that empties the rail is LLM Explorer non-determinism on the remember-REBUILD:**
  `/api/feedback` → `_do_build` → `build_dossier` → `_resolve_manifest` re-runs `build_llm_manifest(topic)`
  from scratch (`pipeline.py:98-101`), so the carefully-reviewed board is REGENERATED (different anatomy
  cards → different/fewer figures), not refined. (Prefs pruning is conservative — weight≥2 to remove —
  so a first-cycle remember does not deterministically drop figures.)
- **Disposition:** the proper fix is a *deterministic remember-rebuild* — thread the cached raw manifest
  through `build_dossier`/`_resolve_manifest` so remember APPLIES prefs to the same manifest instead of
  re-running the Explorer. That is a core-build-path change (manifest-injection seam) = its own slice, not
  a P3 polish change; a process-scoped memo would be unsafe (stale-manifest reuse). **Tracked as a new
  backlog follow-up (#15), not attempted here.** This PR does not touch the build pipeline.

## Part B — ambiguous ✗/★ mark attachment → the real, clean fix (this slice)
**Bug:** In rehearsal, the `✗ wrong` / `★ important` buttons render at the bottom of each claim card
(`DossierView.tsx:165-198`), directly below the claim's **sub-items** — which display as `☐` glyphs that
look like checkboxes (`DossierView.tsx:126-143`). So it's ambiguous whether ✗/★ mark the WHOLE claim or
the last sub-item / the checkboxes. They actually mark the whole claim (`onMark(heading, claim, mark)`).

---

- [x] **Step 1 — Disambiguate the rehearsal mark controls (frontend only)**
  - `web/src/components/build/DossierView.tsx` (the rehearsal mark-controls block, ~164-198):
    - Add a short mono label scoping the marks to the claim, e.g. a leading
      `<span className="font-mono text-[9px] uppercase tracking-[0.14em]" style={{ color: "#6b93ff" }}>Mark
      this card</span>` (or "Rate this claim") immediately before the ✗/★ buttons, on the same row.
    - Add a subtle top separator so the controls read as a distinct footer of the card, not part of the
      sub-item list: wrap the controls in a container with `borderTop: "1px solid rgba(255,255,255,.06)"`
      + `mt-3 pt-3` (replacing the bare `mt-3`), visually detaching them from the `☐` considerations above.
    - Give each button an explicit `aria-label` naming the target: `aria-label={`Mark this claim wrong`}` /
      `…important`} and `aria-pressed={active === "wrong"}` / `…"important"` (the buttons are toggles — the
      pressed state is currently only conveyed by color, which fails the contrast-alone rule). This both
      disambiguates for SR users AND announces toggle state.
    - The `☐` sub-item glyphs are decorative considerations, NOT interactive checkboxes — they're already
      `aria-hidden` and inside an `aria-label="Considerations"` list. Leave them; the new "Mark this card"
      label + separator is what removes the visual confusion. (Do NOT make sub-items individually markable —
      the data model marks whole claims; pretending otherwise would be a false affordance.)
  - **Verify:** `npm --prefix web run test` + `npm --prefix web run build` + `npm --prefix web run lint`.

**Non-regression:** pure presentation — no change to the mark data model (still whole-claim
`onMark(heading, claim, mark)`), no engine/data change. The new `aria-pressed`/`aria-label` strengthen a11y
(toggle state was color-only). Honest invariant intact — no fabricated affordance (sub-items stay
non-interactive because the model can't mark them).
