# Ask Citation Faithfulness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Each Task below is ONE `- [ ]` checklist item = one implementation-sized, independently-testable, committable unit. The numbered TDD steps inside a Task are instructions for the implementing subagent (write the failing test first, run it red, implement minimally, run it green, commit) — they are NOT separate checklist items.

**Goal:** Wire the existing entailment verifier into the Ask answer path so every claim citing a textbook `[n]` or literature `[L#]` is checked, unsupported claims are flagged `needs-verification` as metadata, and a computed groundedness / unsupported-claim-rate metric is added to the evaluation harness.

**Architecture:** A new post-synthesis verification layer in `neuro_caseboard` (`answer_verify.py`) reuses `entailment.get_default_verifier()`. `neuro_core` stays citation-grounded-but-unverified; its only change is an *additive* optional `text` premise field on `Citation`. Verdicts attach as `QAResult.verification` **metadata** — the raw `answer` string is never mutated (the benchmark grader sees clean text); display annotation is render-only and flag-gated. The evaluation harness reads per-answer verification off run records to compute a groundedness aggregate and emit the dormant `unsupported_claim` / `citation_claim_mismatch` defect categories.

**Tech Stack:** Python 3, dataclasses, stdlib `re`; pytest. Reuses `neuro_caseboard/entailment.py` (`LexicalVerifier` default, offline/deterministic; `NLIVerifier` only if `CASEBOARD_NLI_MODEL` set).

## Global Constraints

- All work on `loop/ask-citation-faithfulness` in worktree `…/.project-loop/wt` (based on `origin/master` d1b6482).
- Additive + backward-compatible: the 266 scoped baseline tests stay green; new fields are optional with defaults.
- Reuse `entailment.should_cite(premise, hypothesis, verifier)` + `entailment.get_default_verifier()`. Do not build a new verifier.
- Non-destructive: verdicts only *label*; never remove a citation/claim.
- Dependency direction: `neuro_caseboard` imports `neuro_core`, never the reverse.
- Raw answer is sacrosanct: `QAResult.answer` / `WovenSynthesis.answer` is never edited; annotation is render-only behind `CASEBOARD_VERIFY_DISPLAY` (default on).
- Offline tests only; do NOT run the live 67-question benchmark in this loop.
- Each Task's final TDD step commits with the loop's `loop step <n>: <task>` prefix.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `neuro_core/synthesize.py` | textbook synthesis + `Citation` | Modify — add optional `text` to `Citation`; populate from `Hit.text` |
| `neuro_caseboard/woven_synth.py` | woven synthesis | Modify — populate `Citation.text` |
| `neuro_caseboard/answer_verify.py` | **NEW** — segmentation + verification + dataclasses | Create |
| `neuro_caseboard/qa.py` | Ask orchestration | Modify — `LiteratureCitation.abstract`; `QAResult.verification`; attach in both paths |
| `api/server.py` | HTTP surface | Modify — add `verification` to answer response |
| `neuro_caseboard/cli.py` | CLI Ask render | Modify — flag-gated `needs-verification` annotation (display only) |
| `evaluation/scripts/run_benchmark.py` | runner | Modify — record per-answer verification summary |
| `evaluation/scripts/summarize_grades.py` | metrics | Modify — groundedness/unsupported-rate aggregate |
| `evaluation/scripts/build_failure_ledger.py` | defects | Modify — emit `unsupported_claim`/`citation_claim_mismatch` |
| `evaluation/schemas/run-record.schema.json` | schema | Modify — declare `verification` |
| `tests/test_answer_verify.py` | A: seg+verify | Create (append to harness at Task A1) |
| `tests/test_qa.py`, `tests/test_woven_qa.py` | A: integration | Modify |
| `tests/evaluation/test_summarize_grades.py`, `tests/evaluation/test_failure_ledger.py` | B | Create |
| `tests/evaluation/test_runner.py` | B1 | Modify |

---

## Tasks

