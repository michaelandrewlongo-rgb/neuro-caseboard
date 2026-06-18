# CasePrep Fact-State Rendering Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Ensure patient/case facts extracted from free-text are first-class, provenance-carrying inputs to the CasePrep renderer so known facts are never rendered as missing, unknown facts remain explicit, and outputs generalize across procedure families.

**Architecture:** Add a small deterministic fact-state layer between `case_parser.py` and `schema.py`: extract typed `CaseFact` objects, validate required family fact slots, project facts into render contexts, and add final markdown contradiction guards. Keep evidence synthesis evidence-only; make patient-specific rendering depend on `structured_case.facts`, not on evidence excerpts or markdown re-parsing.

**Tech Stack:** Python dataclasses/stdlib regex, pytest, existing CasePrep schema/rendering pipeline. No new external dependencies for MVP.

**Target State:**

```text
free-text case
  -> caseprep.case_parser.parse_case_input()
  -> CaseSpec + facts: {key -> CaseFact(status/value/source/span)}
  -> caseprep.fact_projection.project_facts_into_schema()
  -> schema render helpers use fact-aware lines
  -> caseprep.fact_validation.validate_rendered_fact_consistency()
  -> markdown dossier + caseprep.yaml
```

**Graceful Degradation:**
- If a fact is absent: render `needs input` only for that semantic slot.
- If a fact is partially supplied: render `known but incomplete` plus the missing subfields.
- If facts conflict: render a conflict warning and keep the fact in `missing_critical_facts` / verification prompts.
- If parser confidence is low: render as `inferred/verify`, not as confirmed.

**Out of Scope for This Phase:**
- Dense retrieval changes.
- LLM synthesis changes.
- New UI/dashboard work.
- Full rewrite of `schema.py` rendering architecture.
- Perfect extraction for every neurosurgical condition.

---

## Phase 1 Acceptance Criteria

1. A thrombectomy input with `left M1`, `NIHSS 18`, `ASPECTS 7`, `LKW 10h`, `CTP mismatch`, and `transfemoral BGC aspiration/stent-retriever` renders those facts as known in:
   - `00-morning-of-case.md`
   - `01-case-summary.md`
   - `02-imaging-review.md`
   - `04-operative-plan.md`
   - `09-open-questions.md`
2. The same facts are not rendered as `incomplete/needs input` anywhere in those sections.
3. Sparse thrombectomy cases still render missing LKW/NIHSS/ASPECTS/access as missing.
4. Basilar and M2 variants do not leak M1/MCA-specific assumptions.
5. ACDF and parasagittal meningioma tests prove the fact-state mechanism is not thrombectomy-only.
6. Existing full suite remains green.

---

## Task 1: Add the `CaseFact` data model

**Objective:** Introduce a generic representation for patient/case facts without changing renderer behavior yet.

**Files:**
- Create: `caseprep/facts.py`
- Test: `tests/test_facts.py`

**Step 1: Write failing tests**

Create `tests/test_facts.py`:

```python
from caseprep.facts import CaseFact, FactStatus, facts_to_dict, fact_value


def test_case_fact_serializes_to_dict():
    fact = CaseFact(
        key="nihss",
        label="NIHSS",
        value=18,
        unit=None,
        status="supplied",
        confidence=1.0,
        source="prompt",
        span="NIHSS 18",
    )

    assert facts_to_dict([fact]) == {
        "nihss": {
            "key": "nihss",
            "label": "NIHSS",
            "value": 18,
            "unit": None,
            "status": "supplied",
            "confidence": 1.0,
            "source": "prompt",
            "span": "NIHSS 18",
            "notes": None,
        }
    }


def test_fact_value_returns_none_for_missing_fact():
    assert fact_value({}, "nihss") is None
```

**Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_facts.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'caseprep.facts'`.

**Step 3: Implement minimal model**

Create `caseprep/facts.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

FactStatus = Literal["supplied", "extracted", "inferred", "needs_input", "conflict"]


@dataclass(frozen=True)
class CaseFact:
    key: str
    label: str
    value: Any
    unit: str | None
    status: FactStatus
    confidence: float
    source: str
    span: str | None = None
    notes: str | None = None


def facts_to_dict(facts: list[CaseFact] | tuple[CaseFact, ...]) -> dict[str, dict[str, Any]]:
    return {fact.key: asdict(fact) for fact in facts}


def fact_value(facts: dict[str, Any], key: str) -> Any | None:
    fact = facts.get(key)
    if not isinstance(fact, dict):
        return None
    if fact.get("status") in {"supplied", "extracted", "inferred"}:
        return fact.get("value")
    return None
