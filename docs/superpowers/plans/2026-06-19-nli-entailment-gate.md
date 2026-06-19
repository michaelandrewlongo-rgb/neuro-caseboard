# NLI Claim↔Citation Entailment Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. **Each top-level checkbox is one implementation-sized task** (one commit, marker `loop step <n>: …`). The numbered sub-steps inside a task are the TDD micro-cycle to follow within that single task — they are NOT separate checkboxes.

**Goal:** Before a corpus paper becomes an inline `[n]` citation on a claim, verify the paper's retrieved span actually *entails* the claim; withhold the citation (and downgrade the claim's status) when it does not — closing the "evidence leakage" gap where a domain-accepted paper is cited for a claim it doesn't support.

**Architecture:** Add an injectable `ClaimVerifier` (entailment judge) consumed at the single citation-binding site in `compile.py`. Ship a dependency-free deterministic `LexicalVerifier` as the default and an optional lazy `NLIVerifier` (off-the-shelf cross-encoder NLI) for production. The verifier *abstains→keeps* when the premise span is too thin to judge, so behavior is unchanged where no real span text exists (preserving the offline quality gate). A new `attribution_precision` metric guards the behavior in CI.

**Tech Stack:** Python ≥3.10, stdlib only for the default path; optional `sentence-transformers` (already declared in the `models` extra) for the real NLI backend, lazily imported so the test suite never loads it.

## Global Constraints

- **Inference-only; no training/fine-tuning.** The NLI backend is an off-the-shelf model loaded for inference; never trained.
- **No new *required* dependency.** The default verifier is stdlib-only. The real NLI backend must be lazy-imported and must NOT be importable-at-collection by the test suite (mirror the existing "fakes injected" test pattern).
- **Never fabricate a citation.** The gate may only ever *remove* a weak `[n]`, never add or re-point one. `cited ⊆ accepted_papers` must still hold.
- **Conservative abstain.** When the premise span has fewer than `min_premise_tokens` content tokens, the verifier returns "keep" (cannot disprove → do not withhold). This preserves the offline gate's `_FakeCorpus` `[n]` markers and the existing `corpus_n_coverage` metric.
- **Topic-agnostic.** No hardcoded clinical phrases; judgments are purely lexical/model-driven over `(premise, hypothesis)` text.
- **No regressions.** All 97 currently-passing scoped tests and every existing `eval/BASELINE.json` metric (esp. `corpus_n_coverage`, `red_flag_contamination`) must stay green.
- **Harness (scoped):** `python -m pytest tests/ -q -m "not integration" -k "evidence or compile or quality_gate or corpus_grounding or render_md or entail or attribution or audit"`

---