- [x] **Task A0 — Expose per-citation premise text on `Citation` (additive enabler).**

  **Files:** Modify `neuro_core/synthesize.py:35-40` (dataclass) + `:96-99` (construction); `neuro_caseboard/woven_synth.py:64-68` (construction). Test: `tests/neuro_core/test_synthesize.py`.
  **Produces:** `Citation(n:int, book:str, chapter:str, page:int, text:str = "")` — `text` is the cited chunk passage (empty for appended-figure citations whose `source_n > len(hits)`).
  **Why:** `should_cite(premise, hypothesis, verifier)` needs the source passage as `premise`. Today `Citation` has only n/book/chapter/page; the passage is on `Hit.text` (`neuro_core/index.py:9-19`).
  **TDD steps for the subagent:**
  1. Failing test in `tests/neuro_core/test_synthesize.py`:
     ```python
     def test_citation_carries_source_text():
         from neuro_core import synthesize as S
         from neuro_core.index import Hit
         hits = [Hit(id="a", book="Youmans", chapter="Ch1", page=42, text="The MCA supplies the lateral cortex.")]
         class _Synth:
             def generate(self, system, user, images): return "Answer [1]."
         out = S.synthesize("q", hits, [], [], _Synth())
         assert out.citations[0].n == 1
         assert out.citations[0].text == "The MCA supplies the lateral cortex."
     ```
  2. Run it red: `… pytest -q tests/neuro_core/test_synthesize.py::test_citation_carries_source_text`.
  3. Add `text: str = ""` to `Citation`; at the citation comprehension set `text=hits[i-1].text if i-1 < len(hits) else ""`; mirror in `woven_synth.py`.
  4. Run green; run `tests/neuro_core` + `tests/test_woven_synth.py` (no regression).
  5. Commit.

- [x] **Task A1 — Claim segmentation utility (`answer_verify.py`).**

  **Files:** Create `neuro_caseboard/answer_verify.py`; create `tests/test_answer_verify.py`. **After this lands, the operator appends `tests/test_answer_verify.py` to STATE.harness.**
  **Produces:**
  ```python
  @dataclass
  class ClaimSpan:
      text: str                       # sentence, markers preserved
      markers: list = field(default_factory=list)   # e.g. ["1", "L2"]
  def segment_claims(answer: str) -> list: ...
  ```
  Marker grammar: `[n]`→`"n"`, `[Ln]`→`"Ln"`; sentence split on `(?<=[.!?])\s+`; sentences with no marker still returned (empty `markers`).
  **TDD steps:**
  1. Failing tests in `tests/test_answer_verify.py`:
     ```python
     from neuro_caseboard.answer_verify import segment_claims
     def test_segment_associates_markers_per_sentence():
         ans = "The MCA supplies the lateral cortex [1]. Bridging therapy is debated [L2][3]. No citation here."
         spans = segment_claims(ans)
         assert [s.markers for s in spans] == [["1"], ["L2", "3"], []]
         assert spans[0].text.startswith("The MCA")
     def test_segment_handles_empty():
         assert segment_claims("") == []
     ```
  2. Run red.
  3. Implement:
     ```python
     import re
     from dataclasses import dataclass, field
     _MARKER = re.compile(r"\[(L?\d+)\]")
     _SENT = re.compile(r"(?<=[.!?])\s+")
     @dataclass
     class ClaimSpan:
         text: str
         markers: list = field(default_factory=list)
     def segment_claims(answer: str) -> list:
         answer = (answer or "").strip()
         if not answer:
             return []
         spans = []
         for sent in _SENT.split(answer):
             sent = sent.strip()
             if sent:
                 spans.append(ClaimSpan(text=sent, markers=_MARKER.findall(sent)))
         return spans
     ```
  4. Run green.
  5. Commit.

