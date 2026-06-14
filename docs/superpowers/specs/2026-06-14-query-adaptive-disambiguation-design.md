# Query-adaptive variant disambiguation — design

**Date:** 2026-06-14
**Status:** Approved design
**Author:** Michael Longo + Claude

## 1. Context & problem

Independent grading of a "decompressive craniectomy for TBI" briefing found the engine **conflated
two distinct operations** the corpus files under one heading — the **unilateral
frontotemporoparietal (FTP) hemicraniectomy** (wanted) and the **bifrontal (Kjellberg-type)
decompression**. Symptoms in the output: an incision described "to the *contralateral* zygoma" (a
bicoronal/bifrontal trajectory) and a bifrontal pediatric figure attached to a unilateral answer.

This is **intra-topic variant conflation**, not a cross-domain leak: both variants are
cranial/anterior, so the existing STRICT figure-region guard (`neuro_core/query.py` figure-fusion;
`neuro_core/figure_guards.py`) is blind to it by construction — it catches `cranial↔spine` /
`non-op-angio`, not "right region, wrong *variant*." The research memo
(`docs/research/2026-06-14-query-adaptive-disambiguation.md`) frames the fix as **AmbigQA** (Min et
al., EMNLP 2020): an ambiguous question should resolve to a *disambiguated rewrite*, not a presumed
merge.

**Empirical anchor (already validated):** issuing the variant-resolved query a disambiguation step
*would auto-generate* ("unilateral FTP hemicraniectomy, not bifrontal") drove
`bifrontal`/`bicoronal`/`Kjellberg` mentions to **0**, removed the contralateral-zygoma incision,
kept the correct 12×15 cm flap, and dropped the bifrontal figure. **The resolve mechanism is
proven.** The open work is the *detect* + *decide* front-end, the *resolve* wiring, and an eval.

### Why this matters for the end product specifically

The briefing PDF (`neuro_caseboard/briefing_pdf.py`) is a **pure render of `QueryResult`** — it
adds zero clinical content and makes zero correctness decisions. So every correctness lever lives
upstream, and this fix lands exactly where the bound is set (`Engine.query()`, before synthesis).
The PDF also *raises the stakes* of conflation: a printed, brand-styled, citation-bearing document
reads as authoritative and has no interactive "which did you mean?" affordance.

## 2. Decisions (locked during brainstorming)

- **Decide-mode default = auto-pick likeliest + name the assumption.** On a confident detection the
  engine commits to the single most-likely variant from retrieval context and opens the answer with
  a bold line naming the assumption (e.g. **"Assuming unilateral FTP hemicraniectomy (most
  consistent with retrieved sources)."**). This honors "never force the user to write
  hyper-specific queries."
- **Low-confidence fallback = clarify first.** When the top two variants are near-tied, the engine
  returns a **clarifying question** instead of a briefing — the AmbigQA "high-stakes fallback." No
  PDF is produced for that case until the user answers.
- **Detection = hybrid, gated so non-ambiguous queries cost nothing.** A cheap gate (curated
  variant-taxonomy topic-match **or** ≥2 named-variant clusters in the already-retrieved top-k)
  runs first; only when it trips do we spend an LLM `query_analyze()` pass. Queries that don't trip
  the gate run **byte-identical to today** — the no-regression guarantee is structural.
- **Resolve via the validated lever.** Re-retrieve on the chosen variant's rewrite, plus a
  synthesis directive that forbids merging steps across variants.
- **Cost is acceptable.** +1 Vertex LLM pass (only when gated) + one extra retrieval on the
  resolved rewrite. Per the standing quality-first-on-free-Vertex-credits preference, money cost is
  a non-issue; only modest latency on the *ambiguous* path.

## 3. Architecture & control flow

New pre-synthesis stage inside `Engine.query()` (`neuro_core/query.py:158`). Pseudo-flow:

```
def query(question):
    top = _retrieve(question)                      # unchanged
    gate = ambiguity_gate(question, top)           # CHEAP: taxonomy match OR >=2 variant clusters
    if not gate.tripped:
        return _answer(question, top)              # IDENTICAL to today's path

    analysis = query_analyze(question, top)        # ONE Vertex LLM pass (taxonomy-seeded)
    if not analysis.ambiguous:
        return _answer(question, top)              # gate false-positive -> today's path

    if analysis.confidence < CLARIFY_THRESHOLD:    # near-tied
        return Clarification(question, analysis.variants)

    resolved = analysis.chosen.rewrite
    top2 = _retrieve(resolved)                      # the validated lever
    return _answer(resolved, top2, variant=analysis.chosen)
```