```

**Step 4: Run test to verify pass**

Run:

```bash
pytest tests/test_facts.py -q
```

Expected: PASS.

**Step 5: Commit when executing**

```bash
git add caseprep/facts.py tests/test_facts.py
git commit -m "feat: add case fact model"
```

---

## Task 2: Extract thrombectomy facts deterministically

**Objective:** Preserve numeric/value facts from thrombectomy prompts instead of only detecting their presence.

**Files:**
- Modify: `caseprep/case_parser.py`
- Test: `tests/test_case_parser.py`

**Step 1: Write failing test**

Append to `tests/test_case_parser.py`:

```python
def test_thrombectomy_prompt_extracts_structured_facts():
    case = parse_case_input(
        "left M1 MCA occlusion NIHSS 18 ASPECTS 7 LKW 10h "
        "CT perfusion mismatch planned transfemoral BGC aspiration stent-retriever thrombectomy"
    )

    facts = case.to_dict()["facts"]

    assert facts["nihss"]["value"] == 18
    assert facts["aspects"]["value"] == 7
    assert facts["last_known_well"]["value"] == "10h"
    assert facts["perfusion_selection"]["value"] == "CT perfusion mismatch"
    assert facts["access_route"]["value"] == "transfemoral"
    assert facts["balloon_guide"]["value"] is True
    assert facts["aspiration"]["value"] is True
    assert facts["stent_retriever"]["value"] is True
    assert "NIHSS" not in case.missing_critical_facts
    assert "last-known-well time" not in case.missing_critical_facts
    assert "imaging selection" not in case.missing_critical_facts
    assert "access plan" not in case.missing_critical_facts
```

**Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_case_parser.py::test_thrombectomy_prompt_extracts_structured_facts -q
```

Expected: FAIL — `facts` key absent or values absent.

**Step 3: Extend `CaseSpec` with facts**

In `caseprep/case_parser.py`, add a `facts` field to `CaseSpec` and include it in `to_dict()`:

```python
facts: dict[str, dict[str, Any]]
```

If `CaseSpec` is frozen or tuple-like, preserve backward compatibility by defaulting to `{}`.

**Step 4: Add deterministic extraction helpers**

In `caseprep/case_parser.py`, add private helpers:

```python
def _extract_thrombectomy_facts(text: str) -> dict[str, dict[str, Any]]:
    normalized = text.casefold()
    facts: list[CaseFact] = []

    nihss = re.search(r"\bnihss\s*[:=]?\s*(\d{1,2})\b", text, re.IGNORECASE)
    if nihss:
        facts.append(CaseFact("nihss", "NIHSS", int(nihss.group(1)), None, "supplied", 1.0, "prompt", nihss.group(0)))

    aspects = re.search(r"\baspects\s*[:=]?\s*(\d{1,2})\b", text, re.IGNORECASE)
    if aspects:
        facts.append(CaseFact("aspects", "ASPECTS", int(aspects.group(1)), None, "supplied", 1.0, "prompt", aspects.group(0)))

    lkw = re.search(r"\b(?:lkw|last[- ]known[- ]well)\s*[:=]?\s*(\d+\s*(?:h|hr|hrs|hour|hours))\b", text, re.IGNORECASE)
    if lkw:
        facts.append(CaseFact("last_known_well", "Last known well", lkw.group(1).replace(" ", ""), None, "supplied", 1.0, "prompt", lkw.group(0)))

    if "ct perfusion mismatch" in normalized or "ctp mismatch" in normalized or "perfusion mismatch" in normalized:
        facts.append(CaseFact("perfusion_selection", "Perfusion selection", "CT perfusion mismatch", None, "supplied", 0.95, "prompt", "perfusion mismatch"))

    if "transfemoral" in normalized or "femoral access" in normalized:
        facts.append(CaseFact("access_route", "Access route", "transfemoral", None, "supplied", 0.95, "prompt", "transfemoral"))
    elif "transradial" in normalized or "radial access" in normalized:
        facts.append(CaseFact("access_route", "Access route", "transradial", None, "supplied", 0.95, "prompt", "radial"))

    if "bgc" in normalized or "balloon guide" in normalized or "balloon-guide" in normalized:
        facts.append(CaseFact("balloon_guide", "Balloon guide", True, None, "supplied", 0.95, "prompt", "BGC"))
    if "aspiration" in normalized:
        facts.append(CaseFact("aspiration", "Aspiration", True, None, "supplied", 0.95, "prompt", "aspiration"))
    if "stent retriever" in normalized or "stent-retriever" in normalized:
        facts.append(CaseFact("stent_retriever", "Stent retriever", True, None, "supplied", 0.95, "prompt", "stent-retriever"))

    return facts_to_dict(facts)
```

**Step 5: Wire helper into parse flow**

Inside `deterministic_parse_case()` / `parse_case_input()`, after family selection:

```python
facts = {}
if family and family.id == "endovascular_thrombectomy":
    facts.update(_extract_thrombectomy_facts(text))
```

Pass `facts=facts` into `CaseSpec`.

**Step 6: Make missing checks fact-aware**