- [x] **Task A2 — Per-claim entailment verification (`answer_verify.py`).**

  **Files:** Modify `neuro_caseboard/answer_verify.py`; test `tests/test_answer_verify.py`.
  **Consumes:** `segment_claims`; `entailment.should_cite`, `entailment.get_default_verifier`.
  **Produces:**
  ```python
  @dataclass
  class ClaimVerdict:
      text: str; markers: list; supported: bool; premise_chars: int
  @dataclass
  class AnswerVerification:
      claims: list; n_cited_claims: int; n_unsupported: int
      def groundedness(self) -> float       # 1.0 if n_cited_claims==0 else 1 - n_unsupported/n_cited_claims
      def unsupported_markers(self) -> list
  def verify_answer(answer: str, premises: dict, *, verifier=None) -> AnswerVerification: ...
  ```
  `premises` maps marker→source text (`{"1": chunk_text, "L2": abstract}`), assembled by the caller (A3/A4) so this fn is pure. Hypothesis = sentence with markers stripped; premise = the markers' texts joined by `" "`.
  **TDD steps:**
  1. Failing tests:
     ```python
     from neuro_caseboard.answer_verify import verify_answer
     def test_supported_claim_passes():
         v = verify_answer("The middle cerebral artery supplies the lateral cerebral cortex [1].",
                           {"1": "The middle cerebral artery supplies the lateral cerebral cortex and insula."})
         assert v.n_cited_claims == 1 and v.n_unsupported == 0 and v.groundedness() == 1.0
     def test_unsupported_claim_flagged():
         v = verify_answer("Endovascular thrombectomy improves outcomes in distal occlusion [1].",
                           {"1": "The corpus callosum connects the two hemispheres."})
         assert v.n_unsupported == 1 and v.groundedness() == 0.0 and "1" in v.unsupported_markers()
     def test_uncited_excluded_from_denominator():
         v = verify_answer("Background prose. The MCA supplies lateral cortex [1].", {"1": "The MCA supplies the lateral cortex."})
         assert v.n_cited_claims == 1
     def test_missing_premise_is_non_destructive():
         v = verify_answer("A figure-only reference [3].", {})
         assert v.n_unsupported == 0   # should_cite abstains->keep on empty premise
     ```
  2. Run red.
  3. Implement (strip markers for hypothesis; assemble premise; `should_cite`; cited iff ≥1 marker; unsupported iff cited and not supported):
     ```python
     from neuro_caseboard.entailment import should_cite, get_default_verifier
     def _strip(text): return _MARKER.sub("", text).strip()
     def verify_answer(answer, premises, *, verifier=None):
         verifier = verifier or get_default_verifier()
         verdicts, n_cited, n_unsup = [], 0, 0
         for span in segment_claims(answer):
             if not span.markers:
                 verdicts.append(ClaimVerdict(span.text, span.markers, True, 0)); continue
             n_cited += 1
             premise = " ".join(p for m in span.markers for p in [premises.get(m)] if p)
             supported = should_cite(premise, _strip(span.text), verifier)
             if not supported: n_unsup += 1
             verdicts.append(ClaimVerdict(span.text, span.markers, supported, len(premise)))
         return AnswerVerification(verdicts, n_cited, n_unsup)
     ```
     (Implement `groundedness`/`unsupported_markers` per the interface.)
  4. Run green.
  5. Commit.

- [x] **Task A3 — Integrate into `qa.answer_question` (separate/default path) + literature premise.**

  **Files:** Modify `neuro_caseboard/qa.py` — add `abstract: str = ""` to `LiteratureCitation` (`:16-24`), populate in `build_literature_section` (`:105-108`) from records; add `verification` to `QAResult` (`:33-38`); attach it in `answer_question` (`:239-240`).
  **Consumes:** `verify_answer`; `Citation.text` (A0); `LiteratureRecord.abstract`. Premise map = `{str(c.n): getattr(c,"text","") for c in citations}` ∪ `{f"L{lc.n}": lc.abstract for lc in lit.citations}`.
  **TDD steps:**
  1. Failing test in `tests/test_qa.py` (mirror lane injection at `:11-14,45-68`):
     ```python
     def test_answer_question_attaches_verification():
         from types import SimpleNamespace
         from neuro_caseboard.qa import answer_question
         qr = SimpleNamespace(answer="The MCA supplies the lateral cortex [1].",
             citations=[SimpleNamespace(n=1, book="Youmans", chapter="", page=5,
                                        text="The MCA supplies the lateral cerebral cortex.")], figures=[])
         out = answer_question("q", lane_a=lambda: qr, lane_b=lambda: None)
         assert out.verification is not None
         assert out.verification.n_cited_claims == 1 and out.verification.n_unsupported == 0
     ```
  2. Run red.
  3. Implement: add fields; build premise map (guard `getattr`); `verify_answer`; set `QAResult(..., verification=v)`; populate `LiteratureCitation.abstract`.
  4. Run green; run `tests/test_qa.py` + `tests/test_literature_synth.py`.
  5. Commit.

