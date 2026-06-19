# Ask Claim-Level Confidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Ask answers per-claim confidence/evidence status (BACKLOG P2 #4), mirroring Build's supported/needs-verification machinery: each claim is labelled **consensus** (multi-source textbook), **single-source**, **conflict** (cites a contradicting source), **literature-only** (PubMed lane only), or **unsupported** (no citation — explicit "not found", never filled in).

**Architecture:** The grading signal already exists in the synthesized answer: inline `[n]` markers tie each sentence to numbered sources, and a number's lane (textbook vs literature) is known from which citation list it indexes. So the core is a **pure function** `grade_answer(answer, source_lane, *, conflicting=frozenset()) -> list[ClaimConfidence]` — split into claims, read cited numbers per claim, classify — with no LLM/corpus/network. A small status→label/marker map mirrors `neuro_caseboard/model.MARK`. The Streamlit Ask lane then renders each claim with its marker, plus a one-line evidence summary.

**Tech Stack:** Python 3.10+, dataclasses, `re` for sentence/marker parsing, Streamlit (render only), pytest. Hermetic tests — the grader is pure; the app test stubs the engine.

## Global Constraints

- Loop harness (must exit 0): `python3 -m pytest -p no:cacheprovider -q tests/test_ask_claim_confidence.py`. Full suite ~17min on WSL2 — inner loop scoped to this file; CI runs the full suite.
- The grader is **pure and additive** (new module); do NOT change engine answer synthesis in `neuro_core/`/`neuro_caseboard/qa.py`. Wiring is app-layer (`app/streamlit_app.py`) + the new module.
- Preserve explicit "not found": a claim with no citations is `unsupported` and must stay visible as such — never silently dropped or upgraded.
- `app/` is a bare-import script dir; new app helpers import bare. Streamlit AppTest must be guarded with `pytest.importorskip("streamlit")` (web extra absent in required `.[dev]` CI aborts collection otherwise).
- Reuse existing status vocabulary where sensible (`model.MARK` = {supported ✓, verify ⚠}); new statuses get their own markers in the new module (don't mutate `model.py`).
- Verified facts: `QAResult(answer:str, citations:list, figures:list, literature:LiteratureSection|None)` (`neuro_caseboard/qa.py:34`); answer carries inline `[n]` markers; textbook sources = `result.citations`, literature sources = `result.literature.citations`; Ask lane renders at `app/streamlit_app.py` (Ask branch).

---

## Tasks (project-loop step cursor)

- [x] Task 1: Pure claim-confidence grader (`app/ask_confidence.py`) + hermetic unit tests
- [x] Task 2: Render per-claim markers + evidence summary in the Ask lane (`app/streamlit_app.py`) + AppTest

---

### Task 1: Pure claim-confidence grader + hermetic unit tests

**Files:**
- Create: `app/ask_confidence.py`
- Create (Test): `tests/test_ask_claim_confidence.py`

**Interfaces:**
- Produces:
  - `STATUS_LABEL: dict[str,str]` and `STATUS_MARK: dict[str,str]` for the 5 statuses (`consensus`, `single-source`, `conflict`, `literature-only`, `unsupported`).
  - `ClaimConfidence(text: str, status: str, sources: tuple[int, ...])` — dataclass.
  - `split_claims(answer: str) -> list[str]` — sentence split that keeps trailing `[n]` markers with their sentence.
  - `cited_sources(claim: str) -> tuple[int, ...]` — ordered unique `[n]` numbers in a claim.
  - `classify(sources: tuple[int,...], source_lane: dict[int,str], conflicting: frozenset[int]) -> str` — the 5-way rule.
  - `grade_answer(answer: str, source_lane: dict[int,str], *, conflicting: frozenset[int] = frozenset()) -> list[ClaimConfidence]`.
  - `summarize(claims: list[ClaimConfidence]) -> dict[str,int]` — status → count.
- Consumes: nothing.

**Classification rule (in `classify`):**
- no sources → `unsupported`
- any source in `conflicting` → `conflict`
- all sources have lane `"literature"` → `literature-only`
- ≥2 distinct `"textbook"` sources → `consensus`
- else (exactly 1 textbook source, possibly + literature) → `single-source`

**Step 1: Write the failing test** — create `tests/test_ask_claim_confidence.py`:

```python
"""Hermetic unit tests for Ask claim-level confidence (app/ask_confidence.py), BACKLOG P2 #4.

Pure parsing/classification — no Streamlit, engine, corpus, LLM, or network. `app/` is a
bare-import script dir, so we put it on sys.path."""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from ask_confidence import (ClaimConfidence, split_claims, cited_sources,  # noqa: E402
                            classify, grade_answer, summarize, STATUS_LABEL, STATUS_MARK)

TEXTBOOK = "textbook"
LIT = "literature"


def test_cited_sources_extracts_ordered_unique_markers():
    assert cited_sources("The PICA supplies the lateral medulla [1][2].") == (1, 2)
    assert cited_sources("No citation here.") == ()
    assert cited_sources("Repeated [3] then again [3].") == (3,)


def test_split_claims_keeps_markers_with_their_sentence():
    claims = split_claims("First fact [1]. Second fact [2][3]. Third has none.")
    assert len(claims) == 3
    assert "[1]" in claims[0] and "[2][3]" in claims[1]


def test_classify_five_way_rule():
    lane = {1: TEXTBOOK, 2: TEXTBOOK, 3: LIT}
    assert classify((), lane, frozenset()) == "unsupported"
    assert classify((1, 2), lane, frozenset()) == "consensus"
    assert classify((1,), lane, frozenset()) == "single-source"
    assert classify((3,), lane, frozenset()) == "literature-only"
    assert classify((1, 3), lane, frozenset()) == "single-source"   # 1 textbook + lit
    assert classify((1, 2), lane, frozenset({2})) == "conflict"     # conflict wins


def test_grade_answer_labels_each_claim_and_preserves_not_found():
    answer = ("PICA supplies the lateral medulla [1][2]. "
              "Recent trials favor early surgery [3]. "
              "Some surgeons prefer a lateral approach.")
    lane = {1: TEXTBOOK, 2: TEXTBOOK, 3: LIT}
    claims = grade_answer(answer, lane)
    assert [c.status for c in claims] == ["consensus", "literature-only", "unsupported"]
    assert claims[0].sources == (1, 2)
    # explicit not-found preserved (still present, labelled unsupported)
    assert claims[2].text.strip().startswith("Some surgeons")


def test_summarize_counts_by_status():
    claims = [ClaimConfidence("a", "consensus", (1, 2)),
              ClaimConfidence("b", "unsupported", ())]
    assert summarize(claims) == {"consensus": 1, "unsupported": 1}


def test_status_label_and_mark_cover_all_five_statuses():
    for s in ("consensus", "single-source", "conflict", "literature-only", "unsupported"):
        assert s in STATUS_LABEL and s in STATUS_MARK
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_ask_claim_confidence.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ask_confidence'`.

**Step 3: Write the grader** — create `app/ask_confidence.py`:

```python
"""Per-claim confidence for Ask answers (BACKLOG P2 #4).

Pure parsing/classification over the synthesized answer's inline ``[n]`` citation markers, so the
logic is unit-testable without Streamlit/engine/network. The Ask lane renders the result; the app
builds ``source_lane`` from result.citations (textbook) vs result.literature.citations (literature)."""
from __future__ import annotations

import re
from dataclasses import dataclass

STATUS_LABEL = {
    "consensus": "multi-source consensus",
    "single-source": "single source",
    "conflict": "source conflict",
    "literature-only": "literature only",
    "unsupported": "not found in corpus",
}
STATUS_MARK = {
    "consensus": "✓✓",
    "single-source": "✓",
    "conflict": "⚠",
    "literature-only": "≈",
    "unsupported": "∅",
}

_MARKER = re.compile(r"\[(\d+)\]")
# split after sentence-ending punctuation that may be followed by citation markers
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


@dataclass
class ClaimConfidence:
    text: str
    status: str
    sources: tuple[int, ...]


def cited_sources(claim: str) -> tuple[int, ...]:
    seen: list[int] = []
    for m in _MARKER.finditer(claim):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return tuple(seen)


def split_claims(answer: str) -> list[str]:
    return [c for c in (s.strip() for s in _SENT.split(answer.strip())) if c]


def classify(sources, source_lane, conflicting) -> str:
    if not sources:
        return "unsupported"
    if any(s in conflicting for s in sources):
        return "conflict"
    lanes = [source_lane.get(s, "textbook") for s in sources]
    if all(ln == "literature" for ln in lanes):
        return "literature-only"
    n_textbook = sum(1 for ln in lanes if ln == "textbook")
    return "consensus" if n_textbook >= 2 else "single-source"


def grade_answer(answer: str, source_lane, *, conflicting=frozenset()) -> list[ClaimConfidence]:
    out = []
    for claim in split_claims(answer):
        srcs = cited_sources(claim)
        out.append(ClaimConfidence(text=claim, status=classify(srcs, source_lane, conflicting),
                                   sources=srcs))
    return out


def summarize(claims) -> dict:
    counts: dict = {}
    for c in claims:
        counts[c.status] = counts.get(c.status, 0) + 1
    return counts
```

**Step 4: Run to verify it passes**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_ask_claim_confidence.py`
Expected: PASS — 6 passed.

**Step 5: Commit**

```bash
git add app/ask_confidence.py tests/test_ask_claim_confidence.py
git commit -m "loop step 0: pure Ask claim-confidence grader + hermetic tests (P2 #4)"
```

---

### Task 2: Render per-claim markers + evidence summary in the Ask lane

**Files:**
- Modify: `app/streamlit_app.py` (Ask lane: build `source_lane`, grade the answer, render markers + summary)
- Modify (Test): `tests/test_ask_claim_confidence.py` (append an AppTest that the graded answer renders, engine stubbed)

**Interfaces:**
- Consumes: `grade_answer`, `summarize`, `STATUS_LABEL`, `STATUS_MARK` from Task 1.
- Produces: nothing new (render wiring).

**Exact edits to `app/streamlit_app.py`:**

1. Bare import near the other app helpers:

```python
from ask_confidence import grade_answer, summarize, STATUS_LABEL, STATUS_MARK
```

2. In the Ask render block (where `st.session_state["ask_result"]` is rendered, just before/after `st.markdown(sig.citation_chips(result.answer), ...)`), build the lane map and render per-claim confidence:

```python
        # Per-claim confidence (BACKLOG P2 #4): textbook sources from result.citations,
        # literature sources from result.literature.citations.
        source_lane = {}
        for c in result.citations:
            source_lane[getattr(c, "n", getattr(c, "source_n", 0))] = "textbook"
        if result.literature and result.literature.citations:
            for c in result.literature.citations:
                source_lane.setdefault(getattr(c, "n", 0), "literature")
        graded = grade_answer(result.answer, source_lane)
        counts = summarize(graded)
        sig.section("Claim confidence", "CONF")
        st.caption(" · ".join(f"{STATUS_MARK[s]} {STATUS_LABEL[s]}: {n}"
                              for s, n in counts.items()))
        for c in graded:
            st.markdown(f"{STATUS_MARK[c.status]} {c.text}")
```

(Keep the existing `citation_chips`/sources/literature/figures rendering; this adds a confidence panel — it does not remove the prose answer.)

**Step 1: Write the failing test (append to `tests/test_ask_claim_confidence.py`)**

```python
def test_ask_lane_renders_claim_confidence(monkeypatch):
    """The Ask lane grades the engine answer and renders per-claim markers + a summary, with no
    exception. Hermetic: engine stubbed, no corpus/LLM/network."""
    import pytest
    pytest.importorskip("streamlit")
    import neuro_caseboard.qa as qa

    class _Cite:
        def __init__(self, n): self.n = n

    class _Res:
        answer = "PICA supplies the lateral medulla [1][2]. Some surgeons prefer a lateral approach."
        citations = [_Cite(1), _Cite(2)]
        figures = []
        literature = None

    monkeypatch.setattr(qa, "answer_question", lambda question, **kw: _Res())

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=30)
    at.session_state["ask_q"] = "blood supply of the lateral medulla"
    at.run()
    assert len(at.exception) == 0
    blob = " ".join(m.value for m in at.markdown)
    assert "consensus" in blob.lower()          # the summary line
    assert "not found in corpus" in blob.lower()  # the unsupported claim is shown, not dropped
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_ask_claim_confidence.py::test_ask_lane_renders_claim_confidence`
Expected: FAIL before wiring (no confidence panel rendered).

**Step 3: Apply the edits above to `app/streamlit_app.py`.**

**Step 4: Run the full harness**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_ask_claim_confidence.py`
Expected: PASS — 7 passed.

