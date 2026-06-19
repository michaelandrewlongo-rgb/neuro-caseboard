# Corpus Gap Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Operationalize BACKLOG P1 #3 ("Close high-yield corpus gaps") as a code deliverable: a **gap-audit tool** that takes a curated taxonomy of high-yield neurointerventional topics, probes the current index for coverage of each, classifies each topic as covered / weak / absent, and emits a corpus-expansion report **prioritized by clinical consequence × expected query frequency** — so expansion is driven by clinical consequence, not textbook availability.

**Architecture:** Two layers. (1) A **pure, hermetically-testable core** (`neuro_core/corpus_audit.py`) operating on an injected coverage `probe: Callable[[str], Coverage]` — no engine/corpus/network, so all logic (classify / audit / prioritize / render) is unit-tested on canned coverage signals. (2) A thin **integration seam**: `index_probe()` builds a real probe over the engine's retrieval seam (`Engine._retrieve` → `list[Hit]` with `.score`), and a `python -m neuro_core.scripts.audit_corpus_gaps` CLI prints the prioritized report (mirrors `neuro_core/scripts/probe_book.py`). The curated taxonomy is data (`neuro_core/high_yield_topics.py`).

**Tech Stack:** Python 3.10+, dataclasses, pytest. Hermetic tests — no corpus / index / LLM / network (the probe is injected/stubbed). No new dependencies.

## Global Constraints

- Loop harness (must exit 0): `python3 -m pytest -p no:cacheprovider -q tests/test_corpus_gap_audit.py`. Full suite ~17min on WSL2 — keep the inner loop scoped to this file; CI runs the full suite.
- **Additive only**: create new modules; do NOT modify existing engine behavior in `neuro_core/query.py`, `index.py`, etc. The integration probe consumes the existing retrieval seam read-only.
- The literal "add missing content" cannot be done autonomously (needs copyrighted textbook material); this deliverable is **detection + prioritization** of the gaps, producing the expansion worklist.
- Tests hermetic: drive the core with an injected `probe` returning canned `Coverage`; never build a real index or hit the network.
- Verified facts: retrieval seam is `Engine._retrieve(question) -> list[Hit]`; `Hit.score: float` (RRF fused, relative not absolute) at `neuro_core/index.py:10-16`; `get_engine(config)` / `query(question, config)` at `neuro_core/query.py:229-264`; CLI scripts use `python -m neuro_core.scripts.<name>` with `main(argv)` + `argparse` + `load_config()` (see `probe_book.py`); console entry points live in `pyproject.toml [project.scripts]`.

---

## Tasks (project-loop step cursor)

- [x] Task 1: Pure gap-audit core (`neuro_core/corpus_audit.py`) + curated taxonomy (`neuro_core/high_yield_topics.py`) + hermetic unit tests
- [x] Task 2: Real `index_probe` over the engine retrieval seam + `python -m neuro_core.scripts.audit_corpus_gaps` CLI + composition smoke test (engine stubbed)

---

### Task 1: Pure gap-audit core + curated taxonomy + hermetic unit tests

**Files:**
- Create: `neuro_core/corpus_audit.py`
- Create: `neuro_core/high_yield_topics.py`
- Create (Test): `tests/test_corpus_gap_audit.py`

**Interfaces:**
- Produces:
  - `Topic(key: str, label: str, probe_query: str, consequence: int, frequency: int)` — frozen dataclass; `consequence`/`frequency` are 1..5 weights.
  - `Coverage(top_score: float, n_strong_hits: int)` — the probe's coverage signal for one topic.
  - `GapRow(topic: Topic, status: str, coverage: Coverage, priority: int)` — one audited topic; `status ∈ {"covered","weak","absent"}`; `priority = consequence*frequency`.
  - `classify(cov: Coverage, *, strong_top: float, weak_top: float, min_strong: int = 2) -> str`
  - `audit(topics: Iterable[Topic], probe: Callable[[str], Coverage], *, strong_top: float, weak_top: float, min_strong: int = 2) -> list[GapRow]`
  - `prioritized_gaps(rows: Iterable[GapRow]) -> list[GapRow]` — only weak/absent, sorted by (priority desc, absent-before-weak, label asc) for deterministic output.
  - `render_report(rows: Iterable[GapRow]) -> str` — markdown.
  - `HIGH_YIELD_TOPICS: list[Topic]` (in `high_yield_topics.py`) — includes the three named gaps.
