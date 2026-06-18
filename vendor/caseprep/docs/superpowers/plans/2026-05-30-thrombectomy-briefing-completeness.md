# Thrombectomy Briefing Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a sourced `prognostic_signs` block (favorable/unfavorable outcome indicators, each cited to landmark thrombectomy trials) to the thrombectomy briefing, plus a deterministic source-coverage audit that fails the canonical eval when a sourceable clinical claim is left uncited.

**Architecture:** Authored prognostic content (a family-keyed registry) is cited to stable evidence-pack item IDs, populated into the schema by the core builder with provenance, and rendered at the top of `06-postop-plan.md`. A new `check_source_coverage` audit extends `caseprep/evaluation/rubric.py` with family-keyed sourceable-field and patient-data-exempt registries. Both are built family-agnostic so later cycles register entries without changing logic.

**Tech Stack:** Python 3.10+, `uv run pytest`, existing `caseprep` schema/render/rubric modules, `caseprep/evidence_packs/thrombectomy.py` (`THROMBECTOMY_PACKS`, `EvidencePackItem`), `caseprep/core/contracts.py` (`ProvenanceRecord`).

**Test runner note:** Use `uv run pytest ...`. A harmless `ModuleNotFoundError: No module named 'cuda'` from a `.pth` file prints at startup — ignore it.

**Spec:** `docs/superpowers/specs/2026-05-30-thrombectomy-briefing-completeness-design.md`

---

## File Structure

- **Create** `caseprep/prognostic_signs.py` — authored, family-keyed prognostic-sign registry + pack-ref resolver. One responsibility: declare and resolve prognostic content.
- **Modify** `caseprep/schema.py` — add `_render_thrombectomy_prognostic_signs`, add `_render_thrombectomy_postop`, branch `_render_postop` to it.
- **Modify** `caseprep/core/builder.py` — populate `schema["case"]["prognostic_signs"]` + emit a `ProvenanceRecord` for thrombectomy.
- **Modify** `caseprep/evaluation/rubric.py` — add `SOURCEABLE_FIELDS`, `PATIENT_DATA_EXEMPT`, `check_source_coverage`; wire into `evaluate_case_output`.
- **Create** tests: `tests/test_prognostic_signs.py`, `tests/test_prognostic_render.py`, `tests/test_core_builder_prognostic.py`, `tests/test_source_coverage_audit.py`.
- **Modify** `README.md` — mark Cycle 1 in progress under the program roadmap.

---

## Task 1: Authored prognostic-signs registry

**Files:**
- Create: `caseprep/prognostic_signs.py`
- Test: `tests/test_prognostic_signs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prognostic_signs.py
from caseprep.prognostic_signs import (
    prognostic_signs_for_family,
    valid_thrombectomy_pack_ids,
    resolve_pack_refs,
)


def test_thrombectomy_has_favorable_and_unfavorable():
    block = prognostic_signs_for_family("endovascular_thrombectomy")
    assert block is not None
    assert block["favorable"] and block["unfavorable"]


def test_every_indicator_cites_a_real_pack_id():
    block = prognostic_signs_for_family("endovascular_thrombectomy")
    valid = valid_thrombectomy_pack_ids()
    for group in ("favorable", "unfavorable"):
        for entry in block[group]:
            assert entry["indicator"] and entry["detail"]
            assert entry["source_ids"], f"{entry['indicator']} has no source_ids"
            for sid in entry["source_ids"]:
                assert sid in valid, f"{sid} not a thrombectomy pack item id"


def test_unknown_family_returns_none():
    assert prognostic_signs_for_family("spine_acdf") is None


def test_resolve_pack_refs_renders_pmid():
    refs = resolve_pack_refs(["hermes"])
    assert "hermes" in refs.lower()
    assert "26898852" in refs  # HERMES PMID
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prognostic_signs.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'caseprep.prognostic_signs'`

- [ ] **Step 3: Write minimal implementation**

