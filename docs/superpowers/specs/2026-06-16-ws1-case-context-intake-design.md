# Design — WS-1: `CaseContext` + dictation intake

- **Date:** 2026-06-16
- **Status:** Approved (locked by LOOP_PROMPT §4 WS-1); implementation in progress
- **Branch:** `worktree-streamlit-executive-navy-loop`
- **Loop:** Case Dossier engine (`caseboard case`), Pass 1 of 5

## 1. Context & problem

`neuro-caseboard` today turns a **bare topic string** ("C5-6 corpectomy") into a 3-section
pre-op dossier (`pipeline.build_dossier` → `compile_dossier`). The case-dossier engine must
instead start from a **free-text clinical dictation** for a specific patient and synthesize a
patient-specific dossier. Before any sections, reasoning, literature, or figures can be made
*case-specific*, the dictation has to become a structured, queryable object.

WS-1 builds that object and the intake layer that produces it — the foundation every later
workstream (WS-2 sections, WS-3 literature, WS-4 figures, WS-5 PDF) reads from.

## 2. Decisions

- **`CaseContext` is a plain dataclass** in a new `neuro_caseboard/case_context.py`, decoupled
  from caseprep contracts (same posture as `model.py`). It is a *presentation/intake* contract,
  not a clinical knowledge model.
- **Intake is LLM-first with a deterministic fallback**, mirroring the Explorer
  (`explore_llm.py`): the model call is **injected** (`complete_fn`) so the parse/validate/merge
  logic is unit-testable offline and deterministic; with no provider configured (or on any
  failure) it degrades to a regex/keyword fallback parser. Locked decision §2.
- **Topic-agnostic.** The deterministic parser extracts only **text-structure** signals that
  generalize across all of neurosurgery — laterality directionals (left/right/bilateral/midline),
  spine-level tokens (`C5-6`, `L4-5`, `T10`) by regex, age, and sex. It does **not** carry a
  clinical-content vocabulary (no disease/vessel/procedure word lists). Semantic fields
  (pathology, procedure, surgical goal, comorbidities) are filled by the LLM; the deterministic
  fallback leaves them best-effort/empty rather than guessing from a hardcoded lexicon. This
  respects the repo's central invariant (LOOP_PROMPT §6) — the same carve-out `ontology.py`
  documents: structural signals are allowed, clinical answers are not.
- **`to_topic()` bridges to the existing engine.** `CaseContext` can synthesize a bare topic
  string (laterality + level/location + pathology + procedure) so the *existing*
  `build_manifest`/`classify_profile`/pipeline run unchanged off a case — no regression to
  `build`/`ask`/`cards`, and WS-2+ layer on top.
- **`missing_critical()` is conservative.** It returns only the few fields a case truly cannot
  proceed without — capped at 3 by construction: a working `procedure`-or-`pathology`, an
  anatomic `target` (level or location), and a `surgical_goal`. Laterality is *captured* but not
  deemed critical (a midline lesion has none — forcing it would be wrong), matching the locked
  requirement that intake "must not interrogate me for everything."

## 3. Detailed design (exact files / functions)

### 3.1 `neuro_caseboard/case_context.py` (new)
```python
@dataclass
class CaseContext:
    # demographics
    age: int | None = None
    sex: str = ""                 # "M" | "F" | ""
    # presentation / imaging / history (prose, model- or user-supplied)
    presentation: str = ""        # chief complaint + HPI, normalized
    imaging: str = ""             # relevant imaging findings
    comorbidities: list[str] = field(default_factory=list)
    medications: list[str] = field(default_factory=list)   # esp. anticoagulants
    prior_surgery: str = ""
    functional_status: str = ""
    # case geometry (the levers that make a dossier case-specific)
    laterality: str = ""          # "left" | "right" | "bilateral" | "midline" | ""
    level: str = ""               # spine level token, e.g. "C5-6"
    location: str = ""            # anatomic location (cranial), e.g. "left frontal"
    # plan
    pathology: str = ""           # working diagnosis / lesion
    procedure: str = ""           # planned operation
    surgical_goal: str = ""       # e.g. resection, decompression, clip ligation
    constraints: list[str] = field(default_factory=list)   # hard constraints
    # provenance
    raw_dictation: str = ""
    source: str = ""              # "llm" | "deterministic"

    def target(self) -> str: ...        # level or location (the anatomic target)
    def to_topic(self) -> str: ...       # bare topic string for the existing pipeline
    def missing_critical(self) -> list[str]: ...   # <=3 field labels truly required
    @classmethod
    def from_dict(cls, d: dict) -> "CaseContext": ...  # tolerant coercion (LLM JSON)
```
- `target()` → `self.level or self.location`.
- `to_topic()` → space-join, de-duped, of `[laterality, level or location, pathology, procedure]`,
  collapsing whitespace; falls back to `presentation[:60]` then `"case"` if all empty. This keeps
  `classify_profile()` / `build_manifest()` working.
- `missing_critical()` → for each of the three critical axes, append a human label if empty:
  `"procedure or working diagnosis"` (if neither procedure nor pathology),
  `"anatomic target (spine level or location)"` (if `target()` empty),
  `"surgical goal"` (if `surgical_goal` empty). At most 3.