- [x] **Task A4 — Integrate into the woven path (`_answer_question_woven`).**

  **Files:** Modify `neuro_caseboard/qa.py` `_answer_question_woven` (`:133-196`) — premise map from `plan.hits[i-1].text` (textbook) and `records[i-1].abstract` (literature); attach `verification` to the returned `QAResult` (`:195-196`).
  **TDD steps:**
  1. Failing test in `tests/test_woven_qa.py` (reuse `_bundle`/`_rec`/`_Synth`, `:11-46`):
     ```python
     def test_woven_attaches_verification():
         out = _answer_question_woven("q", lit_config=_cfg(),
             synth_client=_Synth("The MCA supplies lateral cortex [1]. EVT helps [L1]."),
             plan_a=lambda: _bundle(), retrieve_b=lambda: [_rec("111")])
         assert isinstance(out, QAResult) and out.verification is not None
         assert out.verification.n_cited_claims == 2
     ```
     (Tune `_bundle().hits[0].text` / `_rec().abstract` if asserting an unsupported count.)
  2. Run red.
  3. Implement the premise-map assembly + `verify_answer` + `verification=v`.
  4. Run green (`tests/test_woven_qa.py`).
  5. Commit.

- [x] **Task A5 — Surface verification in API + CLI (flag-gated display).**

  **Files:** Modify `api/server.py` — add `"verification": _verification_dict(getattr(result,"verification",None))` to the `kind="answer"` dict (`:362-368`); add `_verification_dict`. Modify `neuro_caseboard/cli.py` `_run_ask` — when `os.environ.get("CASEBOARD_VERIFY_DISPLAY","1") != "0"`, print a compact `⚠ needs verification: claims [markers]` notice AFTER the answer; never edits the answer string. Test: `tests/test_qa.py` (or `tests/test_cli_smoke.py`).
  **Produces (JSON):** `{"n_cited_claims":int,"n_unsupported":int,"groundedness":float,"unsupported_markers":[str]}` or `None`.
  **TDD steps:**
  1. Failing test:
     ```python
     def test_verification_dict_shape():
         import importlib; server = importlib.import_module("api.server")
         from neuro_caseboard.answer_verify import AnswerVerification, ClaimVerdict
         v = AnswerVerification([ClaimVerdict("x [1].", ["1"], False, 10)], 1, 1)
         d = server._verification_dict(v)
         assert d["n_cited_claims"]==1 and d["n_unsupported"]==1 and d["groundedness"]==0.0 and d["unsupported_markers"]==["1"]
         assert server._verification_dict(None) is None
     ```
  2. Run red.
  3. Implement `_verification_dict` + wire into response; CLI notice gated by the env flag.
  4. Run green; run `tests/test_qa.py` + server/cli tests.
  5. Commit.

- [x] **Task B1 — Benchmark runner records the per-answer verification summary.**

  **Files:** Modify `evaluation/scripts/run_benchmark.py` — add `serialize_verification(v)->dict|None` near `:120-134`; in the `status=="completed"` block (`:383-392`) set `record["verification"] = serialize_verification(getattr(result,"verification",None))`. Test: `tests/evaluation/test_runner.py`.
  **TDD steps:**
  1. Failing test (extend `make_qaresult` to accept `verification`):
     ```python
     def test_runner_records_verification():
         from neuro_caseboard.answer_verify import AnswerVerification, ClaimVerdict
         v = AnswerVerification([ClaimVerdict("x [1].", ["1"], False, 5)], 1, 1)
         rec = _run_one(_stub_returning(make_qaresult(answer="x [1].", verification=v)))
         assert rec["verification"]["n_cited_claims"] == 1 and rec["verification"]["n_unsupported"] == 1
     ```
  2. Run red.
  3. Implement `serialize_verification` (`{"n_cited_claims","n_unsupported","groundedness","unsupported_markers"}`) + the record line. Keep independent of `serialize_raw_response`.
  4. Run green (`tests/evaluation/test_runner.py`).
  5. Commit.