In `_missing_critical_facts()`, for thrombectomy, use fact keys before boolean string checks:

```python
if "last_known_well" not in facts and not _has_last_known_well(normalized):
    missing.append("last-known-well time")
```

If threading `facts` through `_missing_critical_facts()` is too invasive, first compute facts before missing and add a `facts` parameter.

**Step 7: Run targeted parser test**

Run:

```bash
pytest tests/test_case_parser.py::test_thrombectomy_prompt_extracts_structured_facts -q
```

Expected: PASS.

**Step 8: Commit when executing**

```bash
git add caseprep/case_parser.py tests/test_case_parser.py
git commit -m "feat: extract thrombectomy case facts"
```

---

## Task 3: Add generic fact projection helpers

**Objective:** Provide one API that renderers can use to decide whether to print a known fact, a verification prompt, or a missing prompt.

**Files:**
- Create: `caseprep/fact_projection.py`
- Test: `tests/test_fact_projection.py`

**Step 1: Write failing tests**

Create `tests/test_fact_projection.py`:

```python
from caseprep.fact_projection import fact_line, missing_or_confirm_line


def test_fact_line_renders_known_value():
    facts = {"nihss": {"label": "NIHSS", "value": 18, "status": "supplied", "source": "prompt"}}
    assert fact_line(facts, "nihss", missing="NIHSS: incomplete/needs input") == "NIHSS: 18 (supplied from prompt)"


def test_fact_line_renders_missing_value():
    assert fact_line({}, "nihss", missing="NIHSS: incomplete/needs input") == "NIHSS: incomplete/needs input"


def test_missing_or_confirm_line_reframes_known_fact_as_confirmation():
    facts = {"aspects": {"label": "ASPECTS", "value": 7, "status": "supplied", "source": "prompt"}}
    assert missing_or_confirm_line(
        facts,
        "aspects",
        missing="ASPECTS score needs input",
        confirm="Confirm ASPECTS {value} and document involved regions.",
    ) == "Confirm ASPECTS 7 and document involved regions."
```

**Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_fact_projection.py -q
```

Expected: FAIL — module absent.

**Step 3: Implement helper module**

Create `caseprep/fact_projection.py`:

```python
from __future__ import annotations

from typing import Any

KNOWN_STATUSES = {"supplied", "extracted", "inferred"}