```python
# caseprep/prognostic_signs.py
"""Authored, cited prognostic-sign registry, keyed by procedure family.

Content is curated (like the decision/rescue tables), not per-case LLM output.
Each indicator cites stable evidence-pack item IDs so a clinician can trace it to
a landmark trial/guideline. Built family-agnostic: later cycles add families to
`_FAMILY_PROGNOSTIC_SIGNS` and the audit/render reuse this module unchanged.
"""
from __future__ import annotations

from typing import Any

from caseprep.evidence_packs.thrombectomy import THROMBECTOMY_PACKS

# Each entry: {"indicator": str, "detail": str, "source_ids": [pack_item_id, ...]}
_THROMBECTOMY_PROGNOSTIC_SIGNS: dict[str, list[dict[str, Any]]] = {
    "favorable": [
        {"indicator": "High ASPECTS (>=6)",
         "detail": "Limited early ischemic change predicts better EVT benefit.",
         "source_ids": ["hermes", "aha_asa_2019_update"]},
        {"indicator": "Good collaterals",
         "detail": "Robust pial collaterals sustain penumbra and improve outcome.",
         "source_ids": ["hermes"]},
        {"indicator": "Short onset-to-reperfusion time",
         "detail": "Faster reperfusion strongly increases the odds of independence.",
         "source_ids": ["hermes"]},
        {"indicator": "Successful reperfusion (mTICI 2b-3)",
         "detail": "Substantial/complete reperfusion is the dominant modifiable predictor.",
         "source_ids": ["hermes"]},
        {"indicator": "Late-window clinical-core mismatch met",
         "detail": "DAWN/DEFUSE-3 selection criteria identify late patients who still benefit.",
         "source_ids": ["dawn", "defuse_3"]},
        {"indicator": "Younger age / low baseline mRS",
         "detail": "Younger, independent patients have greater absolute benefit.",
         "source_ids": ["hermes"]},
    ],
    "unfavorable": [
        {"indicator": "Low ASPECTS / large ischemic core",
         "detail": "Large established core lowers benefit and raises hemorrhage risk; weigh large-core trial caveats.",
         "source_ids": ["select2", "hermes"]},
        {"indicator": "Poor collaterals",
         "detail": "Sparse collaterals accelerate core growth and worsen outcome.",
         "source_ids": ["hermes"]},
        {"indicator": "Long time-to-reperfusion",
         "detail": "Each hour of delay reduces the probability of functional independence.",
         "source_ids": ["hermes"]},
        {"indicator": "Failed / partial reperfusion (<mTICI 2b)",
         "detail": "Incomplete reperfusion predicts poor functional outcome.",
         "source_ids": ["hermes"]},
        {"indicator": "Late presentation without qualifying mismatch",
         "detail": "Outside DAWN/DEFUSE-3 selection, late EVT benefit is unproven.",
         "source_ids": ["dawn", "defuse_3"]},
    ],
}

_FAMILY_PROGNOSTIC_SIGNS: dict[str, dict[str, list[dict[str, Any]]]] = {
    "endovascular_thrombectomy": _THROMBECTOMY_PROGNOSTIC_SIGNS,
}


def prognostic_signs_for_family(family_id: str) -> dict[str, list[dict[str, Any]]] | None:
    """Return the authored {favorable, unfavorable} block for a family, or None."""
    block = _FAMILY_PROGNOSTIC_SIGNS.get(family_id)
    if block is None:
        return None
    # Return a deep-ish copy so callers can mutate freely.
    return {group: [dict(entry) for entry in entries] for group, entries in block.items()}


def _thrombectomy_item_index() -> dict[str, Any]:
    index: dict[str, Any] = {}
    for pack in THROMBECTOMY_PACKS.values():
        for item in pack.items:
            index[item.id] = item
    return index


def valid_thrombectomy_pack_ids() -> set[str]:
    """All item IDs declared across the thrombectomy evidence packs."""
    return set(_thrombectomy_item_index().keys())


def resolve_pack_refs(source_ids: list[str]) -> str:
    """Human-readable citation string, e.g. 'hermes (PMID 26898852); dawn (PMID 29129157)'."""
    index = _thrombectomy_item_index()
    parts: list[str] = []
    for sid in source_ids:
        item = index.get(sid)
        if item is None:
            parts.append(sid)
            continue
        ref_bits = []
        if item.pmid:
            ref_bits.append(f"PMID {item.pmid}")
        elif item.doi:
            ref_bits.append(f"DOI {item.doi}")
        parts.append(f"{sid} ({'; '.join(ref_bits)})" if ref_bits else sid)
    return "; ".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prognostic_signs.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add caseprep/prognostic_signs.py tests/test_prognostic_signs.py
git commit -m "feat(prognostic): authored, cited thrombectomy prognostic-sign registry"
```

