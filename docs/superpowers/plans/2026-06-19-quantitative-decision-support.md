# Quantitative Decision Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the numbers a surgeon needs to compare options (BACKLOG P2 #6). Extract quantitative metrics already present in a grounded answer — success/occlusion rates, complication/retreatment rates, follow-up durations, denominators (`n=`), confidence intervals, p-values, decision thresholds — into a structured **"By the numbers"** panel, and **flag comparative claims that assert a comparison without a number** (preserving explicit "not found" rather than inventing figures).

**Architecture:** A **pure, hermetically-testable** extractor `app/quant_support.py` over the answer text (regex/parse only — no LLM/corpus/network), mirroring `app/ask_confidence.py`. The Ask lane renders the panel beneath the existing answer + claim-confidence panel. No engine change — we surface numbers the synthesis already produced; we never fabricate.

**Tech Stack:** Python 3.10+, `re`, dataclasses, Streamlit (render only), pytest. Hermetic tests.

## Global Constraints

- Loop harness (must exit 0): `python3 -m pytest -p no:cacheprovider -q tests/test_quant_support.py`. Full suite ~17min on WSL2; CI runs the full suite.
- Pure + additive: new module + app-layer render; do NOT change engine synthesis. **Never fabricate numbers** — only extract spans literally present in the answer.
- `app/` bare-import script dir; AppTest guarded with `pytest.importorskip("streamlit")`; post-`sys.path` imports get `# noqa: E402`.
- Preserve explicit not-found: if the answer has no metrics, the panel says so (no invented data); comparative-but-unquantified claims are surfaced as a caution, not silently passed.
- Verified facts: Ask render block builds on `result.answer` at `app/streamlit_app.py:107`; the confidence panel pattern (`grade_answer`) is the sibling to mirror.

---

## Tasks (project-loop step cursor)

- [x] Task 1: Pure quantitative extractor (`app/quant_support.py`) + hermetic unit tests
- [x] Task 2: Render "By the numbers" + unquantified-comparison caution in the Ask lane + AppTest

---

### Task 1: Pure quantitative extractor + hermetic unit tests

**Files:**
- Create: `app/quant_support.py`
- Create (Test): `tests/test_quant_support.py`

**Interfaces:**
- Produces:
  - `Metric(clause: str, value: str, kind: str)` — a detected numeric span + the sentence it sits in; `kind ∈ {"percent","count","interval","pvalue","duration","ratio"}`.
  - `METRIC_PATTERNS: list[tuple[str, re.Pattern]]` — ordered (kind, pattern).
  - `extract_metrics(text: str) -> list[Metric]` — one Metric per (sentence, matched value), de-duplicated, source-order.
  - `has_quantitative_support(text: str) -> bool`.
  - `unquantified_comparisons(text: str) -> list[str]` — sentences with comparative language (`better|worse|higher|lower|superior|inferior|more|less|greater|reduc|increas|improv` …) that contain **no** metric.
  - `summarize(metrics: list[Metric]) -> dict[str,int]` — kind → count.
- Consumes: nothing.

**Patterns (kind → regex, first-match wins per sentence-value):**
- `percent`: `\b\d{1,3}(?:\.\d+)?\s?%`
- `count`: `\bn\s?=\s?\d+\b`
- `interval`: `\b\d{1,3}(?:\.\d+)?\s?%?\s?CI\b` or `95\s?%\s?CI`
- `pvalue`: `\bp\s?[<>=]\s?0?\.\d+\b`
- `duration`: `\b\d+(?:\.\d+)?\s?(?:day|week|month|year)s?\b`
- `ratio`: `\b\d+(?:\.\d+)?\s?(?:to|–|-|/)\s?\d+(?:\.\d+)?\b` (e.g. "2 to 1", "1.5–3")

**Step 1: Write the failing test** — create `tests/test_quant_support.py`:

```python
"""Hermetic unit tests for Ask quantitative-support extraction (app/quant_support.py), BACKLOG P2 #6.

Pure regex/parse — no Streamlit, engine, corpus, LLM, or network. `app/` is a bare-import script dir."""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from quant_support import (Metric, extract_metrics, has_quantitative_support,  # noqa: E402
                          unquantified_comparisons, summarize)


def test_extracts_percentages_counts_and_pvalues():
    text = ("Complete occlusion was achieved in 85% of patients (n=240). "
            "Retreatment occurred in 7.5% at 12 months. "
            "The difference was significant (p<0.01).")
    kinds = {m.kind for m in extract_metrics(text)}
    assert {"percent", "count", "pvalue", "duration"} <= kinds


def test_has_quantitative_support_true_and_false():
    assert has_quantitative_support("Mortality was 2.1%.") is True
    assert has_quantitative_support("This approach is generally preferred.") is False


def test_metric_carries_its_clause_and_value():
    [m] = [x for x in extract_metrics("Occlusion in 90% of cases.") if x.kind == "percent"]
    assert "90%" in m.value
    assert "Occlusion" in m.clause


def test_unquantified_comparison_is_flagged_only_without_numbers():
    text = ("Flow diverters achieve higher occlusion than coiling. "
            "Coiling has a 5% complication rate.")
    flags = unquantified_comparisons(text)
    assert any("higher occlusion" in f for f in flags)        # comparative, no number -> flagged
    assert all("5% complication" not in f for f in flags)     # quantified -> not flagged


def test_summarize_counts_by_kind():
    metrics = [Metric("a", "85%", "percent"), Metric("b", "n=10", "count"),
               Metric("c", "90%", "percent")]
    assert summarize(metrics) == {"percent": 2, "count": 1}
```

**Step 2: Run to verify it fails** — `ModuleNotFoundError: No module named 'quant_support'`.

**Step 3: Write the extractor** — create `app/quant_support.py`:

```python
"""Quantitative decision-support extraction for Ask answers (BACKLOG P2 #6).

Pure regex/parse over the grounded answer text — never fabricates a number; only surfaces spans
literally present. Mirrors app/ask_confidence.py (the app passes result.answer; tests pass strings)."""
from __future__ import annotations

import re
from dataclasses import dataclass

METRIC_PATTERNS = [
    ("count", re.compile(r"\bn\s?=\s?\d+\b", re.I)),
    ("interval", re.compile(r"\b(?:95\s?%\s?CI|\d{1,3}(?:\.\d+)?\s?%?\s?CI)\b", re.I)),
    ("pvalue", re.compile(r"\bp\s?[<>=]\s?0?\.\d+\b", re.I)),
    ("percent", re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%")),
    ("duration", re.compile(r"\b\d+(?:\.\d+)?\s?(?:day|week|month|year)s?\b", re.I)),
    ("ratio", re.compile(r"\b\d+(?:\.\d+)?\s?(?:to|–|/)\s?\d+(?:\.\d+)?\b", re.I)),
]
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_COMPARATIVE = re.compile(
    r"\b(?:better|worse|higher|lower|superior|inferior|more|less|greater|fewer|"
    r"reduc\w*|increas\w*|improv\w*|outperform\w*|favou?rs?)\b", re.I)


@dataclass
class Metric:
    clause: str
    value: str
    kind: str


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text.strip()) if s.strip()]


def extract_metrics(text: str) -> list[Metric]:
    out: list[Metric] = []
    seen: set[tuple[str, str]] = set()
    for sent in _sentences(text):
        for kind, pat in METRIC_PATTERNS:
            for m in pat.finditer(sent):
                val = m.group(0).strip()
                key = (sent, val)
                if key in seen:
                    continue
                seen.add(key)
                out.append(Metric(clause=sent, value=val, kind=kind))
    return out


def has_quantitative_support(text: str) -> bool:
    return bool(extract_metrics(text))


def unquantified_comparisons(text: str) -> list[str]:
    flagged = []
    for sent in _sentences(text):
        if _COMPARATIVE.search(sent) and not any(p.search(sent) for _, p in METRIC_PATTERNS):
            flagged.append(sent)
    return flagged


def summarize(metrics) -> dict:
    counts: dict = {}
    for m in metrics:
        counts[m.kind] = counts.get(m.kind, 0) + 1
    return counts
```