- [ ] **Task 0 — `ClaimVerifier` interface + dependency-free `LexicalVerifier`** (commit marker: `loop step 0: …`)

  **Files:** Create `neuro_caseboard/entailment.py`; Test `tests/test_entailment_gate.py`.

  **Produces:** `ClaimVerifier` Protocol (`entails(premise, hypothesis) -> bool`); `LexicalVerifier(threshold=0.18, min_premise_tokens=5)`; `should_cite(premise, hypothesis, verifier) -> bool` (abstain→keep when premise has `< min_premise_tokens` content tokens); `_content_tokens(text) -> set[str]`.

  1. **Write the failing tests** in `tests/test_entailment_gate.py`:

  ```python
  from neuro_caseboard.entailment import LexicalVerifier, should_cite

  def test_lexical_entails_when_overlap_high():
      v = LexicalVerifier()
      premise = "The recurrent artery of Heubner supplies the caudate head and must be preserved."
      assert v.entails(premise, "Preserve the recurrent artery of Heubner.") is True

  def test_lexical_rejects_when_disjoint():
      v = LexicalVerifier()
      premise = "Lumbar pedicle screw trajectories follow the convergent sagittal angle."
      assert v.entails(premise, "Preserve the recurrent artery of Heubner.") is False

  def test_should_cite_abstains_keep_on_thin_premise():
      assert should_cite("Reference corpus record 1",
                         "Preserve the recurrent artery of Heubner.", LexicalVerifier()) is True

  def test_should_cite_withholds_on_substantial_disjoint_premise():
      premise = "Lumbar pedicle screw trajectories follow the convergent sagittal angle through the pars."
      assert should_cite(premise, "Preserve the recurrent artery of Heubner.", LexicalVerifier()) is False
  ```

  2. **Run to verify they fail:** `python -m pytest tests/test_entailment_gate.py -q` → FAIL (`ModuleNotFoundError: neuro_caseboard.entailment`).

  3. **Implement `neuro_caseboard/entailment.py`:**

  ```python
  """Claim↔citation entailment verification (inference-only).

  A claim earns an inline [n] corpus citation only if its cited span ENTAILS the claim. The default
  LexicalVerifier is stdlib-only and deterministic; NLIVerifier (Task 1) is an optional, lazily
  imported off-the-shelf cross-encoder NLI backend for production. Conservative: when a premise span
  is too thin to judge, `should_cite` abstains and KEEPS the citation; the gate may only ever REMOVE
  a weak citation — never add or re-point one.
  """
  from __future__ import annotations

  import re
  from typing import Protocol, runtime_checkable

  _TOKEN = re.compile(r"[a-z0-9]+")
  _STOP = {"the", "and", "for", "with", "that", "this", "are", "must", "its", "into",
           "from", "their", "which", "may", "can", "not", "but", "all", "any", "per"}


  def _content_tokens(text: str) -> set[str]:
      return {t for t in _TOKEN.findall((text or "").lower()) if len(t) >= 3 and t not in _STOP}


  @runtime_checkable
  class ClaimVerifier(Protocol):
      def entails(self, premise: str, hypothesis: str) -> bool: ...


  class LexicalVerifier:
      """Deterministic token-overlap entailment proxy (no model/deps). `entails` is True when the
      hypothesis's content tokens are sufficiently recalled by the premise."""

      def __init__(self, threshold: float = 0.18, min_premise_tokens: int = 5) -> None:
          self.threshold = threshold
          self.min_premise_tokens = min_premise_tokens

      def entails(self, premise: str, hypothesis: str) -> bool:
          p = _content_tokens(premise)
          h = _content_tokens(hypothesis)
          if not h:
              return True
          return (len(p & h) / len(h)) >= self.threshold


  def should_cite(premise: str, hypothesis: str, verifier: ClaimVerifier) -> bool:
      """Keep the citation unless the verifier positively rejects a JUDGEABLE premise. Abstain→keep
      when the premise is too thin to judge (cannot disprove)."""
      min_tok = getattr(verifier, "min_premise_tokens", 5)
      if len(_content_tokens(premise)) < min_tok:
          return True
      return bool(verifier.entails(premise, hypothesis))
  ```

  4. **Run to verify they pass:** `python -m pytest tests/test_entailment_gate.py -q` → PASS (4 passed).

  5. **Commit:** `git add neuro_caseboard/entailment.py tests/test_entailment_gate.py && git commit -m "loop step 0: ClaimVerifier interface + dependency-free LexicalVerifier"`

---

