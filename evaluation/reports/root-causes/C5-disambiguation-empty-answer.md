# C5 — Disambiguation re-call returns an empty answer (SPINE-02)

**Run:** `evaluation/runs/baseline-20260620-134705/run.jsonl` line 10 (SPINE-02).
**Status recorded:** `not_gradable`, `error_details = "engine returned an empty/None answer"`,
`selected_variant = "Cervical"`, latency 93.2s, the **only** not-gradable answer in the baseline.

---

## 1. The defect in one sentence

A disambiguated/narrowed re-call whose synthesis returns an **empty string** surfaces verbatim as a
non-answer, because the only post-synthesis guard (`is_refusal`) matches the literal abstention string
but **not** the empty string — so `""`/`None` slips through every layer to the runner, which marks it
`not_gradable`.

---

## 2. Answer-path trace (FACT — file:line)

The runner drives `neuro_caseboard.qa.answer_question` in-process and handles disambiguation itself:

1. **Clarification, then external re-call.** `evaluation/scripts/run_benchmark.py:285-294`
   (`_resolve_answer`): calls `answer_fn(question)`; if the result is a `Clarification` (duck-typed:
   has `.variants`, no `.answer`, `run_benchmark.py:84-85`), it picks a variant via `choose_variant`
   (`run_benchmark.py:88-98` — **longest `.label`, first on tie**) and re-calls
   `answer_fn(chosen.rewrite)`. Note: `_resolve_answer` re-calls **once** and does *not* re-check the
   second result for a clarification or an empty answer.

2. **`answer_question` knows nothing about the original.** `neuro_caseboard/qa.py:103-132`. The
   re-call receives the *rewrite* as a fresh question. Lane A is `neuro_core.query.query` (`qa.py:107-109`).
   A `Clarification` short-circuits (`qa.py:124-125`); otherwise it returns
   `QAResult(answer=qr.answer, …)` at **`qa.py:131`** with **no empty/None guard**. The literature lane
   (Lane B) is strictly additive and never substitutes for an empty Lane A answer.

3. **Engine resolves the rewrite and synthesizes.** `neuro_core/query.py:219-223` (`Engine.query`) →
   `_plan_query` (`query.py:177-191`) retrieves passages, runs the gate/analyze, and on a normal query
   returns `_Resolved`; then `_answer` (`query.py:204-217`) calls `self.synth_fn` and returns a
   `QueryResult`.

4. **THE GAP — where empty is produced and passes through:**
   - `neuro_core/synth_clients.py:104` — `VertexSynthClient.generate` returns **`resp.text or ""`**.
     Gemini 2.5-pro (a *thinking* model) can return a candidate with **no text part** (budget consumed
     by `thoughts`, or a transient `MAX_TOKENS`/`RECITATION`/`SAFETY`/empty-candidate), yielding `""`.
   - `neuro_core/synthesize.py:95,103` — `synthesize` passes that `""` straight into `Synthesis.answer`.
   - `neuro_core/query.py:209` — `_answer` guards only with `is_refusal(syn.answer)`. **`is_refusal("")`
     is `False`** (`synthesize.py:23-32`: it requires `norm(answer) == norm(REFUSAL)`; `"" != "not found
     in the provided sources"`). So the empty answer is **not** caught and is returned as
     `QueryResult(answer="", …)` (`query.py:213-217`).
   - `neuro_caseboard/qa.py:131` — returns `QAResult(answer="", …)`. No guard.
   - `evaluation/scripts/run_benchmark.py:383-391` — runner reads the empty answer, then
     `if not answer_text or not str(answer_text).strip(): status = "not_gradable"`.

**There is no existing empty-answer guard anywhere on the path.** `is_refusal` is the only post-synthesis
check and it is equality against the literal refusal string, so an empty/`None` answer is structurally
invisible to it.

---

## 3. Live reproduction (FACT)

Worktree-authoritative `python3`, live Vertex/Gemini 2.5-pro, INDEX_DIR default
(`~/neuro-textbook-rag/index`). `provider=vertex model=gemini-2.5-pro retrieve_k=40 rerank_k=12`.

**Call 1 — `_plan_query(<SPINE-02 question>)` → `Clarification`** with two variants:

| label | rewrite |
|-------|---------|
| `Cervical` | "Should motion-preserving procedures—**cervical** disc replacement, facet replacement, and tethering—replace fusion in selected patients with **cervical spine** pathology?" |
| `Lumbar` | "Should motion-preserving procedures—**lumbar** disc replacement, facet replacement, and tethering—replace fusion in selected patients with **lumbar spine** pathology?" |

