# Design — WS-2: Expanded section taxonomy (the 8 case surfaces)

- **Date:** 2026-06-16
- **Status:** Approved (locked by LOOP_PROMPT §4 WS-2); implementation in progress
- **Branch:** `worktree-streamlit-executive-navy-loop`
- **Loop:** Case Dossier engine (`caseboard case`), Pass 2 of 5
- **Builds on:** WS-1 `CaseContext`/`intake` (`docs/.../2026-06-16-ws1-case-context-intake-design.md`)

## 1. Context & problem
WS-1 turns a dictation into a `CaseContext`. The `build` engine today emits a **3-section**
dossier (Anatomy at Risk / Operative Plan / Risk & Rescue) from a bare topic. The case dossier
must carry the **eight surfaces** of LOOP_PROMPT §0: Clinical Summary, Clinical Reasoning,
Operative Plan, Alternatives, Risks, Pre-op Optimization, Surgical Technique, and Case-specific
Figures. WS-2 adds that taxonomy and a case-section **author**, driven entirely by card metadata
+ text structure — never hardcoded clinical phrases — on the single evidence axis.

**De-risked (probe, 2026-06-16):** caseprep `enrich_manifest` + `audit_manifest` accept cards
with *arbitrary* `target_file`/`section_key` and assign `audit_status` (a new-file card with no
corpus match → `no_evidence` → a surgeon-facing "verify" claim). So new sections need only (a) an
author that emits cards targeting them and (b) compile headings/order — no change to the audit
engine, and **no regression** to `build`/`ask`.

## 2. Decisions
- **Additive, not a fork.** The existing `compile_dossier` (3-section build) and the `build`/`ask`
  CLIs are untouched. WS-2 adds a parallel **case** path: `build_case_manifest(case) → enrich →
  audit → compile_case_dossier`. `build`'s output is byte-for-byte unchanged.
- **Taxonomy lives in one place:** `neuro_caseboard/case_sections.py` — the ordered list of the 8
  surfaces with their `target_file`, heading, intro, and a generalizable **slot vocabulary**
  (concept labels like Operative Plan's existing slots — the documented `ontology.py` carve-out,
  NOT clinical answers). Reuses `04-operative-plan.md` and `05-risk-and-rescue.md` verbatim;
  adds `01-clinical-summary.md`, `02-clinical-reasoning.md`, `06-alternatives.md`,
  `07-preop-optimization.md`, `08-surgical-technique.md`, and a `09-case-figures.md` placeholder
  band (populated in WS-4).
- **Author is LLM-first with a grounded deterministic fallback** (same contract as WS-1/Explorer:
  injected `complete_fn`, graceful degrade). Offline (no provider) it still emits the full 8-section
  scaffold so the dossier always renders — every offline card is a clinician-**verify** prompt,
  exactly as the offline `build` path already behaves.
- **Topic-agnostic, single evidence axis.** Deterministic cards are composed from the case's own
  fields (the patient's data echoed back) + `ontology.required_dimensions(case.to_topic())` (the
  existing generalizable scaffold). No confidence axis is reintroduced; `EvidenceSummary` stays
  `supported/to_verify/quarantined`.

## 3. Detailed design (exact files / functions)

### 3.1 `neuro_caseboard/case_sections.py` (new)
```python
@dataclass(frozen=True)
class CaseSection:
    target_file: str
    heading: str
    intro: str
    slots: tuple[str, ...]          # generalizable concept labels (compiler_slot source)

CASE_SECTIONS: list[CaseSection] = [ ...the 8, in §0 order... ]
CASE_ORDER   = [s.target_file for s in CASE_SECTIONS]
CASE_HEADINGS = {s.target_file: s.heading for s in CASE_SECTIONS}
CASE_INTROS   = {s.target_file: s.intro for s in CASE_SECTIONS}
SLOT_LABEL = {section_key -> Title Case}   # for compiler_slot derivation
```
Sections & slot vocab (concept labels only):
- `01-clinical-summary.md` → "Clinical Summary": `presentation, key_findings, working_diagnosis, functional_baseline`
- `02-clinical-reasoning.md` → "Clinical Reasoning": `indication, timing, evidence_basis, natural_history`
- `04-operative-plan.md` → "Operative Plan": (reuse caseprep operative slots)
- `06-alternatives.md` → "Alternatives": `nonoperative_option, alternative_approach, tradeoff`
- `05-risk-and-rescue.md` → "Risks": (reuse caseprep risk slots)
- `07-preop-optimization.md` → "Pre-op Optimization": `medical_optimization, imaging_and_planning, consent_counseling, team_readiness`
- `08-surgical-technique.md` → "Surgical Technique": `approach_corridor, key_steps, named_adjuncts, rescue_sequence`
- `09-case-figures.md` → "Case Figures": `schematic` (WS-4; empty band in WS-2)