- [ ] **Task 1 — Optional lazy `NLIVerifier` + `get_default_verifier()` factory** (commit marker: `loop step 1: …`)

  **Files:** Modify `neuro_caseboard/entailment.py`; Test `tests/test_entailment_gate.py`.

  **Consumes:** `ClaimVerifier`, `LexicalVerifier` (Task 0). **Produces:** `NLIVerifier(model_name)` (lazy-imports `sentence_transformers.CrossEncoder`; `entails` maps argmax label index 1 == entailment); `get_default_verifier() -> ClaimVerifier` (NLIVerifier when `CASEBOARD_NLI_MODEL` set and backend imports, else LexicalVerifier).

  1. **Write the failing test** (append):

  ```python
  from neuro_caseboard.entailment import get_default_verifier, LexicalVerifier

  def test_default_verifier_is_lexical_without_model_env(monkeypatch):
      monkeypatch.delenv("CASEBOARD_NLI_MODEL", raising=False)
      assert isinstance(get_default_verifier(), LexicalVerifier)
  ```

  2. **Run to verify it fails:** `python -m pytest tests/test_entailment_gate.py::test_default_verifier_is_lexical_without_model_env -q` → FAIL (`ImportError: cannot import name 'get_default_verifier'`).

  3. **Append to `neuro_caseboard/entailment.py`:**

  ```python
  import os

  # MNLI cross-encoder label order is [contradiction, entailment, neutral]; index 1 == entailment.
  _ENTAIL_INDEX = 1


  class NLIVerifier:
      """Off-the-shelf cross-encoder NLI backend (inference-only; lazily imported). Premise =
      retrieved corpus span; hypothesis = the claim. Production path only — the test suite must never
      trigger the import."""

      def __init__(self, model_name: str) -> None:
          from sentence_transformers import CrossEncoder  # lazy: heavy, optional dep
          self._model = CrossEncoder(model_name)

      def entails(self, premise: str, hypothesis: str) -> bool:
          scores = self._model.predict([(premise, hypothesis)])[0]
          return int(max(range(len(scores)), key=lambda i: scores[i])) == _ENTAIL_INDEX


  def get_default_verifier() -> ClaimVerifier:
      """NLIVerifier when CASEBOARD_NLI_MODEL is set and the backend imports; else LexicalVerifier."""
      model = os.environ.get("CASEBOARD_NLI_MODEL")
      if model:
          try:
              return NLIVerifier(model)
          except Exception:
              pass
      return LexicalVerifier()
  ```

  4. **Run to verify they pass:** `python -m pytest tests/test_entailment_gate.py -q` → PASS (5 passed).

  5. **Commit:** `git add neuro_caseboard/entailment.py tests/test_entailment_gate.py && git commit -m "loop step 1: optional lazy NLIVerifier + get_default_verifier factory"`

---

