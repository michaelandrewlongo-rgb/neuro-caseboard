# Woven Literature Synthesis — Design

**Date:** 2026-06-21
**Status:** Approved (brainstorm), pending implementation plan
**Scope:** Ask pathway (this spec). Dossier pathway is an explicit fast-follow (separate spec).

## Problem

Two related gaps in how contemporary literature reaches the user:

1. **Recency anxiety.** Textbook publication dates lag recent neurosurgery developments. The
   concern: recent practice-changing evidence is hidden behind older corpus content.
2. **Siloed presentation.** Textbook answers (`[n]` citations) and PubMed answers (`[L#]`
   citations) are synthesized independently and shown as two separate blocks. The user wants them
   to *appear as one* — a single woven narrative — while the two **retrievals remain separate**.

### What the benchmark data actually says (3-arm run, 667 unique PubMed articles over 67 Q)

The recency hypothesis is largely already satisfied by the existing retrieval; the real lever is
*composition*, and the real residual problem is *precision*:

- Retrieved articles already skew recent: median publication year **2022**; 43% within 3 years,
  72% within 7 years; only ~27% older than 7 years. Landmark 2024–25 trials (DISTAL, ESCAPE-MeVO,
  V-REX, PROGRESS, MISTIE-III) are already being retrieved.
- Recent papers are **not** being buried — the #1 relevance slot is the *newest* on average
  (mean year 2021.8, 59% within 3y); recency decays *down* the list.
- The measured win came from **composing PubMed into the answer at all**: textbook-only arms
  scored ~78.7–80.0; the arm that folded the PubMed block in scored **83.9 (+5.2)**, winning
  54/67. Graders explicitly credited recent-trial evidence the textbooks lack.
- The residual problem is **precision** — off-topic "citation noise" on a handful of questions
  (SPINE-03/09, GENERAL-09) — *not* staleness.
- **Caveat:** the +5.2 carries a length confound (the composed answer is 2–3× longer);
  validation requires a length-matched grading pass.

**Conclusion:** The woven narrative *is* the recency win. Recency retrieval needs only a light
tie-breaker, not an aggressive date filter (a hard filter would discard ~27% legitimately
retrieved foundational papers and worsen precision). Weaving makes precision matter *more*
(inline noise is worse than siloed noise), so a lightweight precision gate is in scope.

## Goals

- Produce a **single woven narrative** in the Ask pathway from both textbook and PubMed evidence,
  with `[n]` and `[L#]` citations kept **distinct inline** and two reference lists below.
- Keep the **two retrievals separate** (Lane A textbook, Lane B PubMed).
- Surface recent developments the textbook corpus lacks (primarily via composition; secondarily
  via a light recency tie-breaker).
- Add a lightweight, deterministic **precision gate** so only on-topic literature is woven in.
- Ship behind a **feature flag**, default off, validated against the frozen 67-Q benchmark.

## Non-goals

- Dossier pathway weaving (fast-follow, separate spec).
- Aggressive recency mechanisms (hard date filter on all axes) — rejected by the data.
- A full literature precision overhaul (query-construction rewrite, semantic relevance scoring) —
  larger scope; its own brainstorm if the lightweight gate proves insufficient.
- Merging the two citation namespaces into one numbering — rejected; provenance stays explicit.

## Architecture

**Principle:** retrieval stays two separate lanes; only synthesis and presentation merge.

**Approach (chosen): single woven synthesis pass.** Both lanes retrieve independently, then **one**
LLM synthesis call receives the numbered textbook passages `[n]`, figures, and numbered literature
records `[L#]` together and writes one unified answer. This is faithful to "appear as one," is the
composition lever that scored +5.2, and adds no third "merge" LLM hop.

*Rejected alternative:* two synthesis passes + a third weave pass — more latency, more
citation-drift risk, and the weave model can distort claims it didn't ground.

The engine already separates retrieval (`Engine._plan_query`) from synthesis (`Engine._answer`),
so this is a clean fit: expose a **retrieve-only** engine entry returning either a `Clarification`
or a retrieval bundle (`hits` + `figures` + resolved `variant`), and move the *combined* synthesis
into the `neuro_caseboard` integration layer so `neuro_core` stays literature-agnostic.

### Components

| Unit | Responsibility | Depends on |
|---|---|---|
| `Engine` retrieve-only entry (`neuro_core/query.py`) | Run `_plan_query` + `_collect_figures`, return `Clarification` OR a retrieval bundle `(hits, figures, variant)`. No synthesis. | existing `_plan_query`, `_collect_figures` |
| Recency tie-breaker (`literature/retriever.py::rank_key`) | Promote a high-tier, last-N-year paper one relevance bucket. Tunable, conservative. | existing tier/recency helpers |
| Precision gate (`literature/` — new helper) | Deterministic: drop records that fail concept-overlap with rewritten query terms or fall beyond a relevance-rank ceiling; empty-after-gate falls back to single most-relevant + caution note. | existing query-term extraction, `standardize` fallback pattern |
| Woven synthesizer (`neuro_caseboard/` — new module) | One LLM call over `hits` + `figures` + gated `records`; enforce grounding/refusal contract; preserve figure note, variant prepend, C5 empty-answer guard. Returns `answer`, `[n]` citations, `[L#]` citations. | `neuro_core.synthesize` passage/figure formatters; literature record formatter |
| `qa.answer_question` orchestration (`neuro_caseboard/qa.py`) | When flag on: retrieve-only Lane A (short-circuit `Clarification`) + Lane B retrieve+gate, then woven synth. When off: today's path unchanged. | the above |
| Output assembly (`cli.py`, `briefing_pdf.py`, `app/`) | One answer block + two reference lists (`[n]`, `[L#]`). | `QAResult` |

