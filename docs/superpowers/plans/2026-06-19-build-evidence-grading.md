# Build Evidence Grading Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Build's overly-broad "needs verification" bucket with a more informative evidence taxonomy (BACKLOG P2 #5): **directly supported**, **multi-source supported**, **standard practice (weakly cited)**, **attending preference**, **conflicting evidence**, **unsupported / quarantined** — derived from signals already present at grading time (audit_status, #accepted sources, whether a citation resolved, contradiction data, attending-preference provenance).

**Architecture:** A **pure, hermetically-testable** classifier `neuro_caseboard/evidence_grade.py` maps a small `GradeSignals` struct to a fine-grained category, plus `summary_bucket(category)` collapsing each category back to the existing 3-way (`supported`/`to_verify`/`quarantined`) so `EvidenceSummary` invariants are preserved. `compile.py` builds `GradeSignals` per card from data it already has (`audit_status`, `len(accepted_papers(c))`, whether `[n]` marks resolved) and records the fine category on `Claim` (new optional field, default keeps current behavior). Renderers surface the fine label without changing color/marker semantics (category→existing status drives the marker).

**Tech Stack:** Python 3.10+, dataclasses, pytest. Hermetic tests — the classifier is pure; compile-path tests use the existing card fixtures pattern.

## Global Constraints

- Loop harness (must exit 0): `python3 -m pytest -p no:cacheprovider -q tests/test_build_evidence_grading.py`. Full suite ~17min on WSL2; CI runs the full suite.
- **Backwards-compatible**: the existing `EvidenceSummary` counts (supported / to_verify / quarantined) and the supported/verify marker semantics must not regress. The new category is additive (`summary_bucket` maps each new category onto exactly one existing bucket).
- Do not break the `_STATUS`/`claim.status` contract the renderers consume; add `claim.grade` alongside `claim.status`.
- Tests hermetic: drive the classifier with explicit `GradeSignals`; for the compile wiring, reuse the existing `AuditedCard`/`_compile` test fixtures (see `tests/test_build_source_attribution.py` for the constructor shape — `AuditedCard(..., compiler_slot="")`).
- Verified facts: grading at `neuro_caseboard/compile.py:121-168`; `_PRIMARY={"supported","needs_review","no_evidence"}`, `_STATUS={"supported":"supported","needs_review":"verify","no_evidence":"verify"}`; `accepted_papers(c)` returns accepted supporting papers; `should_cite(snippet, hypothesis, v)` gates `[n]`; `EvidenceSummary(supported,to_verify,quarantined)` at `model.py:61-67`; `Claim` at `model.py:34` has `status` (and other fields).

---

## Tasks (project-loop step cursor)

- [x] Task 1: Pure evidence-grade classifier (`neuro_caseboard/evidence_grade.py`) + hermetic unit tests
- [x] Task 2: Wire fine categories into `compile.py` (build `GradeSignals`, set `Claim.grade`) + summary-invariant test

---

### Task 1: Pure evidence-grade classifier + hermetic unit tests

**Files:**
- Create: `neuro_caseboard/evidence_grade.py`
- Create (Test): `tests/test_build_evidence_grading.py`

**Interfaces:**
- Produces:
  - `GradeSignals(audit_status: str, n_sources: int = 0, cited: bool = False, has_conflict: bool = False, is_preference: bool = False)` — frozen dataclass.
  - `GRADES: tuple[str,...]` = the 6 category keys.
  - `GRADE_LABEL: dict[str,str]` — human labels.
  - `grade(sig: GradeSignals) -> str` — precedence rule (below).
  - `summary_bucket(category: str) -> str` — `"supported"` | `"to_verify"` | `"quarantined"`.
- Consumes: nothing.

**Category keys / labels:**
- `directly-supported` → "Directly supported"
- `multi-source` → "Supported by multiple sources"
- `standard-practice` → "Standard practice (weakly cited)"
- `attending-preference` → "Attending preference"
- `conflicting` → "Conflicting evidence"
- `unsupported` → "Unsupported or quarantined"

**Precedence rule (`grade`):**
1. `audit_status == "off_target"` → `unsupported`
2. `has_conflict` → `conflicting`
3. `is_preference` → `attending-preference`
4. `audit_status == "supported"` and `n_sources >= 2` → `multi-source`
5. `audit_status == "supported"` (n_sources ≤ 1) → `directly-supported`
6. `audit_status == "needs_review"` → `standard-practice`
7. else (`no_evidence`, uncited) → `unsupported`