`choose_variant` (longest label) → **`Cervical`** (both labels reproduce the baseline's `selected_variant`).

**Retrieval for the `Cervical` rewrite:** `n_passages = 12`, top scores
`0.9829 / 0.9808 / 0.9747 / 0.9692 / 0.9641 / 0.9571` (Benzel Spine, Schmidek & Sweet, Vaccaro,
Greenberg). **Retrieval is healthy — not thin.**

**Call 2 — `engine.query(<Cervical rewrite>)`:** returned a **full 3868-char answer, 15 citations**,
`finish_reason = FinishReason.STOP`, `candidates_token_count=827`, `thoughts_token_count=2774`.
Answer text begins: *"Yes, in selected patients, motion-preserving procedures are recommended
alternatives to fusion for treating cervical spine pathology [2, 6]…"*

**Interpretation (FACT + HYPOTHESIS):** the identical narrowed rewrite that produced `None` in the
baseline produced a complete, well-cited answer on re-run. Therefore the empty answer was **transient,
not structural**:
- **Refuted:** thin retrieval (12 strong passages, top 0.98).
- **Refuted:** synthesis structurally returning `None` (the synth path returns whatever the client
  returns; here it returned a full answer).
- **Confirmed mechanism:** a **transient empty `resp.text` from Gemini** (`synth_clients.py:104`,
  `resp.text or ""`), surfaced only because **no empty-answer guard exists** and `is_refusal("")` is
  `False`. *(HYPOTHESIS for the exact baseline finish_reason — not captured in the recorded run; the
  re-run finished STOP. The reliability defect is independent of which non-STOP reason caused the empty
  text.)*

---

## 4. Defect layer & the minimal fix

**Layer:** synthesis robustness / infra (transient empty LLM output), surfaced because the **query
path has no empty-answer guard**. *Not* a retrieval defect and *not* a query-understanding defect for
the empty symptom.

### Primary fix (recommended) — empty-answer guard in `Engine._answer`
**Location:** `neuro_core/query.py::Engine._answer`, at the existing guard seam **lines 208-217**
(immediately where `is_refusal` is already checked at line 209).

**What it should do:** after `syn = self.synth_fn(...)`, detect an empty/whitespace answer that is *not*
a refusal — `if not (syn.answer or "").strip():`. On empty, **retry `self.synth_fn(...)` once** (the
empty is transient — the identical input succeeded on re-run); if it is *still* empty, **degrade to the
honest abstention** `return QueryResult(answer=REFUSAL, citations=[], figures=[])` (import `REFUSAL`
from `synthesize`). This guarantees `answer_question` can never return an empty/`None` answer for *any*
query — narrowed or not — and converts a `not_gradable` into either a real answer (retry) or a gradable
abstention. It sits at the same layer that already drops citations/figures on refusal, so it is the
minimal, architecturally-consistent change.

**Why not `answer_question` (`qa.py`) as the hypothesis suggested:** in the route SPINE-02 took, the
narrowing happens in the **runner** (`choose_variant` + re-call), so `answer_question` receives only the
rewrite and **has no reference to the original broad question** — it cannot "fall back to the original."
The engine's *internal* high-confidence path (`query.py:190-191`, `confidence >= CLARIFY_THRESHOLD`)
*does* know both `question` and `chosen.rewrite`; a "re-answer the original on empty" fallback could
live in `Engine.query`/`_plan_query` but would cover **only** that internal path, not the external
clarify route. A belt-and-suspenders runner guard could also be added in
`run_benchmark.py:285-294` (`_resolve_answer`), which *does* hold the original `question`, but that is
eval-harness hardening, not an engine fix. The single guard at `query.py:208-217` covers every route.

---

## 5. Secondary, deeper defect — the narrowing itself drops the lumbar limb

**FACT:** SPINE-02 deliberately asks about **both** cervical **and** lumbar motion-preservation
("cervical **or** lumbar disc replacement, facet replacement, and tethering"). The disambiguation split
it into mutually exclusive `Cervical` / `Lumbar` variants and `choose_variant` (longest label) kept only
the **cervical** limb, silently discarding the lumbar half. Even with the empty-answer guard in place,
the *best case* is a complete answer to **half** the question — an **answer-completeness** defect.

**Root of the over-narrowing (FACT):** the compound, multi-region question was treated as a single-axis
*variant* ambiguity. There is no spine-motion axis in the taxonomy (`neuro_core/query_analyze.py:18-50`
`VARIANT_AXES`), so the trip came from the **LLM `analyze` pass** (`query_analyze.py:146-155`) under
`ANALYZE_SYSTEM_PROMPT` (`query_analyze.py:83-102`), which is written to pick "one named VARIANT of one
procedure." A question that names multiple **regions/procedures joined by "and/or"** is a
**multi-part** question for *decomposition*, not an either/or *disambiguation*.

**Fix location for the secondary defect (deeper, separate change — NOT part of the C5 reliability fix):**
either (a) tighten `ANALYZE_SYSTEM_PROMPT` / `_parse_analysis` (`query_analyze.py:83-143`) so a compound
"A and/or B" question returns `ambiguous=False` (decline to split across coordinated limbs), or (b) add a
guard in `Engine._plan_query` (`query.py:177-191`) that, on a compound multi-region question, answers the
**full** question rather than one limb. The runner's `choose_variant` longest-label heuristic
(`run_benchmark.py:88-98`) is a contributing factor ("longest label" ≠ "most clinically comprehensive")
but the primary lever is not splitting a coordinated question in the first place. This is a
**query_decomposition** defect and should be tracked separately from the C5 reliability guard.

---

## 6. Answers to the dispatch questions

- **(b) Exact C5 fix location + fallback:** `neuro_core/query.py::Engine._answer`, lines **208-217**
  (the `is_refusal` seam). On `not (syn.answer or "").strip()`: retry `synth_fn` once; if still empty,
  return `QueryResult(answer=REFUSAL, citations=[], figures=[])`. Guarantees no empty/`None` answer ever
  surfaces.
- **(c) Cause of the empty answer:** **neither** thin retrieval **nor** synthesis returning `None` —
  a **transient empty `resp.text` from Gemini** (`synth_clients.py:104`, `resp.text or ""`) that escaped
  because no empty-answer guard exists and `is_refusal("")` is `False`. The identical rewrite re-ran to a
  full 3868-char / 15-citation answer with healthy 12-passage retrieval.
- **Secondary defect:** yes — the narrowing drops the lumbar limb (answer-completeness /
  query_decomposition), a separate, deeper issue from the empty-answer reliability guard.