## Lane B retrieval changes

### Recency tie-breaker (mechanism B)

In `retriever.py::rank_key` (currently sorts by `(relevance_bucket, pub_tier, recency_flag, -year)`):
let a **high-evidence-tier** paper (guideline/SR/meta/RCT) published within
`LITERATURE_RECENCY_YEARS` be promoted **one relevance bucket**, so a landmark recent trial just
below the relevance cutoff isn't dropped. Strength tunable via new `LITERATURE_RECENCY_BOOST`
(default modest). No new NCBI calls.

*Honest note:* the data suggests this is near-no-op insurance — its value is proven or disproven by
the A/B, not assumed. It must not reorder unrelated results or harm precision.

### Precision gate (before weaving)

Deterministic, runs after ranking and before synthesis:

- **Concept-overlap check:** keep a record only if its title/abstract shares ≥1 key concept with
  the rewritten-query terms (reuse existing query-term extraction). Drops off-topic citation noise
  without an LLM call.
- **Relevance-rank ceiling:** drop records beyond the strong relevance zone.
- Tunable threshold. If the gate empties the set, fall back to the single most-relevant record with
  a caution note (mirrors existing `standardize` behavior).

## Woven synthesis contract

New synthesizer in the `neuro_caseboard` layer, reusing `neuro_core.synthesize`'s passage/figure
formatting helpers and the literature record formatter. Called with textbook `hits`, `figures`, and
gated `records`.

**System prompt contract:**

- Answer **only** from the numbered textbook passages `[n]` and numbered literature studies `[L#]`.
  Cite every claim with its bracketed marker; `[n]` and `[L#]` stay **distinct inline**.
- **Grounding / refusal:**
  - Textbook covers it → answer from `[n]`, weave in `[L#]` where literature
    updates/extends/contradicts.
  - Textbook **silent**, literature covers it → answer from `[L#]` and append an explicit note:
    *"The textbook corpus did not cover this; the answer rests on contemporary literature."*
  - **Both silent** → emit `REFUSAL`.
- Preserve existing **figure note** handling and the **variant directive** ("Assuming \<variant\>"
  prepend on resolved ambiguity).

**Preserved engine safety behaviors** (carried into the woven path, which bypasses `_answer`):

- **C5 empty-answer guard** (retry once, else `REFUSAL`).
- **Ambiguity `Clarification` short-circuit** (handled at retrieve-only stage, before synthesis).

**Returns** `answer`, textbook `citations` (`[n]`), and `literature_citations` (`[L#]`).

## Output assembly (Ask)

The woven answer is **one block**, with two reference lists beneath it.

- **`QAResult`**: when `LITERATURE_WEAVE` on, `answer` = woven prose, `citations` = `[n]`
  (textbook + figures), `literature` = `[L#]`. When off, today's separate-block shape is unchanged.
- **CLI** (`cli.py::_run_ask`): woven answer, then **"Sources"** (`[n]`) and
  **"Contemporary Literature"** (`[L#]`) as two reference lists (not two answer blocks). Figures
  unchanged.
- **PDF/HTML briefing** (`briefing_pdf.py`): one answer section; `_literature_html` becomes a
  reference-list renderer for `[L#]` rather than a separate narrative section. Offline fpdf fallback
  mirrors it.
- **Streamlit** (`app/`): render the single woven answer; the two citation lists below.
- **Dossier:** untouched in this spec (separate-block behavior retained) — fast-follow.

## Configuration

In `literature/config.py`:

- `LITERATURE_WEAVE` (default **off**) — master switch for woven mode.
- `LITERATURE_RECENCY_BOOST` (default modest) — recency tie-breaker strength.
- `LITERATURE_PRECISION_GATE` (default **on** when weaving) + threshold knob.

## Testing (TDD; hermetic + scoped per CLAUDE.md)

- **Recency tie-breaker:** a recent high-tier paper just below the relevance cutoff survives
  ranking; a modest boost does not reorder unrelated results.
- **Precision gate:** off-topic record dropped; on-topic kept; empty-after-gate falls back with a
  caution note.
- **Woven synthesis (mocked synth client):** textbook-only → `[n]` only; literature-only → `[L#]`
  + textbook-silent flag; both → mixed inline + two ref lists; both silent → `REFUSAL`;
  empty-answer guard retries then refuses; variant prepend preserved.
- **Assembly:** flag off → byte-identical to today's separate-block output (regression lock);
  flag on → one block + two lists.

## Validation

Use the `neuro-caseboard-ab-test` skill:

- Run the frozen 67-Q benchmark **woven-on vs woven-off**, blinded subspecialty grading, regression
  + unsafe-output check.
- **Length-matched grading pass** to control for the +5.2 length confound the 3-arm summary flagged.
- Ship only if there are no regressions / unsafe outputs and the woven arm holds up length-matched.

## Risks

- **Length confound** inflating perceived gains → mitigated by length-matched grading.
- **Inline citation noise** if the precision gate is too loose → tunable threshold; default
  conservative; A/B-gated.
- **Behavior change in a safety-sensitive, benchmarked system** → feature flag default off; flag-off
  regression lock; A/B before any default flip.
- **Recency tie-breaker hurting precision** → conservative default; validated, not assumed.

## Rollout

1. Land Lane B changes + woven synthesizer + Ask assembly behind `LITERATURE_WEAVE` (default off).
2. A/B on the frozen benchmark (length-matched). Tune precision gate / recency boost.
3. Flip default only if validated.
4. Fast-follow: Dossier weaving (separate spec) once Ask weave is validated.