**`summary_bucket`:** `{directly-supported, multi-source} → supported`; `{standard-practice, attending-preference, conflicting} → to_verify`; `{unsupported} → quarantined` **only if off_target, else to_verify** — to preserve the existing invariant (`quarantined == off_target` count), `summary_bucket` takes the category AND needs the off_target distinction; simplest: map `unsupported` → `to_verify` and let compile.py count quarantined by `audit_status == "off_target"` as it already does. So `summary_bucket("unsupported") == "to_verify"`; quarantined accounting stays in compile.py unchanged.

**Step 1: Write the failing test** — create `tests/test_build_evidence_grading.py`:

```python
"""Hermetic unit tests for Build evidence-grade refinement (neuro_caseboard/evidence_grade.py),
BACKLOG P2 #5. Pure classification — no corpus/LLM/network."""
from neuro_caseboard.evidence_grade import (GradeSignals, grade, summary_bucket,
                                            GRADES, GRADE_LABEL)


def test_grade_directly_vs_multi_source():
    assert grade(GradeSignals("supported", n_sources=1, cited=True)) == "directly-supported"
    assert grade(GradeSignals("supported", n_sources=3, cited=True)) == "multi-source"


def test_grade_standard_practice_for_needs_review():
    assert grade(GradeSignals("needs_review")) == "standard-practice"


def test_grade_unsupported_for_no_evidence_and_off_target():
    assert grade(GradeSignals("no_evidence")) == "unsupported"
    assert grade(GradeSignals("off_target")) == "unsupported"


def test_conflict_and_preference_take_precedence():
    assert grade(GradeSignals("supported", n_sources=3, has_conflict=True)) == "conflicting"
    assert grade(GradeSignals("supported", n_sources=3, is_preference=True)) == "attending-preference"
    # off_target still wins over conflict/preference (it is quarantined)
    assert grade(GradeSignals("off_target", has_conflict=True)) == "unsupported"


def test_summary_bucket_preserves_three_way_invariant():
    assert summary_bucket("directly-supported") == "supported"
    assert summary_bucket("multi-source") == "supported"
    for c in ("standard-practice", "attending-preference", "conflicting", "unsupported"):
        assert summary_bucket(c) == "to_verify"


def test_grades_and_labels_consistent():
    assert set(GRADES) == set(GRADE_LABEL)
    assert len(GRADES) == 6
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_build_evidence_grading.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'neuro_caseboard.evidence_grade'`.

**Step 3: Write the classifier** — create `neuro_caseboard/evidence_grade.py`:

```python
"""Fine-grained Build evidence grading (BACKLOG P2 #5).

Pure classifier: maps grading signals already available in compile.py to an informative category,
replacing the overly-broad "verify" bucket. ``summary_bucket`` collapses each category back to the
existing 3-way EvidenceSummary so counts/invariants do not regress."""
from __future__ import annotations

from dataclasses import dataclass

GRADE_LABEL = {
    "directly-supported": "Directly supported",
    "multi-source": "Supported by multiple sources",
    "standard-practice": "Standard practice (weakly cited)",
    "attending-preference": "Attending preference",
    "conflicting": "Conflicting evidence",
    "unsupported": "Unsupported or quarantined",
}
GRADES = tuple(GRADE_LABEL)


@dataclass(frozen=True)
class GradeSignals:
    audit_status: str          # supported | needs_review | no_evidence | off_target
    n_sources: int = 0         # # accepted supporting papers
    cited: bool = False        # at least one [n] citation resolved
    has_conflict: bool = False # contradicting evidence present
    is_preference: bool = False  # attending/operative preference provenance


def grade(sig: GradeSignals) -> str:
    if sig.audit_status == "off_target":
        return "unsupported"
    if sig.has_conflict:
        return "conflicting"
    if sig.is_preference:
        return "attending-preference"
    if sig.audit_status == "supported":
        return "multi-source" if sig.n_sources >= 2 else "directly-supported"
    if sig.audit_status == "needs_review":
        return "standard-practice"
    return "unsupported"


def summary_bucket(category: str) -> str:
    if category in ("directly-supported", "multi-source"):
        return "supported"
    return "to_verify"
```