**Step 5: Commit**

```bash
git add app/streamlit_app.py tests/test_ask_claim_confidence.py
git commit -m "loop step 1: render per-claim confidence + evidence summary in Ask lane (P2 #4)"
```

---

## Self-Review

**1. Spec coverage:** (a) per-claim status displayed → `grade_answer` + Ask-lane render. (b) distinguish consensus / single-source / conflict / literature-only → `classify` 5-way rule. (c) preserve explicit "not found" → `unsupported` status, claim still rendered (asserted in tests). ✔
**2. Placeholder scan:** all steps have runnable code/commands + expected output; the Ask-lane edit references the existing render block (already present), not new prose. ✔
**3. Type consistency:** `ClaimConfidence(text,status,sources)`, `grade_answer`/`classify`/`summarize`/`STATUS_LABEL`/`STATUS_MARK` signatures identical across module, tests, and app call sites. `source_lane: dict[int,str]`, `conflicting: frozenset[int]` consistent. ✔

> Open implementation note (resolve at wiring): citation objects' source-number attribute — textbook `result.citations` items and literature `result.literature.citations` items may name it `n` vs `source_n`. The wiring uses `getattr(c,"n",getattr(c,"source_n",0))`; confirm the real attribute during Task 2 and pin it. The load-bearing assertions are status labels + that unsupported claims stay visible.