---

## Task 2: Render the prognostic-signs section in the postop file

**Files:**
- Modify: `caseprep/schema.py` (add `_render_thrombectomy_prognostic_signs`, `_render_thrombectomy_postop`; branch `_render_postop` at line ~2221)
- Test: `tests/test_prognostic_render.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prognostic_render.py
from caseprep.schema import _render_postop


def _thrombectomy_schema() -> dict:
    return {
        "topic": "left MCA thrombectomy",
        "procedure_family": {"id": "endovascular_thrombectomy"},
        "case": {
            "postop_plan": {
                "destination": "Neuro-ICU", "neuro_checks": "q1h",
                "bp_goals": "per attending", "imaging_timing": "24h CT",
                "dvt_prophylaxis": "per protocol",
                "medications": [], "drains_devices": [],
                "labs_monitoring": [], "discharge_criteria": [],
            },
        },
    }


def test_thrombectomy_postop_has_prognostic_section():
    out = _render_postop(_thrombectomy_schema())
    assert "## Prognostic Signs" in out
    assert "Favorable" in out and "Unfavorable" in out
    assert "Successful reperfusion (mTICI 2b-3)" in out
    assert "Low ASPECTS" in out
    # Source ref is rendered (HERMES PMID)
    assert "26898852" in out
    # Existing postop content still renders
    assert "Immediate Postop Orders" in out


def test_non_thrombectomy_postop_has_no_prognostic_section():
    schema = {
        "topic": "ACDF",
        "procedure_family": {"id": "spine_acdf"},
        "case": {"postop_plan": {
            "destination": "floor", "neuro_checks": "q4h", "bp_goals": "normal",
            "imaging_timing": "as needed", "dvt_prophylaxis": "SCDs",
            "medications": [], "drains_devices": [], "labs_monitoring": [],
            "discharge_criteria": [],
        }},
    }
    out = _render_postop(schema)
    assert "Prognostic Signs" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prognostic_render.py -q`
Expected: FAIL — `## Prognostic Signs` not in output (thrombectomy postop not yet branched).

- [ ] **Step 3: Write minimal implementation**

In `caseprep/schema.py`, add these two functions immediately **above** `def _render_postop` (line ~2221). They reuse the existing `prognostic_signs` data when present in the schema, else fall back to the authored registry:

