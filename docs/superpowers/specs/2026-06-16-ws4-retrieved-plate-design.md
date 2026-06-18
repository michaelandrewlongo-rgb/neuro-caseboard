# Design — WS-4: Real-anatomy structures-at-risk figure (retrieved plate)

- **Date:** 2026-06-16
- **Status:** Approved (locked by LOOP_PROMPT §5 WS-4); implementation in progress
- **Branch:** `worktree-loop+output-quality`
- **Loop:** Output-Quality (`caseboard case`), Pass 4 of 6

## 1. Context & problem

The `anatomy_map` archetype is the documented figure ceiling: an abstract node scatter that cannot
name real anatomy ("structure at risk (medial)"). The corridor schematic is already 9–10/10 and must
stay **byte-identical**. WS-4 renders the at-risk map as an **annotated crop of a RETRIEVED real
anatomical plate** via the textbook-rag figure lane, falling back to the deterministic schematic when
no figure corpus is available (offline CI).

## 2. Decisions

- **A retrieved plate is a *reference* image, labeled honestly** (LOOP_PROMPT §1.7): caption =
  `Reference plate (not this patient's imaging): <book, p.N>`, carrying the corpus citation. The
  reader and the judge are never misled about the source.
- **The plate is guarded against the case.** Reuse `figures_gen.guard.guard_spec`: a plate whose
  region/level/side contradicts the case is rejected and we fall back to the schematic. The retrieved
  record's caption → a minimal `FigureSpec` (region = caption, level parsed from the caption) drives
  the existing region/level guard.
- **PIL only — no new dependency.** `render.render_plate` opens the retrieved PNG, normalizes size,
  and draws a top reference banner (and the citation) with the existing PIL stack. Deterministic
  given the same plate.
- **Corridor frozen.** `render_spec` is untouched; only `anatomy_map` specs are eligible for a plate.
  The corridor schematic path renders exactly as before → `figure_spec_eval` byte-stability stays
  green.
- **Offline-safe.** `generate_case_figures(..., figret=None)` → all deterministic schematics (current
  behavior, corridor byte-identical). `build_case_dossier` builds the figure retriever
  (`build_figure_retriever`, `None` offline) and passes it down.

## 3. Detailed design

- `figures_gen/plate.py` (new):
  - `build_plate_figure(case, figret, out_dir, index, *, query=None) -> FigureItem | None`: query the
    figret keyed by region/level + "structures at risk"; for the first retrieved record with an
    existing `figure_path` that **passes the guard**, render an annotated crop and return a
    `FigureItem` (reference-plate caption + corpus citation). Returns `None` when no figret, no
    record, missing file, or all guard-rejected → caller falls back to the schematic.
  - `_plate_spec_from_record(rec, case)`: a minimal `FigureSpec(archetype="anatomy_map",
    region=caption, level=<parsed>, …)` for the guard.
- `figures_gen/render.py`: `render_plate(src_path, out_path, *, citation, labels=())` — PIL open →
  RGB → scale to a standard width → top reference banner + citation (+ optional structure labels) →
  save. `render_spec` untouched.
- `figures_gen/__init__.py`: `generate_case_figures(case, out_dir, *, complete_fn=None, figret=None,
  start_index=1)` — for an `anatomy_map` spec with a figret, try `build_plate_figure`; on success use
  the plate, else render the deterministic schematic. Corridor/other specs unchanged.
- `pipeline.py`: `build_case_dossier(..., fig_retriever=None)`; when `figures_dir` is set, resolve
  `fig_retriever or build_figure_retriever()` and pass it to `generate_case_figures`.

## 4. Acceptance criteria (LOOP_PROMPT §5)

- With an **injected fake figure retriever**, the at-risk figure is a guard-passing annotated
  retrieved plate with a real citation and the "Reference plate (not this patient's imaging)"
  caption; with no retriever it is the deterministic schematic (corridor byte-identical).
- A region/level/side-contradicting plate is **rejected** by the guard (unit test → schematic).
- No new dependency; 0 regressions.

## 5. Testing strategy (TDD)

`tests/test_figure_plate.py` (new) + `tests/test_case_figures.py`:
1. `test_plate_used_when_figret_available` — fake figret returns a record pointing at a real PNG
   (written with PIL in the test) → an `anatomy_map` FigureItem with the reference-plate caption +
   citation; the file exists and is a valid PNG.
2. `test_contradicting_plate_rejected_falls_back_to_schematic` — fake figret returns an off-region
   plate → guard rejects → the at-risk figure is the deterministic schematic (no reference caption).
3. `test_no_figret_is_deterministic_schematic` — `figret=None` → schematic captions only (current
   behavior), corridor byte-identical.
4. `tests/test_figure_render.py` — `render_plate` writes a valid PNG with the banner; deterministic.
5. Corridor byte-stability (`figure_spec_eval`) unchanged.

## 6. EVAL

- Offline: `figure_spec_eval.py` corridor byte-stable + guard-rejects-contradiction stays N/N; a new
  "plate preferred when available, schematic offline" check folds into `quality_gate.py`.
- Live (WS-6, deferred): structures-at-risk image-judge ~7 → ≥ 8/10; corridor 9–10 preserved.

## 7. Risks

- **Corridor drift.** Mitigation: `render_spec` untouched; only `anatomy_map` is plate-eligible; the
  byte-stability eval guards it.
- **Misleading source.** Mitigation: the mandatory "Reference plate (not this patient's imaging)"
  caption + the guard (region/level/side) — figure honesty, not a disclaimer.
- **Missing/oversized plate file.** Mitigation: existence check + try/except → fall back to schematic.

## 8. Out of scope

Intake accuracy (WS-5); the keyed live image judge run (WS-6); a semantic structure-label layer
beyond the plate caption.