**Step 4: Run to verify it passes** — PASS (5 passed).

**Step 5: Commit**

```bash
git add app/quant_support.py tests/test_quant_support.py
git commit -m "loop step 0: pure quantitative-support extractor + hermetic tests (P2 #6)"
```

---

### Task 2: Render "By the numbers" + unquantified-comparison caution in the Ask lane

**Files:**
- Modify: `app/streamlit_app.py` (Ask lane: render the panel beneath the confidence panel)
- Modify (Test): `tests/test_quant_support.py` (append an AppTest, engine stubbed)

**Edits to `app/streamlit_app.py`:**

1. Bare import near the other app helpers:

```python
from quant_support import extract_metrics, unquantified_comparisons, summarize as quant_summarize
```

2. After the claim-confidence panel render block (after the `for c in graded:` loop), add:

```python
        metrics = extract_metrics(result.answer)
        flags = unquantified_comparisons(result.answer)
        if metrics or flags:
            sig.section("By the numbers", "QTY")
            if metrics:
                st.caption(" · ".join(f"{k}: {n}" for k, n in quant_summarize(metrics).items()))
                for m in metrics:
                    st.markdown(f"**{m.value}** — {m.clause}")
            else:
                st.caption("No quantitative outcomes found in this answer.")
            if flags:
                st.warning("Comparative claims without numbers (verify against primary sources):")
                for f in flags:
                    st.markdown(f"⚠ {f}")
```

**Step 1: Write the failing test (append to `tests/test_quant_support.py`)**

```python
def test_ask_lane_renders_by_the_numbers(monkeypatch):
    """The Ask lane surfaces extracted metrics and flags unquantified comparisons, no exception.
    Hermetic: engine stubbed."""
    import pytest
    pytest.importorskip("streamlit")
    import neuro_caseboard.qa as qa

    class _Res:
        answer = ("Complete occlusion in 85% of patients (n=240). "
                  "Flow diverters achieve higher occlusion than coiling.")
        citations = []
        figures = []
        literature = None

    monkeypatch.setattr(qa, "answer_question", lambda question, **kw: _Res())

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=30)
    at.session_state["ask_q"] = "flow diverter vs coiling occlusion rates"
    at.run()
    assert len(at.exception) == 0
    blob = " ".join(m.value for m in at.markdown)
    assert "85%" in blob                      # extracted metric surfaced
    assert "higher occlusion" in blob         # unquantified comparison flagged
```

**Step 2-5:** run to confirm RED, apply edits, run full harness (expect 6 passed), commit:

```bash
git add app/streamlit_app.py tests/test_quant_support.py
git commit -m "loop step 1: render By-the-numbers + unquantified-comparison caution in Ask (P2 #6)"
```

---

## Self-Review

**1. Spec coverage:** surfaces rates/percentages/counts/intervals/p-values/durations (the comparison numbers the spec asks for) and explicitly flags comparative claims lacking numbers; never fabricates (extraction only); preserves not-found ("No quantitative outcomes found"). ✔
**2. Placeholder scan:** all code/commands runnable with expected output; the Ask-lane edit anchors on the existing confidence-panel block. ✔
**3. Type consistency:** `Metric(clause,value,kind)`, `extract_metrics`/`has_quantitative_support`/`unquantified_comparisons`/`summarize` signatures identical across module, tests, app. ✔

> Follow-up (not this PR): pull denominators/study-type/evidence-date from citation metadata (not just answer prose) and extend the panel to Build dossiers + the PDF. This PR lands the Ask-lane extraction + caution.