```python
def _render_thrombectomy_prognostic_signs(schema: dict[str, Any]) -> str:
    from caseprep.prognostic_signs import prognostic_signs_for_family, resolve_pack_refs

    block = schema.get("case", {}).get("prognostic_signs")
    if not isinstance(block, dict) or not (block.get("favorable") or block.get("unfavorable")):
        block = prognostic_signs_for_family("endovascular_thrombectomy")
    if not block:
        return ""

    def _rows(entries: list[dict[str, Any]]) -> str:
        if not entries:
            return "| _none_ | |"
        out = []
        for e in entries:
            refs = resolve_pack_refs(list(e.get("source_ids", [])))
            out.append(f"| {_md_cell(e.get('indicator'))} | {_md_cell(e.get('detail'))} | {_md_cell(refs)} |")
        return "\n".join(out)

    return f"""## Prognostic Signs

### Favorable

| Indicator | Why it matters | Source |
|---|---|---|
{_rows(block.get('favorable', []))}

### Unfavorable

| Indicator | Why it matters | Source |
|---|---|---|
{_rows(block.get('unfavorable', []))}"""


def _render_thrombectomy_postop(schema: dict[str, Any]) -> str:
    prognostic = _render_thrombectomy_prognostic_signs(schema)
    body = _render_postop_body(schema)
    return _markdown_sections(f"# Outcome & Postop Plan - {schema['topic']}", prognostic, body)
```

Then refactor the existing `_render_postop` (line ~2221) so its body (everything after the `# Postop Plan` heading) lives in a reusable `_render_postop_body`, and dispatch thrombectomy. Replace:

```python
def _render_postop(schema: dict[str, Any]) -> str:
    return f"""# Postop Plan - {schema["topic"]}

## Immediate Postop Orders
... (existing body) ...
"""
```

with:

```python
def _render_postop(schema: dict[str, Any]) -> str:
    if _is_thrombectomy(schema):
        return _render_thrombectomy_postop(schema)
    return f"""# Postop Plan - {schema["topic"]}

{_render_postop_body(schema)}"""


def _render_postop_body(schema: dict[str, Any]) -> str:
    return f"""## Immediate Postop Orders

- Destination: {_section_scalar(schema, "postop_plan", "destination")}
- Neuro checks: {_section_scalar(schema, "postop_plan", "neuro_checks")}
- BP goals: {_section_scalar(schema, "postop_plan", "bp_goals")}
- Imaging timing: {_section_scalar(schema, "postop_plan", "imaging_timing")}
- DVT prophylaxis: {_section_scalar(schema, "postop_plan", "dvt_prophylaxis")}

## Medications

{_list_block(_section_list(schema, "postop_plan", "medications"))}

## Drains / Devices

{_list_block(_section_list(schema, "postop_plan", "drains_devices"))}

## Labs / Monitoring

{_list_block(_section_list(schema, "postop_plan", "labs_monitoring"))}

## Discharge Criteria

{_list_block(_section_list(schema, "postop_plan", "discharge_criteria"))}"""
```