- Consumes: nothing.

**Step 1: Write the failing test** — create `tests/test_corpus_gap_audit.py`:

```python
"""Hermetic unit tests for the corpus gap-audit core (BACKLOG P1 #3).

Pure logic on an injected coverage probe — no engine, index, corpus, LLM, or network."""
from neuro_core.corpus_audit import (Topic, Coverage, GapRow, classify, audit,
                                     prioritized_gaps, render_report)
from neuro_core.high_yield_topics import HIGH_YIELD_TOPICS


def _t(key="t", consequence=3, frequency=3):
    return Topic(key=key, label=key.title(), probe_query=f"{key} query",
                 consequence=consequence, frequency=frequency)


def test_classify_covered_weak_absent():
    assert classify(Coverage(0.9, 5), strong_top=0.5, weak_top=0.2) == "covered"
    # strong top score but too few strong hits -> only weak
    assert classify(Coverage(0.9, 1), strong_top=0.5, weak_top=0.2) == "weak"
    assert classify(Coverage(0.3, 0), strong_top=0.5, weak_top=0.2) == "weak"
    assert classify(Coverage(0.1, 0), strong_top=0.5, weak_top=0.2) == "absent"


def test_audit_runs_probe_per_topic_and_records_priority():
    topics = [_t("a", 5, 4), _t("b", 2, 2)]
    canned = {"a query": Coverage(0.05, 0), "b query": Coverage(0.9, 4)}
    rows = audit(topics, lambda q: canned[q], strong_top=0.5, weak_top=0.2)
    by_key = {r.topic.key: r for r in rows}
    assert by_key["a"].status == "absent" and by_key["a"].priority == 20
    assert by_key["b"].status == "covered" and by_key["b"].priority == 4


def test_prioritized_gaps_excludes_covered_and_sorts_by_priority():
    rows = [
        GapRow(_t("low", 2, 2), "weak", Coverage(0.3, 0), 4),
        GapRow(_t("high", 5, 5), "absent", Coverage(0.0, 0), 25),
        GapRow(_t("ok", 4, 4), "covered", Coverage(0.9, 9), 16),
    ]
    gaps = prioritized_gaps(rows)
    assert [r.topic.key for r in gaps] == ["high", "low"]  # covered dropped, priority desc


def test_prioritized_gaps_absent_before_weak_on_tie():
    rows = [
        GapRow(_t("w", 3, 3), "weak", Coverage(0.3, 0), 9),
        GapRow(_t("a", 3, 3), "absent", Coverage(0.0, 0), 9),
    ]
    assert [r.status for r in prioritized_gaps(rows)] == ["absent", "weak"]


def test_render_report_lists_gaps_with_status_and_priority():
    rows = [GapRow(_t("aneurysm-rupture-rescue", 5, 5), "absent", Coverage(0.0, 0), 25)]
    md = render_report(rows)
    assert "aneurysm-rupture-rescue" in md.lower() or "Aneurysm-Rupture-Rescue" in md
    assert "absent" in md
    assert "25" in md


def test_taxonomy_includes_the_three_named_gaps():
    keys = {t.key for t in HIGH_YIELD_TOPICS}
    # the three gaps named in BACKLOG P1 #3
    assert any("rupture" in k for k in keys)        # intraprocedural aneurysm rupture rescue
    assert any("eca" in k or "anastomos" in k for k in keys)  # ECA dangerous anastomoses
    assert any("outcome" in k or "rate" in k for k in keys)   # quantitative outcomes/rates
    # every topic is well-formed
    for t in HIGH_YIELD_TOPICS:
        assert t.probe_query and 1 <= t.consequence <= 5 and 1 <= t.frequency <= 5
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_corpus_gap_audit.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'neuro_core.corpus_audit'`.