- [x] **Task B2 — Computed groundedness aggregate in `summarize_grades.py`.**

  **Files:** Modify `evaluation/scripts/summarize_grades.py` — add `groundedness_summary(run_rows)->dict` + a top-level `"groundedness"` key in `build_summary` (`:90-111`) and a `"groundedness"` entry per `by_domain`. Create `tests/evaluation/test_summarize_grades.py` (NET-NEW; load script via `importlib.util.spec_from_file_location` like `test_results_summary.py:1-13`).
  **Produces:** `{"answers_scored","answers_with_unsupported","fraction_with_unsupported","total_cited_claims","total_unsupported","mean_unsupported_rate","mean_groundedness"}` from `run_rows[*]["verification"]` (skip rows lacking it).
  **TDD steps:**
  1. Failing test:
     ```python
     def test_groundedness_summary_counts(summarize_module):
         rows = [{"verification": {"n_cited_claims": 4, "n_unsupported": 1}},
                 {"verification": {"n_cited_claims": 2, "n_unsupported": 0}},
                 {}]  # skipped
         g = summarize_module.groundedness_summary(rows)
         assert g["answers_scored"]==2 and g["answers_with_unsupported"]==1
         assert g["total_cited_claims"]==6 and g["total_unsupported"]==1
         assert round(g["mean_groundedness"],4) == round(((3/4)+(2/2))/2,4)
     ```
  2. Run red.
  3. Implement (`per-answer rate = n_unsupported/n_cited_claims` when cited>0; `mean_groundedness` = mean of `1-rate`); add to `build_summary` + per-domain.
  4. Run green; run `tests/evaluation`.
  5. Commit.

- [x] **Task B3 — Emit `unsupported_claim` / `citation_claim_mismatch` defects.**

  **Files:** Modify `evaluation/scripts/build_failure_ledger.py` — add a `--run <run.jsonl>` input; add `defects_for_run_row(row)->list[dict]` reusing the `add()` record shape (`:61-75`); for each `verification` with `n_unsupported>0` emit `category="unsupported_claim"`; extend `LAYER` with `unsupported_claim`→`("model_synthesis",["neuro_caseboard/answer_verify.py","neuro_core/synthesize.py"])` and `citation_claim_mismatch`→`("citation_rendering",["neuro_caseboard/qa.py"])`; wire `--run` into `main()`. Create `tests/evaluation/test_failure_ledger.py`.
  **TDD steps:**
  1. Failing test:
     ```python
     def test_unsupported_claim_defect_emitted(ledger_module):
         row = {"question_id":"Q1","answer":"Claim one [1]. Claim two [L2].",
                "verification":{"n_cited_claims":3,"n_unsupported":2,"unsupported_markers":["1","L2"]}}
         defects = ledger_module.defects_for_run_row(row)
         assert "unsupported_claim" in {d["category"] for d in defects}
         assert defects[0]["question_id"]=="Q1"
         assert defects[0]["probable_layer"] in ("model_synthesis","citation_rendering")
     ```
  2. Run red.
  3. Implement `defects_for_run_row` + `LAYER` entries + `--run` wiring.
  4. Run green; run `tests/evaluation`.
  5. Commit.

- [x] **Task B4 — Schema + docs.**

  **Files:** Modify `evaluation/schemas/run-record.schema.json` — declare a `verification` object property (`n_cited_claims`,`n_unsupported`,`groundedness`,`unsupported_markers`); schema is `additionalProperties:true` so this documents it. Modify `evaluation/README.md` — one paragraph on the computed groundedness metric and the `CASEBOARD_VERIFY_DISPLAY` flag. Add a small schema-validation test (or extend `tests/evaluation/test_manifest.py` style); skip gracefully if no validator is importable.
  **TDD steps:**
  1. Failing test: validate a sample record carrying `verification` against `run-record.schema.json`.
  2. Run red.
  3. Implement schema property + docs paragraph.
  4. Run green; run `tests/evaluation`.
  5. Commit.

---

## Notes

- **Type consistency:** `AnswerVerification`/`ClaimVerdict`/`ClaimSpan` and the `premises` marker keys (`"1"`, `"L2"`) are used identically across A2/A3/A4/B1.
- **Harness:** Task A1 adds `tests/test_answer_verify.py` → operator appends it to STATE.harness before the A1 VERIFY; `tests/evaluation/` is already in the harness.
- **Follow-on (note in PR, out of scope):** true `citation_claim_mismatch` (contradiction vs. mere non-entailment) needs the `NLIVerifier` contradiction signal; this PR emits `unsupported_claim` and wires the `citation_claim_mismatch` category/LAYER, but full contradiction detection is a follow-up (the default `LexicalVerifier` only distinguishes support / non-support).