(Note: `_render_postop_body` no longer carries a trailing blank line; `_render_postop` and `_markdown_sections` add spacing. Keep the body text identical to the original otherwise.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prognostic_render.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the render regression suite**

Run: `uv run pytest tests/ -k "render or postop or markdown" -q`
Expected: PASS (existing postop/render tests still green; if a snapshot asserts the exact `# Postop Plan` heading for thrombectomy, update it to `# Outcome & Postop Plan` — that is the intended change).

- [ ] **Step 6: Commit**

```bash
git add caseprep/schema.py tests/test_prognostic_render.py
git commit -m "feat(render): prognostic-signs section atop the thrombectomy postop file"
```

---

## Task 3: Populate the schema + provenance in the core builder

**Files:**
- Modify: `caseprep/core/builder.py` (add a `_bind_prognostic_signs` helper; call it during core build)
- Test: `tests/test_core_builder_prognostic.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core_builder_prognostic.py
from caseprep.core.builder import _bind_prognostic_signs
from caseprep.core.contracts import ProvenanceRecord


def test_binds_thrombectomy_prognostic_signs_with_provenance():
    schema = {"procedure_family": {"id": "endovascular_thrombectomy"}, "case": {}}
    provenance: list[ProvenanceRecord] = []
    _bind_prognostic_signs(schema, provenance)

    block = schema["case"]["prognostic_signs"]
    assert block["favorable"] and block["unfavorable"]

    recs = [r for r in provenance if r.field_path == "case.prognostic_signs"]
    assert len(recs) == 1
    rec = recs[0]
    assert rec.value_status == "generated"
    assert rec.generated_by == "caseprep.prognostic_signs"
    assert "hermes" in rec.source_ids  # union of cited pack ids


def test_no_binding_for_non_thrombectomy():
    schema = {"procedure_family": {"id": "spine_acdf"}, "case": {}}
    provenance: list[ProvenanceRecord] = []
    _bind_prognostic_signs(schema, provenance)
    assert "prognostic_signs" not in schema["case"]
    assert provenance == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_core_builder_prognostic.py -q`
Expected: FAIL — `cannot import name '_bind_prognostic_signs'`.

- [ ] **Step 3: Write minimal implementation**

In `caseprep/core/builder.py`, add the import near the other `caseprep` imports (top of file):

```python
from caseprep.prognostic_signs import prognostic_signs_for_family
```

Confirm `ProvenanceRecord` is importable in this module (it is used via `caseprep.core.contracts`); if not already imported, add:

```python
from caseprep.core.contracts import ProvenanceRecord
```

Add the helper (place it near the other `_bind_*` / artifact helpers):

```python
def _bind_prognostic_signs(schema: dict[str, Any], provenance: list[ProvenanceRecord]) -> None:
    """Attach the authored prognostic-signs block + provenance for supported families."""
    family_id = ""
    fam = schema.get("procedure_family")
    if isinstance(fam, dict):
        family_id = str(fam.get("id") or "")
    block = prognostic_signs_for_family(family_id)
    if not block:
        return
    schema.setdefault("case", {})["prognostic_signs"] = block
    source_ids: list[str] = []
    for group in ("favorable", "unfavorable"):
        for entry in block.get(group, []):
            for sid in entry.get("source_ids", []):
                if sid not in source_ids:
                    source_ids.append(sid)
    provenance.append(ProvenanceRecord(
        field_path="case.prognostic_signs",
        source_ids=source_ids,
        value_status="generated",
        generated_by="caseprep.prognostic_signs",
        notes="Authored favorable/unfavorable outcome indicators cited to thrombectomy evidence-pack items.",
    ))
```

Then call it during the core build. Find where `_write_core_artifacts` (or the build function that renders files) assembles `provenance` and the `schema`, and insert — **before** `render_caseprep_files` is invoked — a guarded call:

```python
    try:
        _bind_prognostic_signs(schema, provenance)
    except Exception as exc:  # never block the briefing on prognostic binding
        warnings.append(f"Prognostic signs: {exc}")
```

(Use the existing `warnings` list in that scope. If `provenance` there is typed `list[Any]`, the call is still valid.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_core_builder_prognostic.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add caseprep/core/builder.py tests/test_core_builder_prognostic.py
git commit -m "feat(core): populate prognostic_signs schema block + provenance for thrombectomy"
```

---

## Task 4: Source-coverage audit in the rubric

**Files:**
- Modify: `caseprep/evaluation/rubric.py` (add registries + `check_source_coverage`; call it in `evaluate_case_output` at line ~89)
- Test: `tests/test_source_coverage_audit.py`

The audit checks the **rendered markdown** for the prognostic section: every favorable/unfavorable indicator line must carry a citation token, and a `needs synthesis` in a sourceable area where the evidence pack has sources fails. Patient-data `needs input` markers are exempt.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_source_coverage_audit.py
from caseprep.evaluation.rubric import check_source_coverage

FAMILY = "endovascular_thrombectomy"


def _schema(family=FAMILY):
    return {"procedure_family": {"id": family}}


def test_uncited_prognostic_section_fails():
    md = (
        "## Prognostic Signs\n\n### Favorable\n"
        "| Indicator | Why | Source |\n|---|---|---|\n"
        "| Successful reperfusion | matters | |\n"  # no citation
    )
    failures = check_source_coverage(_schema(), md)
    assert any("prognostic" in f.lower() for f in failures)


def test_cited_prognostic_section_passes():
    md = (
        "## Prognostic Signs\n\n### Favorable\n"
        "| Indicator | Why | Source |\n|---|---|---|\n"
        "| Successful reperfusion | matters | hermes (PMID 26898852) |\n"
    )
    assert check_source_coverage(_schema(), md) == []


def test_needs_synthesis_in_sourceable_area_fails():
    md = "## Prognostic Signs\n\nneeds synthesis\n"
    failures = check_source_coverage(_schema(), md)
    assert any("needs synthesis" in f.lower() for f in failures)


def test_patient_data_needs_input_is_exempt():
    md = (
        "## Prognostic Signs\n\n### Favorable\n"
        "| Indicator | Why | Source |\n|---|---|---|\n"
        "| Reperfusion | matters | hermes (PMID 26898852) |\n\n"
        "## Imaging\nASPECTS: incomplete/needs input\n"
    )
    assert check_source_coverage(_schema(), md) == []


def test_non_thrombectomy_family_is_noop():
    assert check_source_coverage(_schema("spine_acdf"), "anything") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_source_coverage_audit.py -q`
Expected: FAIL — `cannot import name 'check_source_coverage'`.

- [ ] **Step 3: Write minimal implementation**

In `caseprep/evaluation/rubric.py`, add near the top-level constants (after `PLACEHOLDER_PATTERNS`):

```python
import re as _re  # rubric already imports re; reuse the module-level one if present

# Family-keyed registries so later cycles register entries without changing logic.
# Each value is a set of markdown section headings whose indicator rows must be cited.
SOURCEABLE_SECTIONS: dict[str, tuple[str, ...]] = {
    "endovascular_thrombectomy": ("## Prognostic Signs",),
}

# needs-synthesis is never legitimate in a sourceable area; needs-input MAY be a
# patient-data placeholder and is exempt unless it is a bare unqualified marker.
_NEEDS_SYNTHESIS = re.compile(r"needs\s+synthesis", re.IGNORECASE)
# A markdown table row whose last cell (the Source column) is empty.
_UNCITED_ROW = re.compile(r"^\|[^|]+\|[^|]+\|\s*\|\s*$")
# Heading/separator rows to skip.
_TABLE_NONDATA = re.compile(r"^\|\s*(indicator|---)", re.IGNORECASE)


def _family_id_from_schema(schema: dict[str, Any]) -> str:
    fam = schema.get("procedure_family")
    if isinstance(fam, dict) and fam.get("id"):
        return str(fam["id"])
    return ""


def check_source_coverage(schema: dict[str, Any], markdown_text: str) -> list[str]:
    """Fail when a sourceable clinical claim is left uncited (family-keyed)."""
    family = _family_id_from_schema(schema)
    sections = SOURCEABLE_SECTIONS.get(family)
    if not sections:
        return []
    failures: list[str] = []

    # 1) needs-synthesis anywhere in the doc is a sourceable-area failure.
    if _NEEDS_SYNTHESIS.search(markdown_text):
        failures.append("source-coverage: 'needs synthesis' found where evidence is expected")

    # 2) Within each registered sourceable section, every data table row must cite.
    lines = markdown_text.splitlines()
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = any(stripped == s for s in sections)
            continue
        if not in_section:
            continue
        if _TABLE_NONDATA.match(stripped):
            continue
        if _UNCITED_ROW.match(stripped):
            failures.append(f"source-coverage: uncited prognostic row -> {stripped}")
    return failures
```

(If `re` is already imported at the top of `rubric.py` — it is — drop the `import re as _re` line; it is shown only to make the dependency explicit. Use the existing module-level `re`.)

Then wire it into `evaluate_case_output` (line ~89). After `markdown_text = _read_markdown_text(output_dir)` and where `failures` is being assembled, add:

```python
    failures.extend(check_source_coverage(schema, markdown_text))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_source_coverage_audit.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add caseprep/evaluation/rubric.py tests/test_source_coverage_audit.py
git commit -m "feat(eval): deterministic source-coverage audit for prognostic claims"
```

---

## Task 5: Integration — eval passes with the block; README roadmap note

**Files:**
- Test: `tests/test_source_coverage_audit.py` (add an end-to-end render→audit case)
- Modify: `README.md`

- [ ] **Step 1: Write the failing end-to-end test**

```python
# append to tests/test_source_coverage_audit.py
from caseprep.schema import _render_postop


def test_rendered_thrombectomy_postop_passes_audit():
    schema = {
        "topic": "left MCA thrombectomy",
        "procedure_family": {"id": "endovascular_thrombectomy"},
        "case": {"postop_plan": {
            "destination": "Neuro-ICU", "neuro_checks": "q1h", "bp_goals": "x",
            "imaging_timing": "24h", "dvt_prophylaxis": "x",
            "medications": [], "drains_devices": [], "labs_monitoring": [],
            "discharge_criteria": [],
        }},
    }
    md = _render_postop(schema)
    assert check_source_coverage(schema, md) == []  # real render is fully cited
```

- [ ] **Step 2: Run it to verify it passes immediately**

Run: `uv run pytest tests/test_source_coverage_audit.py::test_rendered_thrombectomy_postop_passes_audit -q`
Expected: PASS — the real rendered prognostic table cites every row, so the audit returns no failures. (If it fails, the render in Task 2 left a row's Source cell empty — fix the render, not the test.)

- [ ] **Step 3: Update the README program roadmap**

In `README.md`, under the image-bank "Next — briefing clinical-content completeness" section, mark Cycle 1 in progress. Replace the bullet:

```
1. **Add a `prognostic_signs` schema block** (favorable / unfavorable outcome
   indicators) — currently not modeled.
```

with:

```
1. **`prognostic_signs` schema block — in progress (Cycle 1).** Favorable /
   unfavorable outcome indicators, authored and cited to landmark thrombectomy
   trials, rendered atop the postop file, with a deterministic source-coverage
   audit (`check_source_coverage`) that fails the canonical eval on uncited
   prognostic claims. Design:
   `docs/superpowers/specs/2026-05-30-thrombectomy-briefing-completeness-design.md`.
```

- [ ] **Step 4: Run the full feature suite**

Run: `uv run pytest tests/test_prognostic_signs.py tests/test_prognostic_render.py tests/test_core_builder_prognostic.py tests/test_source_coverage_audit.py -q`
Expected: PASS (all feature tests green).

- [ ] **Step 5: Commit**

```bash
git add tests/test_source_coverage_audit.py README.md
git commit -m "test(eval): e2e prognostic render passes source-coverage audit; README roadmap"
```

---

## Final verification (run after all tasks)

- [ ] Run the broader regression: `uv run pytest -q` (full suite is slow — many network-mocked tests; let it complete). Expected: green except pre-existing unrelated slowness. Fix any test that asserted the old thrombectomy postop heading.
- [ ] Confirm a thrombectomy `caseprep.yaml` produced via the core build contains `case.prognostic_signs` and `provenance.json` contains the `case.prognostic_signs` record.

## Notes for the implementer

- **Scope of the audit (Cycle 1):** `SOURCEABLE_SECTIONS` registers only `## Prognostic Signs` for thrombectomy. Extending the audit to require citations on `risk_and_rescue` bullets is a deliberate fast-follow (it would require citing existing authored bullets) and is **out of scope** here — keep the registry to the prognostic section so the canonical eval stays green.
- **Family-agnostic by construction:** Later cycles add a family to `_FAMILY_PROGNOSTIC_SIGNS` (Task 1) and `SOURCEABLE_SECTIONS` (Task 4); no logic changes.
- **No file renumbering:** the prognostic section renders inside the existing `06-postop-plan.md`; `MAJOR_MARKDOWN_FILES` in the rubric is unchanged.