**Step 3: Write the core** — create `neuro_core/corpus_audit.py`:

```python
"""Corpus gap audit (BACKLOG P1 #3): score high-yield topic coverage against the index and
emit a clinically-prioritized expansion worklist.

Pure core: every function operates on an injected ``probe: Callable[[str], Coverage]`` so the
logic is hermetically testable. The real probe over the engine lives in ``index_probe`` (added
in Task 2); it is the only part that touches the corpus."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class Topic:
    key: str
    label: str
    probe_query: str
    consequence: int  # 1..5 — clinical consequence of missing this topic
    frequency: int    # 1..5 — expected query frequency


@dataclass
class Coverage:
    top_score: float    # best reranked hit score for the probe query
    n_strong_hits: int  # number of hits judged strong by the probe


@dataclass
class GapRow:
    topic: Topic
    status: str           # "covered" | "weak" | "absent"
    coverage: Coverage
    priority: int         # consequence * frequency


def classify(cov: Coverage, *, strong_top: float, weak_top: float, min_strong: int = 2) -> str:
    """covered = a strong top hit AND enough strong hits; weak = some signal; absent = none."""
    if cov.top_score >= strong_top and cov.n_strong_hits >= min_strong:
        return "covered"
    if cov.top_score >= weak_top:
        return "weak"
    return "absent"


def audit(topics: Iterable[Topic], probe: Callable[[str], Coverage], *,
          strong_top: float, weak_top: float, min_strong: int = 2) -> list[GapRow]:
    rows = []
    for t in topics:
        cov = probe(t.probe_query)
        rows.append(GapRow(topic=t,
                           status=classify(cov, strong_top=strong_top, weak_top=weak_top,
                                           min_strong=min_strong),
                           coverage=cov,
                           priority=t.consequence * t.frequency))
    return rows


_STATUS_RANK = {"absent": 0, "weak": 1}  # absent sorts before weak on a priority tie


def prioritized_gaps(rows: Iterable[GapRow]) -> list[GapRow]:
    gaps = [r for r in rows if r.status in _STATUS_RANK]
    return sorted(gaps, key=lambda r: (-r.priority, _STATUS_RANK[r.status], r.topic.label))


def render_report(rows: Iterable[GapRow]) -> str:
    gaps = prioritized_gaps(rows)
    lines = ["# Corpus expansion worklist — high-yield gaps",
             "",
             "Ranked by clinical consequence x expected query frequency. "
             "Coverage probed against the current index.",
             "",
             "| Priority | Topic | Status | Consequence | Frequency | Top score | Strong hits |",
             "|---:|---|---|---:|---:|---:|---:|"]
    for r in gaps:
        lines.append(f"| {r.priority} | {r.topic.label} | {r.status} | "
                     f"{r.topic.consequence} | {r.topic.frequency} | "
                     f"{r.coverage.top_score:.3f} | {r.coverage.n_strong_hits} |")
    if not gaps:
        lines.append("| — | _no gaps detected_ | — | — | — | — | — |")
    return "\n".join(lines) + "\n"
```

**Step 4: Write the taxonomy** — create `neuro_core/high_yield_topics.py`:

```python
"""Curated high-yield neurointerventional topics for the corpus gap audit (BACKLOG P1 #3).

Weights are editorial (1..5): ``consequence`` = clinical harm if the corpus lacks the topic;
``frequency`` = how often it is queried. Seeded with the three gaps named in the operator brief
plus adjacent high-consequence topics; extend as coverage priorities evolve."""
from neuro_core.corpus_audit import Topic

HIGH_YIELD_TOPICS: list[Topic] = [
    Topic("intraprocedural-aneurysm-rupture-rescue",
          "Intraprocedural aneurysm rupture rescue",
          "intraprocedural aneurysm rupture management during coiling rescue", 5, 4),
    Topic("eca-dangerous-anastomoses",
          "ECA dangerous anastomoses",
          "external carotid artery dangerous anastomoses to ICA and vertebral", 5, 3),
    Topic("quantitative-procedural-outcome-rates",
          "Quantitative procedural outcome / complication / retreatment rates",
          "aneurysm coiling occlusion complication retreatment rates outcomes", 4, 5),
    Topic("thrombectomy-recanalization-rates",
          "Thrombectomy recanalization (TICI) rates",
          "mechanical thrombectomy TICI recanalization first-pass outcome rates", 4, 5),
    Topic("flow-diverter-occlusion-rates",
          "Flow diverter occlusion / complication rates",
          "flow diverter pipeline occlusion rate delayed rupture complication", 4, 4),
    Topic("contrast-induced-neurotoxicity",
          "Contrast-induced neurotoxicity / nephropathy",
          "contrast induced neurotoxicity encephalopathy nephropathy neurointervention", 3, 3),
    Topic("groin-access-complications",
          "Arterial access-site complications",
          "femoral radial access site complication pseudoaneurysm hematoma", 3, 4),
    Topic("vasospasm-endovascular-management",
          "Endovascular vasospasm management",
          "cerebral vasospasm intra-arterial verapamil angioplasty management", 4, 4),
]
```

**Step 5: Run to verify it passes**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_corpus_gap_audit.py`
Expected: PASS — 6 passed.

**Step 6: Commit**

```bash
git add neuro_core/corpus_audit.py neuro_core/high_yield_topics.py tests/test_corpus_gap_audit.py
git commit -m "loop step 0: corpus gap-audit core + high-yield taxonomy + hermetic tests (P1 #3)"
```

---

### Task 2: Real index probe + CLI report + composition smoke test

**Files:**
- Modify: `neuro_core/corpus_audit.py` (append `index_probe`)
- Create: `neuro_core/scripts/audit_corpus_gaps.py`
- Modify (Test): `tests/test_corpus_gap_audit.py` (append a composition test with a stubbed engine)

**Interfaces:**
- Consumes: `Topic`, `Coverage`, `audit`, `render_report`, `HIGH_YIELD_TOPICS` from Task 1; `get_engine` from `neuro_core.query`.
- Produces: `index_probe(engine=None, config=None, strong_ratio: float = 0.6) -> Callable[[str], Coverage]`; `audit_corpus_gaps.main(argv=None) -> int`.

**Design note (RRF scores are relative):** `Hit.score` is an RRF fused score, not an absolute similarity, so "strong" is defined relative to the probe's own top score: a hit counts as strong when `score >= strong_ratio * top_score`. Absolute `strong_top`/`weak_top` thresholds for `classify` are CLI flags with documented defaults; the report is advisory (calibration is surfaced, not asserted — it cannot be validated without the live corpus, by design).

**Step 1: Write the failing composition test (append to `tests/test_corpus_gap_audit.py`)**

```python
def test_index_probe_composes_with_audit_over_a_stubbed_engine():
    """index_probe turns engine retrieval into Coverage; audit+render then run end-to-end.
    Hermetic: a fake engine returns canned hits — no real index/corpus/network."""
    from neuro_core.corpus_audit import index_probe, audit, render_report, Topic

    class _Hit:
        def __init__(self, score): self.score = score

    class _FakeEngine:
        def _retrieve(self, q):
            # a well-covered query returns strong hits; a gap query returns nothing
            return [_Hit(0.9), _Hit(0.8), _Hit(0.7)] if "covered" in q else []

    probe = index_probe(engine=_FakeEngine(), strong_ratio=0.6)
    assert probe("covered topic").n_strong_hits >= 2
    assert probe("missing topic") == probe("missing topic")  # deterministic
    gap = probe("missing topic")
    assert gap.top_score == 0.0 and gap.n_strong_hits == 0

    topics = [Topic("c", "Covered", "a covered query", 3, 3),
              Topic("m", "Missing", "a missing query", 5, 5)]
    rows = audit(topics, probe, strong_top=0.5, weak_top=0.2)
    md = render_report(rows)
    assert "Missing" in md and "Covered" not in md  # only the gap is in the worklist
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_corpus_gap_audit.py::test_index_probe_composes_with_audit_over_a_stubbed_engine`
Expected: FAIL — `ImportError: cannot import name 'index_probe'`.

**Step 3: Append `index_probe` to `neuro_core/corpus_audit.py`**

```python
def index_probe(engine=None, config=None, strong_ratio: float = 0.6):
    """Build a coverage probe over the engine's retrieval seam (read-only).

    A hit is "strong" relative to the query's own top score (RRF scores are not absolute):
    ``score >= strong_ratio * top_score``. Returns Coverage(0.0, 0) for a query with no hits."""
    if engine is None:
        from neuro_core.query import get_engine
        engine = get_engine(config)

    def _probe(query: str) -> Coverage:
        hits = engine._retrieve(query)
        if not hits:
            return Coverage(top_score=0.0, n_strong_hits=0)
        top = max(h.score for h in hits)
        n_strong = sum(1 for h in hits if h.score >= strong_ratio * top)
        return Coverage(top_score=float(top), n_strong_hits=int(n_strong))

    return _probe