**Step 4: Run to verify it passes**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_build_evidence_grading.py`
Expected: PASS — 6 passed.

**Step 5: Commit**

```bash
git add neuro_caseboard/evidence_grade.py tests/test_build_evidence_grading.py
git commit -m "loop step 0: pure Build evidence-grade classifier + hermetic tests (P2 #5)"
```

---

### Task 2: Wire fine categories into compile.py + summary-invariant test

**Files:**
- Modify: `neuro_caseboard/model.py` (add `grade: str = ""` to `Claim`)
- Modify: `neuro_caseboard/compile.py` (build `GradeSignals`, set `claim.grade`)
- Modify (Test): `tests/test_build_evidence_grading.py` (append a `_compile` test asserting fine grades + unchanged EvidenceSummary)

**Interfaces:**
- Consumes: `GradeSignals`, `grade` from Task 1; `accepted_papers(c)`.
- Produces: `Claim.grade` populated; `EvidenceSummary` unchanged.

**Edits:**

1. `model.py` `Claim`: add field `grade: str = ""` (additive; renderers ignore it unless updated).

2. `compile.py` — where `claim.status` is set (after the inline-citation block, before `claims.append(claim)` at ~line 168), derive and attach the fine grade:

```python
            from neuro_caseboard.evidence_grade import GradeSignals, grade as _grade
            claim.grade = _grade(GradeSignals(
                audit_status=c.audit_status,
                n_sources=len(accepted_papers(c)),
                cited=bool(claim.text.endswith("]")),
            ))
            claims.append(claim)
```

(Conflict/preference signals are left at their defaults for now — they require provenance not yet threaded through cards; the classifier already supports them so they light up once wired. `claim.status` and `EvidenceSummary` are untouched, so existing renderers/counts are unaffected.)

**Step 1: Write the failing test (append to `tests/test_build_evidence_grading.py`)**

```python
def test_compile_sets_fine_grade_and_preserves_summary():
    """_compile attaches a fine grade per claim without changing the 3-way EvidenceSummary.
    Hermetic: in-memory AuditedCards, no corpus/LLM/network."""
    from caseprep.audit.card_auditor import AuditedCard
    from neuro_caseboard.compile import _compile

    cards = [
        AuditedCard(question="Approach is via a retrosigmoid craniotomy?",
                    why_it_matters="", section_key="approach", target_file="approach.md",
                    audit_status="supported", audit_reason="", compiler_slot=""),
        AuditedCard(question="Routinely give prophylactic antibiotics?",
                    why_it_matters="", section_key="prep", target_file="prep.md",
                    audit_status="needs_review", audit_reason="", compiler_slot=""),
    ]
    dossier = _compile("vestibular schwannoma", cards, {}, {}, {}, {}, {}, corpus_inline=False)
    grades = [cl.grade for s in dossier.sections for cl in s.claims]
    assert "directly-supported" in grades
    assert "standard-practice" in grades
    # supported counts unchanged: exactly one corpus-supported card
    assert dossier.evidence.supported == 1
```

> Note: confirm `_compile`'s exact signature during wiring (args for headings/intros/order/etc may differ) — adapt the call to the real signature; the load-bearing assertions are (a) fine grades populated and (b) `evidence.supported` unchanged. See `tests/test_build_source_attribution.py` for the canonical `_compile` invocation.

**Step 2: Run to verify it fails**, **Step 3: apply edits**, **Step 4: run full harness** (expect 7 passed), **Step 5: commit**:

```bash
git add neuro_caseboard/model.py neuro_caseboard/compile.py tests/test_build_evidence_grading.py
git commit -m "loop step 1: attach fine evidence grade per claim in compile (P2 #5)"
```

---

## Self-Review

**1. Spec coverage:** the 6 requested categories exist (`GRADES`/`GRADE_LABEL`); `grade` derives them; the broad "verify" is split (directly-supported/multi-source vs standard-practice vs conflicting vs attending-preference vs unsupported). `summary_bucket` + untouched compile counting preserve the existing summary. ✔
**2. Placeholder scan:** classifier fully coded; compile edit shown; `_compile` call flagged to confirm signature (with the canonical reference test). ✔
**3. Type consistency:** `GradeSignals`/`grade`/`summary_bucket`/`GRADES`/`GRADE_LABEL` identical across module, tests, compile call site; `Claim.grade: str`. ✔

> Follow-up (not this PR): thread conflict (`contradicting_paper_ids`) and attending-preference provenance into `GradeSignals`, and surface `GRADE_LABEL` in the renderers (render_md/render_pdf/exec_navy/caseboard_pdf) + web. The classifier already supports both signals; this PR lands the taxonomy + per-claim grade without renderer churn.