### 3.2 `neuro_caseboard/case_author.py` (new)
```python
CASE_SYSTEM = "...attending authoring an 8-section case dossier from a CaseContext, JSON cards..."

def build_case_manifest(case: CaseContext, *, complete_fn=None) -> QuestionManifest:
    """LLM-first (injected complete_fn) author over the 8 case sections; on no-provider / any
    failure, the deterministic scaffold. Always returns a non-empty manifest."""

def deterministic_case_manifest(case: CaseContext) -> QuestionManifest:
    """Grounded scaffold: Clinical Summary echoes the case's own presentation/imaging/diagnosis;
    Reasoning/Alternatives/Pre-op/Technique seed from generalizable slot labels +
    ontology.required_dimensions(case.to_topic()); Operative Plan/Risks reuse the caseprep
    deterministic manifest cards. Every card is a verify prompt. No hardcoded clinical content."""

def _coerce_case_cards(raw: dict) -> list[QuestionCard]:   # validate target_file/section_key vs CASE taxonomy
```
- LLM cards validated against the CASE taxonomy (target_file ∈ CASE_ORDER, section_key ∈ that
  section's slots), `compiler_slot` derived from `SLOT_LABEL`, mirroring `explore_llm._coerce_cards`.
- Deterministic Operative Plan / Risks cards are pulled from the existing
  `pipeline._deterministic_manifest(case.to_topic(), profile)` (reuse — those already cover 04/05),
  filtered to those two files; the 5 new sections get scaffold cards composed from `case` + ontology.

### 3.3 `neuro_caseboard/compile.py` (extend, non-breaking)
- Refactor the file-grouping core of `compile_dossier` into a private `_compile(audited, *, topic,
  evidence, card_evidence, page_texts, headings, order, intros, title)` that takes the
  headings/order/intros maps. `compile_dossier` calls it with the **existing** `_HEADINGS/_ORDER/
  _INTRO` (behavior-preserving — guarded by `test_compile.py`).
- Add `compile_case_dossier(audited, *, case, evidence=None, card_evidence=None, page_texts=None)`
  calling `_compile` with `CASE_HEADINGS/CASE_ORDER/CASE_INTROS` and `title=f"Case Dossier — {case.to_topic()}"`.
  Evidence axis/markers/appendix/dedup all reused unchanged.

### 3.4 `neuro_caseboard/pipeline.py` (extend)
```python
def build_case_dossier(case: CaseContext, *, enrich=True, use_llm=None) -> Dossier:
    """Case path: build_case_manifest(case) -> prune_offtarget -> enrich -> audit ->
    compile_case_dossier. Mirrors build_dossier; reuses the same retriever/guard/enrich/audit."""
```
The anti-bleed `guard.prune_offtarget(manifest, case.to_topic())` stays in the path (LOOP_PROMPT §6).
No CLI/Streamlit wiring yet (WS-5); `build_case_dossier` is the seam, exercised by tests + a new eval.

## 4. Acceptance criteria (LOOP_PROMPT §5 WS-2)
- All **eight** sections render for ≥1 case from each of **cranial / spine / endovascular** (the
  offline deterministic path is sufficient for "render"; LLM enriches content).
- **Zero hardcoded clinical strings** introduced (grep the diff for named vessels/diseases/drugs;
  only generalizable concept/process labels — the ontology carve-out — are allowed).
- Existing `build`/`ask` output **unchanged** where untouched (`compile_dossier` byte-identical).
- Single evidence axis preserved (no confidence axis).
- Blind text-judge ≥ current `build` baseline on must_cover, new sections ≥ "useful, attending-level"
  — **deferred to a keyed run** (recorded), as in WS-1.

## 5. Testing strategy (offline, deterministic — required CI)
`tests/test_case_sections.py`: the 8 sections present & ordered; reused files match the build files;
slot labels Title-Cased.
`tests/test_case_author.py` (mirrors `test_explore_llm.py`): injected fake → cards across all 8
files, invalid file/slot dropped; deterministic fallback yields ≥1 card in **every** section for a
spine/cranial/vascular `CaseContext`; topic-agnostic guard (no named vessel/disease/drug literal in
the deterministic output for a given case — only the case's own echoed terms).
`tests/test_compile.py` (extend): `compile_case_dossier` renders all 8 headings in order on a fake
audited case manifest; `compile_dossier` regression unchanged.
`tests/test_pipeline.py` (extend): `build_case_dossier` with `enrich=False`, injected author fake →
Dossier with 8 sections; `build_dossier` regression unchanged.

## 6. EVAL (reproducible; live portion deferred)
New `eval/case_eval.py`: run `build_case_dossier(parse_dictation(d), enrich=False)` over
`eval/case_dictations.json`, assert all 8 sections render per case across the three subspecialties,
write `eval/CASE_DOSSIER_REPORT_<date>.md` (section coverage table). Live blind text-judge against
`cases.json` must_cover deferred to a keyed run.

## 7. Risks
- **`compile_dossier` refactor regressing build** → mitigated by extracting a pure `_compile` and
  keeping `compile_dossier`'s call args identical; guarded by `test_compile.py` + full suite.
- **Topic-agnostic violation in the deterministic author** → explicit no-clinical-literal test; all
  specifics come from `case` fields or ontology dimension labels.
- **Section bloat / empty sections** → a section with no cards is omitted (existing compile behavior);
  the deterministic scaffold guarantees ≥1 card per text section so all 8 appear offline.

## 8. Out of scope (this pass)
PubMed `[L#]` in the case build (WS-3), generated schematics (WS-4), CLI `caseboard case` + the PDF
surface + Streamlit lane (WS-5). No new runtime dependency.