def _fact(facts: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = facts.get(key)
    return value if isinstance(value, dict) else None


def has_known_fact(facts: dict[str, Any], key: str) -> bool:
    fact = _fact(facts, key)
    return bool(fact and fact.get("status") in KNOWN_STATUSES and fact.get("value") not in {None, ""})


def fact_line(facts: dict[str, Any], key: str, *, missing: str) -> str:
    fact = _fact(facts, key)
    if not has_known_fact(facts, key):
        return missing
    return f"{fact.get('label', key)}: {fact['value']} ({fact.get('status')} from {fact.get('source', 'unknown source')})"


def missing_or_confirm_line(
    facts: dict[str, Any],
    key: str,
    *,
    missing: str,
    confirm: str,
) -> str:
    fact = _fact(facts, key)
    if not has_known_fact(facts, key):
        return missing
    return confirm.format(value=fact["value"], label=fact.get("label", key))
```

**Step 4: Run tests**

Run:

```bash
pytest tests/test_fact_projection.py -q
```

Expected: PASS.

**Step 5: Commit when executing**

```bash
git add caseprep/fact_projection.py tests/test_fact_projection.py
git commit -m "feat: add fact projection helpers"
```

---

## Task 4: Include facts in `caseprep.yaml` schema output

**Objective:** Make facts visible in the structured artifact so downstream tests and reviewers can inspect them.

**Files:**
- Modify: `caseprep/schema.py`
- Test: `tests/test_renderers.py` or `tests/test_fact_propagation.py`

**Step 1: Write failing test**

Create `tests/test_fact_propagation.py` if it does not exist:

```python
from caseprep.case_parser import parse_case_input
from caseprep.schema import build_caseprep_schema


def test_build_schema_preserves_structured_case_facts():
    case = parse_case_input("left M1 occlusion NIHSS 18 ASPECTS 7 LKW 10h thrombectomy")
    schema = build_caseprep_schema("left M1 occlusion NIHSS 18 ASPECTS 7 LKW 10h thrombectomy", structured_case=case.to_dict())

    assert schema["case"]["facts"]["nihss"]["value"] == 18
    assert schema["case"]["facts"]["aspects"]["value"] == 7
    assert schema["case"]["facts"]["last_known_well"]["value"] == "10h"
```

**Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_fact_propagation.py::test_build_schema_preserves_structured_case_facts -q
```

Expected: FAIL — `facts` absent from schema.

**Step 3: Propagate facts into schema**

In `caseprep/schema.py`, inside `build_caseprep_schema()`, ensure the schema includes:

```python
"case": {
    ...,
    "facts": structured_case.get("facts", {}) if structured_case else {},
}
```

If `case` already exists, add only the `facts` key. Do not disturb existing snapshot fields.

**Step 4: Add local accessor**

In `caseprep/schema.py`, near `_structured_case_value()` add:

```python
def _case_facts(schema: dict[str, Any]) -> dict[str, Any]:
    case = schema.get("case", {})
    facts = case.get("facts", {}) if isinstance(case, dict) else {}
    return facts if isinstance(facts, dict) else {}
```

**Step 5: Run test**

Run:

```bash
pytest tests/test_fact_propagation.py::test_build_schema_preserves_structured_case_facts -q
```

Expected: PASS.

**Step 6: Commit when executing**

```bash
git add caseprep/schema.py tests/test_fact_propagation.py
git commit -m "feat: preserve case facts in schema"
```

---

## Task 5: Make thrombectomy morning-of-case fact-aware

**Objective:** Fix the highest-value page first: known thrombectomy facts should appear up front and not be asked for as missing.

**Files:**
- Modify: `caseprep/schema.py`
- Test: `tests/test_fact_propagation.py`

**Step 1: Write failing test**

Add:

```python
from caseprep.case_parser import parse_case_input
from caseprep.schema import build_caseprep_schema, render_caseprep_files


def test_thrombectomy_morning_page_renders_supplied_facts_as_known():
    topic = (
        "left M1 MCA occlusion NIHSS 18 ASPECTS 7 LKW 10h "
        "CT perfusion mismatch planned transfemoral BGC aspiration stent-retriever thrombectomy"
    )
    case = parse_case_input(topic)
    schema = build_caseprep_schema(topic, structured_case=case.to_dict())
    files = render_caseprep_files(schema)
    morning = files["00-morning-of-case.md"]

    assert "NIHSS: 18" in morning
    assert "ASPECTS: 7" in morning
    assert "Last known well: 10h" in morning
    assert "CT perfusion mismatch" in morning
    assert "transfemoral" in morning.casefold()
    assert "NIHSS/disabling deficit: incomplete/needs input" not in morning
    assert "LKW/time window: incomplete/needs input" not in morning
    assert "ASPECTS/core: incomplete/needs input" not in morning
```

**Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_fact_propagation.py::test_thrombectomy_morning_page_renders_supplied_facts_as_known -q
```

Expected: FAIL — morning page still hardcodes incomplete lines.

**Step 3: Add thrombectomy known-facts renderer**

In `caseprep/schema.py`, add helper near thrombectomy render helpers:

```python
def _render_thrombectomy_known_facts(schema: dict[str, Any]) -> str:
    facts = _case_facts(schema)
    lines = [
        fact_line(facts, "nihss", missing="NIHSS: incomplete/needs input"),
        fact_line(facts, "aspects", missing="ASPECTS: incomplete/needs input"),
        fact_line(facts, "last_known_well", missing="Last known well: incomplete/needs input"),
        fact_line(facts, "perfusion_selection", missing="Perfusion selection: incomplete/needs input"),
        fact_line(facts, "access_route", missing="Access route: incomplete/needs input"),
    ]
    if has_known_fact(facts, "balloon_guide"):
        lines.append("Balloon guide: planned/supplied")
    if has_known_fact(facts, "aspiration"):
        lines.append("Aspiration: planned/supplied")
    if has_known_fact(facts, "stent_retriever"):
        lines.append("Stent retriever: planned/supplied")
    return "\n".join(f"- {line}" for line in lines)
```

Add imports at top of `schema.py`:

```python
from caseprep.fact_projection import fact_line, has_known_fact, missing_or_confirm_line
```

**Step 4: Insert into `_render_morning_of_case()`**

In thrombectomy branch of `_render_morning_of_case()`, add a `## Patient-Specific Known Facts` section before open questions/checklists:

```markdown
## Patient-Specific Known Facts

{_render_thrombectomy_known_facts(schema)}
```

Then replace hardcoded missing LKW/NIHSS/ASPECTS lines with `missing_or_confirm_line(...)` equivalents.

**Step 5: Run test**

Run:

```bash
pytest tests/test_fact_propagation.py::test_thrombectomy_morning_page_renders_supplied_facts_as_known -q
```

Expected: PASS.

**Step 6: Commit when executing**

```bash
git add caseprep/schema.py tests/test_fact_propagation.py
git commit -m "feat: render thrombectomy morning facts"
```

---

## Task 6: Make thrombectomy imaging and operative plan fact-aware

**Objective:** Propagate known facts beyond the morning page into imaging and operative sections.

**Files:**
- Modify: `caseprep/schema.py`
- Test: `tests/test_fact_propagation.py`

**Step 1: Write failing test**

Add:

```python
def test_thrombectomy_imaging_and_operative_plan_use_supplied_facts():
    topic = (
        "left M1 MCA occlusion NIHSS 18 ASPECTS 7 LKW 10h "
        "CT perfusion mismatch planned transfemoral BGC aspiration stent-retriever thrombectomy"
    )
    case = parse_case_input(topic)
    schema = build_caseprep_schema(topic, structured_case=case.to_dict())
    files = render_caseprep_files(schema)

    imaging = files["02-imaging-review.md"]
    operative = files["04-operative-plan.md"]

    assert "ASPECTS: 7" in imaging
    assert "CT perfusion mismatch" in imaging
    assert "ASPECTS: incomplete/needs input" not in imaging

    assert "transfemoral" in operative.casefold()
    assert "balloon guide" in operative.casefold()
    assert "aspiration" in operative.casefold()
    assert "stent retriever" in operative.casefold()
```

**Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_fact_propagation.py::test_thrombectomy_imaging_and_operative_plan_use_supplied_facts -q
```

Expected: FAIL.

**Step 3: Update `_render_thrombectomy_imaging()`**

Replace the hardcoded ASPECTS/perfusion lines with fact-aware lines:

```python
facts = _case_facts(schema)
aspects_line = missing_or_confirm_line(
    facts,
    "aspects",
    missing="ASPECTS: incomplete/needs input; document numeric score, involved regions, mass effect, and whether large-core considerations apply.",
    confirm="ASPECTS: {value} supplied; confirm involved regions, mass effect, and whether large-core considerations apply.",
)
perfusion_line = missing_or_confirm_line(
    facts,
    "perfusion_selection",
    missing="CTP/MR perfusion: incomplete/needs input when late/unknown-window selection is required.",
    confirm="Perfusion selection: {value} supplied; still document core volume, penumbra/hypoperfusion volume, mismatch ratio, and thresholds.",
)
```

Use `aspects_line` and `perfusion_line` in the markdown body.

**Step 4: Update `_render_thrombectomy_operative_plan()`**

Add a small `## Supplied Access / Technique Plan` block:

```python
def _render_thrombectomy_supplied_technique(schema: dict[str, Any]) -> str:
    facts = _case_facts(schema)
    lines = [fact_line(facts, "access_route", missing="Access route: incomplete/needs input")]
    if has_known_fact(facts, "balloon_guide"):
        lines.append("Balloon guide: supplied/planned; verify anatomy and operator preference.")
    if has_known_fact(facts, "aspiration"):
        lines.append("Aspiration: supplied/planned as part of first-pass or combined strategy.")
    if has_known_fact(facts, "stent_retriever"):
        lines.append("Stent retriever: supplied/planned; verify vessel size, landing zone, and IFU constraints.")
    return "\n".join(f"- {line}" for line in lines)
```

Insert it before `## Access And Setup`.

**Step 5: Run test**

Run:

```bash
pytest tests/test_fact_propagation.py::test_thrombectomy_imaging_and_operative_plan_use_supplied_facts -q
```

Expected: PASS.

**Step 6: Commit when executing**

```bash
git add caseprep/schema.py tests/test_fact_propagation.py
git commit -m "feat: propagate thrombectomy facts into imaging and operative plan"
```

---

## Task 7: Make open questions subtract known facts

**Objective:** Stop asking for facts already supplied; turn known facts into confirmation prompts instead.

**Files:**
- Modify: `caseprep/schema.py`
- Test: `tests/test_fact_propagation.py`

**Step 1: Write failing test**

Add:

```python
def test_open_questions_do_not_ask_for_supplied_thrombectomy_facts():
    topic = (
        "left M1 MCA occlusion NIHSS 18 ASPECTS 7 LKW 10h "
        "CT perfusion mismatch planned transfemoral BGC aspiration stent-retriever thrombectomy"
    )
    case = parse_case_input(topic)
    schema = build_caseprep_schema(topic, structured_case=case.to_dict())
    files = render_caseprep_files(schema)
    questions = files["09-open-questions.md"]

    assert "What is the NIHSS" not in questions
    assert "NIHSS?" not in questions
    assert "What is the ASPECTS" not in questions
    assert "ASPECTS?" not in questions
    assert "What is the last-known-well" not in questions
    assert "Confirm current NIHSS/exam" in questions
    assert "Confirm ASPECTS 7" in questions
    assert "Unknown: thrombolytic" in questions or "thrombolytic" in questions.casefold()
```

**Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_fact_propagation.py::test_open_questions_do_not_ask_for_supplied_thrombectomy_facts -q
```

Expected: FAIL.

**Step 3: Add thrombectomy open-question helper**

In `caseprep/schema.py`:

```python
def _thrombectomy_open_questions(schema: dict[str, Any]) -> list[str]:
    facts = _case_facts(schema)
    questions: list[str] = []

    questions.append(missing_or_confirm_line(
        facts,
        "nihss",
        missing="Unknown: NIHSS/disabling deficit — document baseline and current pre-puncture exam.",
        confirm="Confirm current NIHSS/exam immediately pre-puncture; initial NIHSS supplied as {value}.",
    ))
    questions.append(missing_or_confirm_line(
        facts,
        "aspects",
        missing="Unknown: ASPECTS/core — document NCCT score, involved regions, mass effect, and core estimate.",
        confirm="Confirm ASPECTS {value} on NCCT and document involved regions/core volume.",
    ))
    questions.append(missing_or_confirm_line(
        facts,
        "last_known_well",
        missing="Unknown: last-known-well/time window — required for EVT/thrombolytic decisions.",
        confirm="Confirm LKW {value}; late-window cases still require tissue-selection details and attending/stroke-team agreement.",
    ))

    questions.extend([
        "Unknown: thrombolytic/TNK/tPA eligibility and administration status.",
        "Unknown: anticoagulation/coagulopathy and relevant labs.",
        "Unknown: baseline mRS/goals of care.",
        "Unknown: collateral grade and quantitative CTP core/penumbra values if late-window selection is used.",
    ])
    return questions
```

Wire thrombectomy branch of `_render_open_questions()` to use this list.

**Step 4: Run test**

Run:

```bash
pytest tests/test_fact_propagation.py::test_open_questions_do_not_ask_for_supplied_thrombectomy_facts -q
```

Expected: PASS.

**Step 5: Commit when executing**

```bash
git add caseprep/schema.py tests/test_fact_propagation.py
git commit -m "feat: subtract known thrombectomy facts from open questions"
```

---

## Task 8: Add contradiction/leakage tests for vascular variants

**Objective:** Prove the fact-aware changes do not overfit left-M1 thrombectomy.

**Files:**
- Create: `tests/test_rendering_contradictions.py`

**Step 1: Write tests**

Create:

```python
from caseprep.case_parser import parse_case_input
from caseprep.schema import build_caseprep_schema, render_caseprep_files


def _render_all(topic: str) -> str:
    case = parse_case_input(topic)
    schema = build_caseprep_schema(topic, structured_case=case.to_dict())
    return "\n\n".join(render_caseprep_files(schema).values())


def test_left_m1_does_not_render_right_m1_as_target():
    text = _render_all("left M1 MCA occlusion NIHSS 18 ASPECTS 7 LKW 10h thrombectomy")
    assert "left M1 MCA occlusion" in text
    assert "right M1 MCA occlusion" not in text


def test_basilar_thrombectomy_does_not_leak_mca_syndrome_as_primary_target():
    text = _render_all("basilar artery occlusion acute ischemic stroke mechanical thrombectomy")
    assert "basilar artery occlusion" in text
    assert "posterior circulation" in text.casefold()
    assert "right M1 MCA occlusion" not in text
    assert "left M1 MCA occlusion" not in text
    assert "malignant MCA edema" not in text


def test_underspecified_thrombectomy_does_not_invent_target():
    text = _render_all("stroke thrombectomy")
    assert "access/occlusion anatomy needs input" in text
    assert "right M1 MCA occlusion" not in text
    assert "left M1 MCA occlusion" not in text
    assert "basilar artery occlusion" not in text
```

**Step 2: Run tests**

Run:

```bash
pytest tests/test_rendering_contradictions.py -q
```

Expected: PASS after previous tasks; if FAIL, fix only the variant leakage causing failure.

**Step 3: Commit when executing**

```bash
git add tests/test_rendering_contradictions.py
git commit -m "test: add thrombectomy rendering contradiction gates"
```

---

## Task 9: Add two non-vascular fact-propagation tests

**Objective:** Lock in that the mechanism is pipeline-level, not thrombectomy-only.

**Files:**
- Modify: `tests/test_fact_propagation.py`
- Possibly modify: `caseprep/case_parser.py`, `caseprep/schema.py` only if tests reveal existing parser/schema gaps.

**Step 1: Add ACDF test**

```python
def test_acdf_known_level_laterality_and_root_are_not_marked_missing():
    topic = "right C6 radiculopathy from C5-6 foraminal disc osteophyte planned C5-6 ACDF with cage and anterior plate"
    case = parse_case_input(topic)
    schema = build_caseprep_schema(topic, structured_case=case.to_dict())
    files = render_caseprep_files(schema)
    text = "\n\n".join(files.values())

    assert "C5-6" in text
    assert "right" in text.casefold()
    assert "C6" in text
    assert "ACDF" in text or "anterior cervical discectomy" in text
    assert "cervical level" not in case.missing_critical_facts
    assert "symptomatic laterality" not in case.missing_critical_facts
```

**Step 2: Add meningioma test**

```python
def test_parasagittal_meningioma_preserves_known_location_size_and_sinus_relationship():
    topic = "left 3.2 cm parasagittal meningioma abutting the superior sagittal sinus planned craniotomy for resection"
    case = parse_case_input(topic)
    schema = build_caseprep_schema(topic, structured_case=case.to_dict())
    files = render_caseprep_files(schema)
    text = "\n\n".join(files.values())

    assert "left" in text.casefold()
    assert "3.2" in text
    assert "parasagittal" in text.casefold()
    assert "superior sagittal sinus" in text.casefold() or "SSS" in text
    assert "tumor location" not in case.missing_critical_facts
    assert "venous/sinus relationship" not in case.missing_critical_facts
```

**Step 3: Run tests**

Run:

```bash
pytest tests/test_fact_propagation.py -q
```

Expected: PASS or reveal small parser/schema gaps. Fix only direct gaps; do not expand into broad extraction rewrite.

**Step 4: Commit when executing**

```bash
git add tests/test_fact_propagation.py caseprep/case_parser.py caseprep/schema.py
git commit -m "test: prove fact propagation across procedure families"
```

---

## Task 10: Add final rendered consistency validator

**Objective:** Catch regressions where a known fact exists but rendered markdown still says that semantic fact is missing.

**Files:**
- Create: `caseprep/fact_validation.py`
- Test: `tests/test_fact_validation.py`
- Modify: `caseprep/core/builder.py` only after standalone tests pass.

**Step 1: Write standalone tests**

Create `tests/test_fact_validation.py`:

```python
from caseprep.fact_validation import validate_rendered_fact_consistency


def test_validator_flags_known_nihss_rendered_as_missing():
    schema = {"case": {"facts": {"nihss": {"label": "NIHSS", "value": 18, "status": "supplied"}}}}
    markdown = "NIHSS/disabling deficit: incomplete/needs input"

    warnings = validate_rendered_fact_consistency(schema, markdown)

    assert any("nihss" in warning.casefold() for warning in warnings)


def test_validator_allows_missing_fact_rendered_as_missing():
    schema = {"case": {"facts": {}}}
    markdown = "NIHSS/disabling deficit: incomplete/needs input"

    assert validate_rendered_fact_consistency(schema, markdown) == []
```

**Step 2: Run test to verify failure**

Run:

```bash
pytest tests/test_fact_validation.py -q
```

Expected: FAIL — module absent.

**Step 3: Implement minimal validator**

Create `caseprep/fact_validation.py`:

```python
from __future__ import annotations

from typing import Any

KNOWN_STATUSES = {"supplied", "extracted", "inferred"}

MISSING_PHRASES_BY_FACT = {
    "nihss": ["NIHSS/disabling deficit: incomplete/needs input", "NIHSS: incomplete/needs input"],
    "aspects": ["ASPECTS/core: incomplete/needs input", "ASPECTS: incomplete/needs input"],
    "last_known_well": ["LKW/time window: incomplete/needs input", "Last known well: incomplete/needs input"],
    "access_route": ["Access route: incomplete/needs input"],
}


def _facts(schema: dict[str, Any]) -> dict[str, Any]:
    case = schema.get("case", {})
    facts = case.get("facts", {}) if isinstance(case, dict) else {}
    return facts if isinstance(facts, dict) else {}


def validate_rendered_fact_consistency(schema: dict[str, Any], markdown: str) -> list[str]:
    warnings: list[str] = []
    facts = _facts(schema)
    for key, phrases in MISSING_PHRASES_BY_FACT.items():
        fact = facts.get(key)
        if not isinstance(fact, dict):
            continue
        if fact.get("status") not in KNOWN_STATUSES or fact.get("value") in {None, ""}:
            continue
        for phrase in phrases:
            if phrase in markdown:
                warnings.append(f"Known fact {key}={fact.get('value')} is rendered as missing via phrase: {phrase}")
    return warnings
```

**Step 4: Run standalone tests**

Run:

```bash
pytest tests/test_fact_validation.py -q
```

Expected: PASS.

**Step 5: Hook validator into builder warnings**

In `caseprep/core/builder.py`, after markdown files are rendered or after `rendered_files` exists, combine generated markdown and append validation warnings to existing warnings/logs. Keep this non-fatal initially.

Pseudo-code:

```python
from caseprep.fact_validation import validate_rendered_fact_consistency

combined_markdown = "\n\n".join(rendered_files.values())
warnings.extend(validate_rendered_fact_consistency(schema, combined_markdown))
```

**Step 6: Add integration assertion if builder exposes warnings**

If existing builder return object has warnings, add a test ensuring a clean supplied-facts case has no fact consistency warnings.

**Step 7: Commit when executing**

```bash
git add caseprep/fact_validation.py caseprep/core/builder.py tests/test_fact_validation.py
git commit -m "feat: validate rendered facts against structured facts"
```

---

## Task 11: Run targeted and full validation

**Objective:** Verify the fact-state changes work without breaking the existing pipeline.

**Files:**
- No code changes unless tests fail.

**Step 1: Run new tests**

```bash
pytest tests/test_facts.py tests/test_fact_projection.py tests/test_fact_propagation.py tests/test_fact_validation.py tests/test_rendering_contradictions.py -q
```

Expected: all pass.

**Step 2: Run existing targeted suite**

```bash
pytest tests/test_case_parser.py tests/test_renderers.py tests/test_canonical_eval.py -q
```

Expected: all pass.

**Step 3: Run full suite**

```bash
pytest -q
```

Expected: full suite passes.

**Step 4: Build fresh thrombectomy sandbox**

Use the same case text as the failed review:

```bash
python -m caseprep build \
  "left M1 MCA occlusion NIHSS 18 ASPECTS 7 LKW 10h CTP mismatch planned transfemoral BGC aspiration stent-retriever thrombectomy" \
  --output-dir /tmp/caseprep-fact-state-left-m1-smoke
```

If the actual CLI differs, use the existing command from prior sandbox generation.

**Step 5: Grep-rendered facts manually**

```bash
python - <<'PY'
from pathlib import Path
root = Path('/tmp/caseprep-fact-state-left-m1-smoke')
for name in ['00-morning-of-case.md', '01-case-summary.md', '02-imaging-review.md', '04-operative-plan.md', '09-open-questions.md']:
    text = (root / name).read_text()
    print('\n---', name, '---')
    for needle in ['NIHSS', 'ASPECTS', 'LKW', 'Last known well', 'transfemoral', 'balloon', 'aspiration', 'stent']:
        if needle.casefold() in text.casefold():
            print('contains', needle)
PY
```

Expected: known facts appear in the intended sections.

**Step 6: Commit validation-only fixes if needed**

```bash
git add .
git commit -m "test: validate fact-state rendering pipeline"
```

---

## Task 12: Fresh blind clinical review gate

**Objective:** Verify the product-level failure is actually fixed, not just the tests.

**Files:**
- Output only: `/tmp/caseprep-fact-state-left-m1-smoke`
- Optional future fixture: `tests/fixtures/rendering_fact_cases.yaml`

**Step 1: Generate blind review packet**

Use these cases:

1. Left M1 late-window supplied facts.
2. Right M1 sparse facts.
3. Left M2 radial-access variant.
4. Basilar thrombectomy.
5. Underspecified stroke thrombectomy.
6. ACDF C5-6 right C6 with cage/plate.
7. Parasagittal meningioma abutting SSS.

**Step 2: Delegate blinded review**

Reviewer sees only raw input + generated dossier. Ask for scores on:

- Known facts surfaced.
- Known facts not marked missing.
- Remaining questions are truly missing.
- No invented specifics.
- Morning-of-case clinical utility.
- Cross-family generalization.

**Step 3: Convert any failure into deterministic test**

If reviewer finds a repeated failure, add it to:

- `tests/test_fact_propagation.py`, or
- `tests/test_rendering_contradictions.py`, or
- future `tests/fixtures/rendering_fact_cases.yaml`.

**Step 4: Commit regression test**

```bash
git add tests/
git commit -m "test: add blind-review regression for fact rendering"
```

---

## Implementation Order Summary

1. `CaseFact` model.
2. Thrombectomy fact extraction.
3. Fact projection helpers.
4. Preserve facts in schema/YAML.
5. Morning-of-case fact-aware rendering.
6. Imaging and operative fact-aware rendering.
7. Open questions subtract known facts.
8. Vascular contradiction tests.
9. Non-vascular generalization tests.
10. Rendered consistency validator.
11. Targeted/full test suite.
12. Fresh blind review.

---

## Main Risks

- **Risk:** Scope creep into universal clinical NLP.
  - **Mitigation:** Only add deterministic high-salience facts for this phase.

- **Risk:** Renderer still contains hardcoded missing phrases.
  - **Mitigation:** Add `fact_validation.py` guard to catch known facts rendered as missing.

- **Risk:** Overfitting to left M1.
  - **Mitigation:** Basilar, M2, underspecified, ACDF, and meningioma tests are required before acceptance.

- **Risk:** Existing uncommitted query-enrichment work is mixed with this change.
  - **Mitigation:** Inspect `git status` before implementation; commit or isolate unrelated work before starting.

---

## Final Verification Commands

```bash
pytest tests/test_facts.py \
       tests/test_fact_projection.py \
       tests/test_fact_propagation.py \
       tests/test_fact_validation.py \
       tests/test_rendering_contradictions.py -q

pytest tests/test_case_parser.py tests/test_renderers.py tests/test_canonical_eval.py -q

pytest -q
```

Expected: all pass.

---

## Handoff Note

Plan complete. Before implementation, run `git status --short` and preserve the existing uncommitted NSGY query-enrichment work. Implementation should proceed task-by-task with TDD and commits after each task if the repository is in a safe state to commit.