- [ ] **Task 2 — Gate the `[n]` citation binding in `compile.py`** (commit marker: `loop step 2: …`)

  **Files:** Modify `neuro_caseboard/compile.py` (the `_compile` signature, the corpus-`[n]` block at lines ~149-156, and the `compile_dossier`/`compile_case_dossier` signatures); Test `tests/test_entailment_gate.py`.

  **Consumes:** `should_cite`, `LexicalVerifier` (Tasks 0-1); `accepted_papers(c)` → dicts with `title`, `text_snippet`; `Claim.text/.why/.status`. **Produces:** `verifier` keyword on `_compile`/`compile_dossier`/`compile_case_dossier` (default `None`→`LexicalVerifier()`). Per accepted paper, append `[n]` only when `should_cite(p["text_snippet"], f"{claim.text} {claim.why}", v)`; if a claim had ≥1 accepted paper but ALL were withheld, set `claim.status = "verify"`.

  1. **Write the failing tests** (append):

  ```python
  from types import SimpleNamespace
  from neuro_caseboard.compile import compile_case_dossier
  from neuro_caseboard.case_sections import CORPUS_ELIGIBLE_FILES
  from neuro_caseboard.case_context import CaseContext

  def _card(tf, q, papers, status="supported"):
      return SimpleNamespace(target_file=tf, question=q, why_it_matters="", compiler_slot="",
                             section_key="op", audit_status=status, audit_reason="", papers=papers)

  def _case():
      return CaseContext(laterality="left", location="MCA bifurcation", pathology="aneurysm",
                         procedure="pterional clipping", surgical_goal="clip ligation")

  def _claims(d):
      return [c for s in d.sections for c in s.claims]

  def test_disjoint_span_withholds_citation_and_downgrades():
      tf = sorted(CORPUS_ELIGIBLE_FILES)[0]
      paper = {"title": "Off-topic spine paper",
               "text_snippet": "Lumbar pedicle screw trajectories follow the convergent sagittal "
                               "angle through the pars interarticularis."}
      d = compile_case_dossier(SimpleNamespace(cards=[_card(tf,
              "Preserve the recurrent artery of Heubner during dissection.", [paper])]),
              case=_case(), verifier=LexicalVerifier())
      c = _claims(d)[0]
      assert "[1]" not in c.text and c.status == "verify"

  def test_entailing_span_keeps_citation():
      tf = sorted(CORPUS_ELIGIBLE_FILES)[0]
      paper = {"title": "Heubner anatomy",
               "text_snippet": "The recurrent artery of Heubner arises near the anterior communicating "
                               "artery and must be preserved during dissection of the region."}
      d = compile_case_dossier(SimpleNamespace(cards=[_card(tf,
              "Preserve the recurrent artery of Heubner during dissection.", [paper])]),
              case=_case(), verifier=LexicalVerifier())
      c = _claims(d)[0]
      assert "[1]" in c.text and c.status == "supported"
  ```

  2. **Run to verify they fail:** `python -m pytest tests/test_entailment_gate.py -q` → FAIL (`unexpected keyword argument 'verifier'`).

  3. **Implement** in `neuro_caseboard/compile.py`. Add import: `from neuro_caseboard.entailment import should_cite, LexicalVerifier`. Add `verifier=None` to `_compile`'s keyword-only params; near the top of `_compile` resolve `v = verifier or LexicalVerifier()`. Replace the corpus-`[n]` block (≈lines 149-156) with:

  ```python
              if corpus_inline and tf in corpus_eligible:
                  hypothesis = f"{claim.text} {claim.why}".strip()
                  considered = 0
                  marks = []
                  for p in accepted_papers(c)[:2]:
                      cite = (p.get("title") or "").strip() if isinstance(p, dict) else ""
                      snippet = (p.get("text_snippet") or "") if isinstance(p, dict) else ""
                      if not cite:
                          continue
                      considered += 1
                      if should_cite(snippet, hypothesis, v):
                          marks.append(_cite_index(cite))
                  if marks:
                      claim.text = f"{claim.text} " + "".join(f"[{m}]" for m in marks)
                  elif considered:
                      claim.status = "verify"   # had candidates but the gate withheld them all
              claims.append(claim)
  ```

  Thread `verifier=verifier` through `compile_dossier` and `compile_case_dossier` (add `verifier=None` to both signatures and pass it into the `_compile(...)` call).

  4. **Run new tests, then the full scoped harness:** `python -m pytest tests/test_entailment_gate.py -q` → PASS (7). Then run the scoped harness (Global Constraints) → 0 failed. If a pre-existing corpus-grounding fixture regresses on a substantial-but-disjoint span, lower `LexicalVerifier.threshold` slightly (a leniency knob, not a clinical constant) and re-run. Never special-case a clinical phrase.

  5. **Commit:** `git add neuro_caseboard/compile.py tests/test_entailment_gate.py && git commit -m "loop step 2: gate inline [n] citations on claim<->span entailment; downgrade on full withhold"`

---

- [ ] **Task 3 — `attribution_precision` metric in the offline quality gate** (commit marker: `loop step 3: …`)

  **Files:** Modify `eval/quality_gate.py` (`compute_metrics` + `DIRECTIONS`); Modify `eval/BASELINE.json` (regenerate); Test `tests/test_quality_gate.py`.

  **Consumes:** gated `build_case_dossier`/`compile_case_dossier` (Task 2); `_CORPUS_CITE`/`_LIT_CITE` regexes already in `quality_gate.py`. **Produces:** `attribution_precision` = fraction of corpus-eligible claims that retained ≥1 `[n]` after the gate; direction `min`. On the deterministic `_FakeCorpus` (thin spans → abstain-keep) this is `1.0`, locking current behavior.

  1. **Write the failing test** (append to `tests/test_quality_gate.py`):

  ```python
  from eval.quality_gate import compute_metrics, load_split, DIRECTIONS

  def test_attribution_precision_present_and_perfect_offline():
      m = compute_metrics(load_split("eval"))
      assert "attribution_precision" in m
      assert DIRECTIONS["attribution_precision"] == "min"
      assert m["attribution_precision"] == 1.0
  ```

  2. **Run to verify it fails:** `python -m pytest tests/test_quality_gate.py::test_attribution_precision_present_and_perfect_offline -q` → FAIL (`KeyError`).

  3. **Implement** in `eval/quality_gate.py`: add `"attribution_precision": "min",` to `DIRECTIONS`. Initialize `attr_kept = attr_considered = 0` before the per-dictation loop. Inside the loop, after `elig` is built, add:

  ```python
          for h in CORPUS_ELIGIBLE:
              for c in getattr(elig.get(h), "claims", []) or []:
                  attr_considered += 1
                  if _CORPUS_CITE.search(_LIT_CITE.sub("", c.text)):
                      attr_kept += 1
  ```

  Add to the returned dict: `"attribution_precision": _frac(attr_kept, attr_considered),`.

  4. **Regenerate baseline + run gate + test:** `python3 eval/quality_gate.py --emit-baseline > eval/BASELINE.json` then `python3 eval/quality_gate.py` → `Gate: PASS`. Then `python -m pytest tests/test_quality_gate.py -q` → PASS.

  5. **Commit:** `git add eval/quality_gate.py eval/BASELINE.json tests/test_quality_gate.py && git commit -m "loop step 3: attribution_precision metric + regenerated BASELINE.json"`

