# Q&A figure-precision pass — design

**Date:** 2026-06-14
**Status:** Approved design
**Author:** Michael Longo + Claude

## 1. Context & problem

Two independent evaluations (an independent-neurosurgeon agent over 5 questions, and a 2-question
endovascular run) converged on one weakness: the Q&A figure lane returns a reliable **lead**
figure but a noisy **tail** — thematically-adjacent but off-domain plates. The clearest miss was a
**spine open-door laminoplasty figure surfaced for an M1 thrombectomy answer**.

Root cause (named, in the correct layer): the Q&A path calls
`neuro_core/query.py::_caption_hits → caption_index.retrieve(question, topic="")`, and
`FigureRetriever.retrieve` only runs guards **when a topic is supplied** (`if topic:`). Boards pass
a topic, so their figures are guarded; **Q&A passes `topic=""`, so guards are dormant.** The
guards that would catch these leaks already exist in `neuro_core/figure_guards.py`. This is
distinct from the earlier Gemini re-captioning work, which fixed caption *recall/quality* (finding
and naming the right plate); it did not add domain *filtering* to the Q&A path.

## 2. Decisions (locked during brainstorming)

- **Policy: hard-block clear conflicts** (not demote, not the full board set).
- **Q&A strict guard set = `cranial↔spine` (caption + source book) + `non-op-angio` (positioning/
  projection setup).** Both are high-precision with negligible recall risk.
- **`diagnostic-image` is EXCLUDED from the Q&A set** (kept board-only). Evidence: endovascular/
  vascular figures are inherently angiographic and their Gemini captions name the modality
  ("computed tomography", "magnetic resonance", "ct angiogram"), so `_DIAGNOSTIC_IMAGE` would
  over-block exactly the figures Q&A wants. *(This refines the initial "operative↔diagnostic"
  framing; `non-op-angio` keeps the safe part — positioning diagrams — while not touching real
  angio findings.)*
- **Also excluded** (board-only): `sellar`, `anterior↔posterior-fossa`, spine `level/CVJ-subaxial`,
  `peripheral-nerve` — each needs a precise *case sub-region* that free-text questions don't
  reliably supply, so applying them risks false-blocking relevant figures.
- **Region signal = the question text itself** (no LLM). Clinical questions almost always name the
  region ("M1 MCA", "C5-6 ACDF"); the guard's existing `_CRANIAL_SIG`/`_SPINE_SIG` term lists
  already match that vocabulary. A question with no region term ⇒ cranial↔spine simply doesn't fire
  (graceful: no false block).
- **Boards are unchanged** (default behavior preserved).

## 3. Detailed design

### 3.1 `neuro_core/figure_guards.py`
Add a keyword-only `guards` selector to `figure_offtarget`:

```python
def figure_offtarget(caption, topic, book="", context="", *, guards="full") -> bool:
```
- `guards="full"` (default) — current behavior, unchanged → **boards identical**.
- `guards="strict"` — run ONLY the `non-op-angio` caption check and the `cranial↔spine`
  (caption + book) check, then return `False`. The `diagnostic-image`, `peripheral-nerve`,
  `sellar`, `anterior↔posterior-fossa`, and `level/CVJ-subaxial` checks are gated behind
  `if guards == "full":` and are skipped in strict.

Concretely: the `_NONOP_ANGIO` check and the two cranial↔spine `return True` branches run in both
modes; everything else is full-only. (The unconditional `_DIAGNOSTIC_IMAGE` check moves under the
full-only gate.)

### 3.2 `neuro_core/figure_retriever.py`
`FigureRetriever.retrieve(query, *, topic="", top_n=8, guard_set="full")`. When `topic` is set,
pass `guard_set` through to `figure_offtarget(..., guards=guard_set)`. Default `"full"` keeps the
board path identical.

### 3.3 `neuro_core/query.py::_caption_hits`
Change the single call from `retrieve(question, topic="", top_n=k)` to
`retrieve(question, topic=question, top_n=k, guard_set="strict")`. The question doubles as the
region signal; only the strict subset runs.

## 4. Acceptance criteria

- **Active on real data:** re-running the endovascular + neurosurgeon questions, the spine-in-
  thrombectomy plate (and other clear cranial↔spine / positioning-diagram leaks) no longer appear,
  AND the lead/in-domain figures — *including all angiographic endovascular figures* — still
  appear (no over-block). >0 real figures change; the endovascular angio figures must NOT drop.
- **No collateral on boards:** the board `figure_eval` (MCA/CPA/C1-C2) is byte-identical to before
  (guaranteed by `guards="full"` default; verified by re-run).
- **Unit + full suite green.**

## 5. Testing strategy

- **`figure_guards` unit:** `figure_offtarget(spine_caption, cranial_question, book, guards="strict")`
  → True; `figure_offtarget(angio_caption_with_"computed tomography", endovascular_question,
  guards="strict")` → **False** (diagnostic-image NOT applied in strict — the key regression
  guard); a sellar plate on a non-sellar cranial question → False in strict (sellar is full-only)
  but True in full; positioning-diagram caption → True in strict. Confirm `guards="full"` results
  are unchanged for the same inputs where the full guard applies.
- **`figure_retriever`:** `retrieve(..., guard_set="strict")` excludes a spine row on a cranial
  query but keeps an angio row; `guard_set="full"` (default) matches today.
- **Real-data validation (fixing-pipeline-output-errors discipline):** a script re-runs the
  endovascular + neurosurgeon questions and prints the figure lists before/after; manually/blind-
  judge confirm the leak is gone and angio figures survive. Re-run `eval` figure parity for boards.

## 6. Risks & mitigations

- **Over-block of angio figures** → the precise reason `diagnostic-image` is excluded; validated
  explicitly on the endovascular set (angio figures must survive).
- **Question lacks a region term** → cranial↔spine doesn't fire; no false block (graceful).
- **Board regression** → impossible by construction (default `guards="full"`); still verified by
  figure_eval re-run.

## 7. Out of scope
- Demotion/soft-ranking (we chose hard-block).
- LLM-based region classification (raw question suffices).
- The other board-only guards on Q&A (sellar, fossa, level, peripheral-nerve).
- Any caption/recall change (that was the Gemini work).

## 8. Resolved decisions
- Hard-block; strict set = **cranial↔spine + non-op-angio**; diagnostic-image and the sub-region
  guards stay board-only; region signal = the question; boards unchanged (default `guards="full"`).