```

**Step 4: Create the CLI** — `neuro_core/scripts/audit_corpus_gaps.py`:

```python
"""Audit the index for high-yield corpus gaps and print a prioritized expansion worklist.

    python -m neuro_core.scripts.audit_corpus_gaps                # markdown report to stdout
    python -m neuro_core.scripts.audit_corpus_gaps --strong-top 0.5 --weak-top 0.2

Exit 0 always (advisory report). Coverage thresholds are heuristic; the report ranks gaps by
clinical consequence x expected query frequency. Adding the missing content is a manual,
SME-curated follow-up — this tool produces the worklist."""
import argparse
import sys

from neuro_core.corpus_audit import audit, index_probe, render_report
from neuro_core.high_yield_topics import HIGH_YIELD_TOPICS


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="audit_corpus_gaps")
    ap.add_argument("--strong-top", type=float, default=0.5,
                    help="top-score at/above which a topic can be 'covered'")
    ap.add_argument("--weak-top", type=float, default=0.2,
                    help="top-score at/above which a topic is 'weak' (else 'absent')")
    ap.add_argument("--min-strong", type=int, default=2,
                    help="strong hits required (with --strong-top) for 'covered'")
    args = ap.parse_args(argv)
    probe = index_probe()
    rows = audit(HIGH_YIELD_TOPICS, probe, strong_top=args.strong_top,
                 weak_top=args.weak_top, min_strong=args.min_strong)
    print(render_report(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 5: Run the full harness**

Run: `python3 -m pytest -p no:cacheprovider -q tests/test_corpus_gap_audit.py`
Expected: PASS — 7 passed.

**Step 6: Commit**

```bash
git add neuro_core/corpus_audit.py neuro_core/scripts/audit_corpus_gaps.py tests/test_corpus_gap_audit.py
git commit -m "loop step 1: index_probe over retrieval seam + audit_corpus_gaps CLI (P1 #3)"
```

---

## Self-Review

**1. Spec coverage:** P1 #3 asks to (a) surface absent high-yield content and (b) prioritize expansion by clinical consequence rather than textbook availability. The taxonomy names the three required gaps (rupture rescue, ECA anastomoses, quantitative rates) + adjacent high-consequence topics; `audit`+`classify` detect coverage; `prioritized_gaps`/`render_report` rank by consequence×frequency; the CLI emits the worklist. Adding content itself is explicitly out of scope (copyrighted material, manual SME step) and stated as such. ✔
**2. Placeholder scan:** all steps contain runnable code/commands + exact expected output. No TODO/TBD. ✔
**3. Type consistency:** `Topic`/`Coverage`/`GapRow` fields and `classify`/`audit`/`prioritized_gaps`/`render_report`/`index_probe` signatures are identical across the core (Task 1 def), the taxonomy data, the tests, and the CLI (Task 2 call sites). `probe: Callable[[str], Coverage]` is consistent everywhere. ✔