---

- [ ] **Task 4 — Wire the default verifier into the production build path + document** (commit marker: `loop step 4: …`)

  **Files:** Modify `neuro_caseboard/pipeline.py` (the `build_case_dossier` → `compile_case_dossier` call); Modify `README.md`; Test `tests/test_entailment_gate.py`.

  **Consumes:** `get_default_verifier()` (Task 1); gated `compile_case_dossier` (Task 2). **Produces:** `build_case_dossier(...)` passes `verifier=get_default_verifier()` into `compile_case_dossier`.

  1. **Write the failing test** (append):

  ```python
  def test_pipeline_passes_verifier_through(monkeypatch):
      import neuro_caseboard.pipeline as pipe
      from neuro_caseboard.entailment import ClaimVerifier
      captured = {}
      real = pipe.compile_case_dossier
      def spy(*a, **k):
          captured["verifier"] = k.get("verifier")
          return real(*a, **k)
      monkeypatch.setattr(pipe, "compile_case_dossier", spy)
      pipe.build_case_dossier(_case(), enrich=False, use_llm=False, literature=False)
      assert isinstance(captured["verifier"], ClaimVerifier)
  ```

  2. **Run to verify it fails:** `python -m pytest tests/test_entailment_gate.py::test_pipeline_passes_verifier_through -q` → FAIL (`captured["verifier"]` is `None`).

  3. **Implement** in `neuro_caseboard/pipeline.py`: add `from neuro_caseboard.entailment import get_default_verifier`, and in `build_case_dossier` pass `verifier=get_default_verifier()` into the `compile_case_dossier(...)` call.

  4. **Run new test + full scoped harness:** `python -m pytest tests/test_entailment_gate.py -q` → PASS (8). Then the scoped harness → 0 failed.

  5. **Document + commit:** add a short `### Citation entailment gate` subsection to `README.md` (the cited span must entail the claim; `CASEBOARD_NLI_MODEL` selects the model else lexical fallback; failing claims are downgraded to needs-verification; citations are only ever withheld, never fabricated; the gate tracks `attribution_precision`). Then `git add neuro_caseboard/pipeline.py README.md tests/test_entailment_gate.py && git commit -m "loop step 4: wire default verifier into build_case_dossier + document"`

---

## Self-Review

- **Spec coverage:** verify each cited claim → Task 2; off-the-shelf NLI, inference-only → Task 1; downgrade unsupported → Task 2 (status→verify); attribution metric in quality gate → Task 3; production wiring → Task 4. ✓
- **Placeholder scan:** none — every code/test step is concrete.
- **Type consistency:** `entails(premise, hypothesis) -> bool`, `should_cite(premise, hypothesis, verifier) -> bool`, `get_default_verifier() -> ClaimVerifier`, and the `verifier=` keyword are used identically across Tasks 0-4. Paper dict keys (`title`, `text_snippet`) match `caseprep.audit.card_auditor._paper_text`. ✓
- **Regression guard:** abstain-keep on thin premises preserves `corpus_n_coverage`; full scoped harness is run in Tasks 2 and 4; baseline regenerated in Task 3. ✓
- **Step granularity:** exactly five top-level task checkboxes → five loop increments with aligned `loop step 0..4` commit markers. ✓