`_answer(question, top, variant=None)` factors out today's `_collect_figures → synthesize →
refusal-handling → QueryResult` body (currently inline at `query.py:159-169`) so both paths share
it. When `variant` is set and synthesis did not refuse, `_answer` forwards the variant directive to
`synthesize()` and prepends the deterministic bold "Assuming …" line (§4.3).

### 3.1 Output contract

`Engine.query()` returns **`QueryResult | Clarification`**. `Clarification` is a small new dataclass
(`question: str`, `variants: list[VariantRewrite]`, optional human-readable `prompt`). Rationale: a
clarifying question genuinely is *not* a briefing; a union forces each surface to branch rather than
silently rendering an empty PDF.

Call sites that render a result branch on the type:
- `neuro_caseboard/cli.py:15` — the only direct caller of `query()` today; prints the answer block
  on `QueryResult`, prints the clarify prompt + candidate variants on `Clarification`.
- Briefing/PDF export and the Streamlit surface: on `Clarification`, **produce no PDF** — surface
  the question instead.

## 4. Components

### 4.1 `ambiguity_gate(question, top) -> Gate` (cheap, no LLM)
- **Taxonomy match:** a curated `variant_axes` table — `{axis: [variant labels]}`, e.g.
  `decompressive-craniectomy → {unilateral FTP, bifrontal/Kjellberg}`, `ACDF ↔ corpectomy`,
  `pterional ↔ orbitozygomatic`, `EVD ↔ lumbar drain`. Topic→axis match trips the gate
  (high-precision).
- **Retrieval-cluster signal:** scan the already-fetched `top` for ≥2 distinct named variants
  (reuses passages we already have — free). Recall booster for un-curated topics; the cluster
  margin also seeds the confidence estimate.
- Neither trips ⇒ `tripped=False` ⇒ fall through to today's path.

### 4.2 `query_analyze(question, top) -> QueryAnalysis` (one Vertex LLM pass, only when gated)
- Taxonomy-seeded prompt; sees `top` so it can both pick and gauge separation.
- Returns `{ambiguous: bool, axis: str|None, variants: [VariantRewrite{label, rewrite}],
  chosen: VariantRewrite|None, confidence: float}`.
- New module `neuro_core/query_analyze.py` (own LLM client via `make_synth_client`, mirroring
  `live_reconcile.py`'s pattern). Keeps `query.py` focused.

### 4.3 Resolve / synthesis directive
- `synthesize()` (`neuro_core/synthesize.py:88`) gains an optional `variant_directive: str | None`.
  When set, the user message / system prompt appends: *"Answer for variant X only; if the corpus
  blends variants, separate them — never merge steps across variants."* Today the prompt has no
  variant rule at all.
- The **"Assuming …" line is prepended deterministically by the engine** (not left to the synth
  LLM) so it is guaranteed present, exact, and unit-testable: `_answer` prefixes the synthesized
  answer with `**Assuming {label} (most consistent with retrieved sources).**` on the resolved
  path. (Not prepended on a refusal — a "Not found" answer gets no assumption line.)
- The line is a **bold lead paragraph, not a `>` blockquote** —
  `briefing_pdf.py::_md_to_html` only renders `##`/`###`/`*`/`-`/`**bold**`; a blockquote would
  ship as a literal `>`. (If a blockquote is wanted later, extend the renderer; out of scope here.)

## 5. Data flow & figure parity

`select_figures()` (`query.py:153`) calls `_retrieve(question)` directly for eval. It must run on
the **resolved** query when the prose path resolved, or figure-eval silently diverges from the
answer. Decision: route both prose and figure selection through the same resolved query — thread the
resolution so `select_figures` and `query` agree.

## 6. Error handling & risks

- **`query_analyze` LLM failure / malformed JSON:** fail *open* to today's path (treat as
  not-ambiguous). Never block a normal answer on the new stage.
- **Over-disambiguation (spurious clarify / wrong split):** mitigated by (a) cheap gate before any
  LLM, (b) `CLARIFY_THRESHOLD` tuned conservative, (c) the over-ask metric in eval.
- **Silent wrong pick:** the named assumption surfaces the choice; the **wrong-variant-rate** metric
  measures it directly.
- **Confidence calibration:** `CLARIFY_THRESHOLD` is a single tunable constant; start conservative
  (prefer auto-pick, clarify only on strong ties) to keep over-ask low.

## 7. Testing & eval

Per the `fixing-pipeline-output-errors` discipline (prove ACTIVE on real cases; prove no
regression):

- **Ambiguous-query set:** DHC, ACDF/corpectomy, pterional/OZ, EVD/lumbar-drain.
- **Three metrics:** **conflation rate** (does the answer mix variants?), **over-ask rate** (does it
  clarify when it shouldn't?), **wrong-variant rate** (did auto-pick choose wrong?). Anchor: scoped
  DHC → **0** `bifrontal`/`Kjellberg` mentions.
- **No-regression hold-out:** a set of non-ambiguous queries must return **byte-identical** results
  (answer + citations + figures) with the stage enabled — the cheap gate makes this structural, the
  test makes it enforced.
- **Unit tests:** `ambiguity_gate` (taxonomy hit, cluster hit, clean miss), `query_analyze` JSON
  parsing + fail-open, `Clarification` rendering in CLI, the bold "Assuming …" line surviving
  `_md_to_html` into the PDF.

## 8. Files touched

- **New:** `neuro_core/query_analyze.py` (gate + LLM analyze + dataclasses), eval harness under
  `eval/` for the ambiguous-query set.
- **Changed:** `neuro_core/query.py` (factor `_answer`, insert the stage, thread resolution through
  `select_figures`); `neuro_core/synthesize.py` (`variant_directive`); `neuro_caseboard/cli.py`
  (branch on `Clarification`); briefing/PDF + Streamlit surfaces (no-PDF on `Clarification`).

## 9. Out of scope

- Multi-axis ambiguity (two independent variant axes in one query) — single-axis first.
- Learned/internal-state ambiguity detection ("Sparse Neurons") — the taxonomy+cluster lever is the
  pragmatic version.
- Blockquote support in the PDF renderer.

## 10. Relationship to other work

This is the **prose analogue of the figure-precision guard** (`figure_offtarget` strict) — right
region, wrong *variant*. It generalizes across neurosurgery and removes the burden of
hyper-specific queries.

## Sources

See `docs/research/2026-06-14-query-adaptive-disambiguation.md` (AmbigQA, CondAmbigQA, CLAMBER,
Structured-Uncertainty/EVPI, Modeling Future Conversation Turns, Adaptive-RAG).
