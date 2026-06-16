# Design — WS-2: Ground the case dossier in the textbook corpus (`[n]`)

- **Date:** 2026-06-16
- **Status:** Approved (locked by LOOP_PROMPT §3 WS-2); implementation in progress
- **Branch:** `worktree-loop+output-quality`
- **Loop:** Output-Quality (`caseboard case`), Pass 2 of 6

## 1. Context & problem (mechanized from real intermediate data)

The brief blamed `pipeline._collect_figures` (its `target_file == "03-anatomy-at-risk.md"` filter, a
build-only file absent from the case taxonomy) for the case dossier earning "almost no corpus `[n]`".
Reproducing with an **injected fake corpus retriever** refined the diagnosis:

- `enrich_manifest` already attaches corpus evidence to **every** case card (`status=success`,
  `papers=3`) — enrichment is *not* the broken layer.
- `_sources_from_audited` yields evidence records and the "Evidence Sources" appendix is populated.
- **But `compile._compile` emits ZERO inline `[n]` markers** — it only turns `card_evidence`
  (figure records with a `figure_path`) into `FigureItem.citation` strings and lists deduped
  appendix sources. It never reads the cards' `.papers` to put an inline `[n]` on a claim.

So the owning layer is **`compile._compile`**: there is no inline-citation mechanism for case claims
at all. `_collect_figures`'s hardcoded literal is a *separate* (figure-collection) defect.

## 2. Decisions

- **Add inline `[n]` numbering in `_compile`, gated to the case path.** `_compile` gains a
  `corpus_inline: bool` + `corpus_eligible: set[str]`. When on, each primary claim in a
  corpus-eligible section whose card carries `.papers` gets inline `[n]` markers appended to its
  text, keyed to a numbered **Evidence Sources** list built from those same papers. The build path
  (`compile_dossier`) passes the defaults (off) → **byte-identical**. Only `compile_case_dossier`
  turns it on.
- **`[n]` = "a retrieved corpus record backs this claim."** A claim carries `[n]` iff its card has
  ≥1 retrieved paper (regardless of `supported` vs `needs_review`, which is the orthogonal status
  axis). Every `[n]` resolves to an entry in the numbered Evidence Sources list — `cited ⊆ retrieved`
  by construction; fabrication is impossible.
- **The number space is the Evidence Sources appendix.** The numbered list is built *inside*
  `_compile` from the cited papers (dedup by citation string = the paper `title`, first-seen order),
  so claim `[k]` ↔ Evidence Sources item `k`. No mismatch with a separately-built list.
- **`[n]` (corpus) and `[L#]` (PubMed) never merge.** `[L#]` is attached post-compile at the section
  level (`attach_case_literature`); `[n]` is inline at the claim level. Disjoint number spaces,
  asserted by test.
- **`_collect_figures` becomes taxonomy-driven.** Its eligible-target-file set is a parameter; the
  build path keeps `{"03-anatomy-at-risk.md"}` (unchanged), the case path passes the case
  figure-eligible files (`04/05/08/09`). Offline (no corpus/figret) it still returns empty → no
  change to required CI.
- **`build_case_dossier` gains an injectable `retriever=`.** So the gate/tests can drive corpus
  enrichment deterministically with a fake retriever; defaults to `build_retriever()` when enriching.
- **Offline degrade unchanged.** With no retriever (required CI), cards have no papers → 0 `[n]`, the
  case path builds with no error, byte-stable vs the prior offline output.

## 3. Detailed design (exact files / functions)

- `neuro_caseboard/case_sections.py`: add `CORPUS_ELIGIBLE_FILES = {"04-operative-plan.md",
  "05-risk-and-rescue.md", "08-surgical-technique.md"}` and `CASE_FIGURE_FILES` (`04/05/08/09`).
- `neuro_caseboard/compile.py`:
  - `_compile(..., corpus_inline=False, corpus_eligible=frozenset())`. After claims are built per
    section, if `corpus_inline` and `tf in corpus_eligible`, for each claim whose source card has
    `.papers`: register each paper's citation (`title`) in an ordered, de-duplicated
    `corpus_citations` list and append `[k]` (capped at the first 2 papers) to `claim.text`. Build
    the "Evidence Sources" appendix from `corpus_citations` (the numbered list) when `corpus_inline`;
    else keep the current `evidence`-derived appendix (build path unchanged).
  - `compile_case_dossier(...)` passes `corpus_inline=True, corpus_eligible=CORPUS_ELIGIBLE_FILES`.
- `neuro_caseboard/pipeline.py`:
  - `_collect_figures(..., eligible_files=frozenset({"03-anatomy-at-risk.md"}))`; the case call
    passes `CASE_FIGURE_FILES`.
  - `build_case_dossier(..., retriever=None)`: `retriever = retriever if retriever is not None else
    (build_retriever() if enrich else None)`.
- `eval/case_eval.py`: extend to assert `[n]` on the corpus-eligible sections via an injected fake
  corpus retriever (zero fabrication).
- `eval/quality_gate.py`: compute `corpus_n_coverage` by building the gt dossier with an injected
  fake corpus retriever; bump `eval/BASELINE.json`.

## 4. Acceptance criteria (LOOP_PROMPT §3)

- With an injected fake corpus retriever, case Operative Plan / Surgical Technique / Risks claims
  carry ≥1 `[n]` each, all resolving to retrieved records; `[n]`/`[L#]` disjoint.
- With no retriever (offline default), the case path still builds, 0 `[n]`, no error — byte-stable
  vs the prior offline case output.
- 0 regressions; `build` path unchanged.

## 5. Testing strategy (TDD)

`tests/test_compile.py` / `tests/test_pipeline.py` (RED → GREEN):
1. `test_case_claims_carry_corpus_citations` — build_case_dossier with a fake corpus retriever →
   Operative Plan / Surgical Technique / Risks each have ≥1 claim with an inline `[n]`; every `[n]`
   index resolves to an Evidence Sources entry.
2. `test_corpus_and_literature_axes_disjoint` — `[n]` ints and `[L#]` ints never collide.
3. `test_offline_case_path_has_no_corpus_citations` — no retriever → 0 `[n]`, builds fine.
4. `test_build_path_unchanged` — `compile_dossier` output identical with/without the new param
   defaults (byte-identical claim text).
5. `test_no_fabrication` — cited `[n]` ⊆ the retrieved papers' citations.

## 6. EVAL

- Offline: `case_eval.py` asserts `[n]` on corpus-eligible sections via the injected retriever
  (zero fabrication); `quality_gate.py` `corpus_n_coverage` rises from 0.0; BASELINE bumped with a
  LOOP_LOG note. Live (WS-6): text-judge accuracy ≥ 8/10 (deferred).

## 7. Risks

- **Build-path drift.** `_compile` is shared. Mitigation: the new behavior is gated off by default;
  `test_build_path_unchanged` + the existing `test_compile`/`render` goldens guard it.
- **Number-space mismatch.** Mitigation: the numbered list is built inside `_compile` from the same
  papers it cites — `cited ⊆ listed` by construction.
- **Dedup interaction.** `[n]` is appended to `claim.text`, but dedup keys on `claim.dedup_text`
  (`raw` = the original question), so near-dup collapse is unaffected.

## 8. Out of scope

- The real-anatomy structures-at-risk figure (WS-4) — WS-2 only broadens `_collect_figures`
  eligibility and grounds the text `[n]`.
- Raising section depth (WS-3) or intake accuracy (WS-5).