- `from_dict()` coerces unknown/missing keys safely, normalizes `laterality`/`sex` to the
  canonical tokens, ints `age`, and lists the list fields (string→[string]).

### 3.2 `neuro_caseboard/intake.py` (new)
```python
INTAKE_SYSTEM = "...attending dictation → structured CaseContext, JSON only..."

def parse_dictation(text, *, complete_fn=None) -> CaseContext:
    """LLM-first parse of free-text dictation → CaseContext; deterministic fallback on
    no-provider / parse-failure. complete_fn injected for offline tests."""

def deterministic_parse(text) -> CaseContext:
    """Regex/keyword text-structure extraction: age, sex, laterality, spine level.
    Semantic fields left empty (no hardcoded clinical vocabulary)."""

def _default_complete(system, user) -> str:   # reuse explore_llm provider dispatch
```
- `parse_dictation`: if `complete_fn` given → call it, `json.loads` (tolerant `_extract_json`
  reused from `explore_llm`), `CaseContext.from_dict`, then **merge** the deterministic
  text-structure signals as a floor for any field the model left blank (laterality/level/age/sex),
  set `source="llm"`, `raw_dictation=text`. On any exception → `deterministic_parse`. If no
  `complete_fn` and no provider available (`explore_llm.llm_available()` is False / `CASEBOARD_LLM=0`)
  → `deterministic_parse`. With a provider available and no injected fn, bind
  `complete_fn` to `explore_llm._default_complete`.
- `deterministic_parse`: `source="deterministic"`, fills age/sex/laterality/level from regex,
  `presentation=text`.
- Regexes (text-structure only):
  - age: `(\d{1,3})\s*(?:-|\s)?\s*(?:year[- ]old|y/?o|yo)\b` and `age[:\s]+(\d{1,3})`
  - sex: word-boundary `male|man|gentleman|boy` → "M"; `female|woman|lady|girl` → "F"
  - laterality: first of `bilateral|midline|left|right` (whole-word)
  - level: `\b([CTL]\d{1,2}\s*[-–/]\s*[CTL]?\d{1,2}|[CTL]\d{1,2})\b` (normalize `–`→`-`,
    drop spaces) → "C5-6"

### 3.3 No wiring into CLI/pipeline yet
WS-1 ships the object + intake only. `caseboard case` (CLI) and the case pipeline arrive in
WS-2/WS-5. `to_topic()` is the seam proving the bridge works.

## 4. Acceptance criteria (LOOP_PROMPT §5 WS-1)
- From a 4–6 sentence dictation, `CaseContext` captures **side / level / goal / key comorbidities**
  correctly on the eval dictations (side/level via the offline deterministic parser; goal +
  comorbidities via the LLM parser, validated offline with an injected fake that returns the
  ground-truth JSON — proving the parse/merge path, not the model).
- `missing_critical()` returns **≤ 3** fields for every eval dictation; **0** when complete.
- Offline tests green; no new dep in the core import path; `caseboard` still imports.
- No regression: `build`/`ask`/`cards` and all existing tests stay green.

## 5. Testing strategy (offline, deterministic — required CI)
`tests/test_case_context.py`:
- `to_topic()` composition (spine level case → contains level + procedure; midline case has no
  laterality); `target()`; `from_dict()` coercion (string→list, age int, laterality/sex
  normalization); `missing_critical()` ≤3 and empty-when-complete.

`tests/test_intake.py` (mirrors `test_explore_llm.py`):
- injected `complete_fn` returning canned JSON → fields populated, `source=="llm"`,
  deterministic floor merged for blanks;
- `_extract_json` tolerance (fenced / prose-wrapped JSON);
- `complete_fn` raising → falls back to deterministic (`source=="deterministic"`);
- no provider + no fn → deterministic;
- `deterministic_parse` extracts age/sex/laterality/level across cranial/spine/vascular samples;
- topic-agnostic guard: deterministic parser leaves pathology/procedure/goal empty (no hardcoded
  clinical vocabulary).

## 6. EVAL (reproducible; offline portion runs here, live portion deferred)
New `eval/case_dictations.json`: a 4–6 sentence dictation per subspecialty
(spine / skull-base / functional / vascular / onc / pediatric — reuse `cases.json` ids) with a
`ground_truth` block (`laterality`, `level`/`location`, `surgical_goal`, `comorbidities`).
New `eval/intake_eval.py`: run the **deterministic** parser over each dictation, score
side/level extraction accuracy and assert `missing_critical()` ≤3; write a dated
`eval/CASE_INTAKE_REPORT_<date>.md`. The LLM-path semantic-accuracy blind-judge grade (goal +
comorbidities) is recorded as **deferred — needs a configured provider** (no key in CI/this env),
consistent with the existing live-PubMed test skip.

## 7. Risks
- **Over-extraction risk** (deterministic parser inventing semantics) → mitigated by restricting
  it to text-structure regexes; semantic fields stay empty without the LLM.
- **Topic-agnostic violation** → guarded by an explicit test asserting no clinical-content
  vocabulary leaks into extraction.
- **Bridge regression** → `to_topic()` covered by tests; existing pipeline untouched this pass.

## 8. Out of scope (this pass)
CLI `caseboard case`, the case pipeline/sections (WS-2), literature (WS-3), figures (WS-4),
PDF surface (WS-5). No Streamlit changes. No new runtime dependency.
