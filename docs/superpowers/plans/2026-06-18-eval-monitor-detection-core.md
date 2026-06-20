# Eval Monitor — Detection Core (Milestone 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the unattended detection half of the eval monitor: a Python command that K-samples the build pathway over the eval cases, flags must_cover coverage regressions against a committed baseline, and writes deduped, suppressible issue cards + a digest — with no changes to the engine.

**Architecture:** A new `eval/monitor/` package. A generic `Detector` protocol consumes a `RunArtifacts` bundle (K boards per case + baseline) and emits `Issue` records. Milestone 1 ships one detector (`coverage_drop`) that reuses `eval/coverage.py`'s scoring. Orchestration builds boards via an *injected* build function (real `build_dossier` by default, a fake in tests), so every unit is offline-testable. State is files: `baseline.json`, `suppressions.yaml`, `issues/<fingerprint>.json`, `digest.md`.

**Tech Stack:** Python 3 (stdlib `dataclasses`, `hashlib`, `json`, `argparse`, `datetime`), PyYAML (already used by `eval/ambiguous_variants.yaml`), pytest. Reuses `eval/coverage.py` and `neuro_caseboard.pipeline.build_dossier` + `neuro_caseboard.render_md.render_markdown`.

## Global Constraints

- Python 3 with `from __future__ import annotations` at the top of every module (repo convention).
- **No engine modifications in Milestone 1.** `eval/monitor/` only *reads* boards produced by the existing pipeline; it imports `build_dossier`/`render_markdown`/`coverage` but does not edit them.
- All live behavior (the actual build) is reached through an **injected** `build_fn`; defaults wrap the real engine, tests pass fakes. No test may call Vertex or require the corpus.
- Tests live under `tests/eval/monitor/` (repo `testpaths = ["tests"]`, `--strict-markers --strict-config`).
- Dataclasses are `frozen=True`.
- Issue card files are named by **fingerprint** (`issues/<fingerprint>.json`) so a recurring issue overwrites its own card (natural dedupe).
- Baseline is read-only in this milestone; advancing it on merge is a later milestone.
- Commit after every task with a `feat:`/`test:`-style message.

---

### Task 1: Contracts (`Evidence`, `Issue`, `RunArtifacts`, `Detector`)

**Files:**
- Create: `eval/monitor/__init__.py`
- Create: `eval/monitor/contracts.py`
- Create: `tests/eval/monitor/__init__.py`
- Test: `tests/eval/monitor/test_contracts.py`

**Interfaces:**
- Produces:
  - `Evidence(case_id: str, detail: str, before: float | None = None, after: float | None = None)`
  - `Issue(kind: str, severity: str, title: str, evidence: list[Evidence], locus: str, proposed_tier: str, proposed_fix: str, fingerprint: str)`
  - `RunArtifacts(cases: list[dict], boards: dict[str, list[str]], baseline: dict, explorer: dict = {})`
  - `Detector` Protocol: attribute `name: str`; method `detect(self, art: RunArtifacts) -> list[Issue]`

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/monitor/test_contracts.py
from __future__ import annotations

from eval.monitor.contracts import Evidence, Issue, RunArtifacts


def test_issue_and_evidence_construct():
    ev = Evidence(case_id="c1", detail="missing X", before=0.9, after=0.5)
    iss = Issue(
        kind="coverage_drop", severity="high", title="c1 dropped",
        evidence=[ev], locus="author", proposed_tier="knob-only",
        proposed_fix="tweak prompt", fingerprint="abc123",
    )
    assert iss.evidence[0].after == 0.5
    assert iss.fingerprint == "abc123"


def test_runartifacts_defaults_explorer_empty():
    art = RunArtifacts(cases=[{"id": "c1"}], boards={"c1": ["board"]}, baseline={})
    assert art.explorer == {}
    assert art.boards["c1"] == ["board"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/eval/monitor/test_contracts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.monitor'`

- [ ] **Step 3: Write minimal implementation**

```python
# eval/monitor/__init__.py
```

```python
# tests/eval/monitor/__init__.py
```

```python
# eval/monitor/contracts.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Evidence:
    case_id: str
    detail: str
    before: float | None = None
    after: float | None = None


@dataclass(frozen=True)
class Issue:
    kind: str
    severity: str
    title: str
    evidence: list[Evidence]
    locus: str
    proposed_tier: str
    proposed_fix: str
    fingerprint: str


@dataclass(frozen=True)
class RunArtifacts:
    cases: list[dict]
    boards: dict[str, list[str]]
    baseline: dict
    explorer: dict = field(default_factory=dict)


class Detector(Protocol):
    name: str

    def detect(self, art: RunArtifacts) -> list[Issue]:
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/eval/monitor/test_contracts.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add eval/monitor/__init__.py eval/monitor/contracts.py tests/eval/monitor/__init__.py tests/eval/monitor/test_contracts.py
git commit -m "feat(monitor): detector/issue contracts"
```

---

### Task 2: Fingerprint

**Files:**
- Create: `eval/monitor/fingerprint.py`
- Test: `tests/eval/monitor/test_fingerprint.py`

**Interfaces:**
- Produces: `fingerprint(kind: str, locus: str, signature: str) -> str` — a stable 16-char hex hash; identical inputs give identical output, and a changed `signature` gives a different output.

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/monitor/test_fingerprint.py
from __future__ import annotations

from eval.monitor.fingerprint import fingerprint


def test_fingerprint_is_stable():
    a = fingerprint("coverage_drop", "author", "itemA|itemB")
    b = fingerprint("coverage_drop", "author", "itemA|itemB")
    assert a == b
    assert len(a) == 16


def test_fingerprint_changes_when_signature_worsens():
    base = fingerprint("coverage_drop", "author", "itemA|itemB")
    worse = fingerprint("coverage_drop", "author", "itemA|itemB|itemC")
    assert base != worse


def test_fingerprint_normalizes_whitespace_and_case():
    assert fingerprint("k", "l", "Item A") == fingerprint("k", "l", "item   a")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/eval/monitor/test_fingerprint.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.monitor.fingerprint'`

- [ ] **Step 3: Write minimal implementation**

```python
# eval/monitor/fingerprint.py
from __future__ import annotations

import hashlib
import re


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def fingerprint(kind: str, locus: str, signature: str) -> str:
    raw = f"{_norm(kind)}|{_norm(locus)}|{_norm(signature)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/eval/monitor/test_fingerprint.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add eval/monitor/fingerprint.py tests/eval/monitor/test_fingerprint.py
git commit -m "feat(monitor): stable fingerprint for dedupe/suppression"
```

---

### Task 3: Baseline load + regression rule

**Files:**
- Create: `eval/monitor/baseline.py`
- Test: `tests/eval/monitor/test_baseline.py`

**Interfaces:**
- Produces:
  - `load_baseline(path) -> dict` — parse JSON; missing file → `{}`.
  - `is_regression(before: float | None, after: float, *, rel_margin: float, abs_floor: float) -> bool` — `True` if `after < abs_floor`, OR (`before` is not None AND `after < before - rel_margin`).

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/monitor/test_baseline.py
from __future__ import annotations

import json

from eval.monitor.baseline import is_regression, load_baseline


def test_absolute_floor_breach_is_regression():
    assert is_regression(None, 0.50, rel_margin=0.05, abs_floor=0.70) is True


def test_healthy_first_run_is_not_a_regression():
    assert is_regression(None, 0.90, rel_margin=0.05, abs_floor=0.70) is False


def test_relative_drop_beyond_margin_is_regression():
    assert is_regression(0.90, 0.80, rel_margin=0.05, abs_floor=0.70) is True


def test_small_dip_within_margin_is_not_a_regression():
    assert is_regression(0.90, 0.88, rel_margin=0.05, abs_floor=0.70) is False


def test_load_baseline_missing_returns_empty(tmp_path):
    assert load_baseline(tmp_path / "nope.json") == {}


def test_load_baseline_reads_json(tmp_path):
    p = tmp_path / "baseline.json"
    p.write_text(json.dumps({"c1": {"coverage": 0.9}}), encoding="utf-8")
    assert load_baseline(p) == {"c1": {"coverage": 0.9}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/eval/monitor/test_baseline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.monitor.baseline'`

- [ ] **Step 3: Write minimal implementation**

```python
# eval/monitor/baseline.py
from __future__ import annotations

import json
from pathlib import Path


def load_baseline(path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def is_regression(before: float | None, after: float, *, rel_margin: float,
                  abs_floor: float) -> bool:
    if after < abs_floor:
        return True
    if before is not None and after < before - rel_margin:
        return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/eval/monitor/test_baseline.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add eval/monitor/baseline.py tests/eval/monitor/test_baseline.py
git commit -m "feat(monitor): baseline load + relative/absolute regression rule"
```

---

### Task 4: Coverage-drop detector

**Files:**
- Create: `eval/monitor/detectors/__init__.py`
- Create: `eval/monitor/detectors/coverage_drop.py`
- Test: `tests/eval/monitor/test_coverage_drop.py`

**Interfaces:**
- Consumes: `eval.coverage.ANCHORS` (dict `case_id -> [(label, [anchors])]`), `eval.coverage.score_board(text, items) -> (covered, missing)`; `RunArtifacts`, `Issue`, `Evidence` (Task 1); `fingerprint` (Task 2); `is_regression` (Task 3).
- Produces: `CoverageDropDetector(*, rel_margin: float = 0.05, abs_floor: float = 0.70)` with `name = "coverage_drop"` and `detect(art) -> list[Issue]`. Per case it takes the **worst-of-K** coverage fraction, compares to `baseline[cid]["coverage"]`, and emits one `Issue` (with the missing must_cover labels as evidence) when `is_regression` is true.

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/monitor/test_coverage_drop.py
from __future__ import annotations

from eval.coverage import ANCHORS
from eval.monitor.contracts import RunArtifacts
from eval.monitor.detectors.coverage_drop import CoverageDropDetector

CID = "spine_acdf_c56"  # a real case id in eval/coverage.py ANCHORS


def _full_board() -> str:
    # one anchor from every must_cover item -> 100% coverage
    return " . ".join(anchors[0] for _label, anchors in ANCHORS[CID])


def test_flags_when_board_covers_nothing_and_no_baseline():
    art = RunArtifacts(
        cases=[{"id": CID, "case_query": "x"}],
        boards={CID: ["- ✓ no relevant clinical content here"]},
        baseline={},
    )
    issues = CoverageDropDetector(abs_floor=0.70).detect(art)
    assert len(issues) == 1
    iss = issues[0]
    assert iss.kind == "coverage_drop"
    assert iss.severity == "high"      # below floor
    assert iss.proposed_tier == "knob-only"
    assert len(iss.evidence) == len(ANCHORS[CID])  # everything missing
    assert iss.fingerprint


def test_silent_when_fully_covered_and_no_baseline():
    art = RunArtifacts(
        cases=[{"id": CID, "case_query": "x"}],
        boards={CID: [f"- ✓ {_full_board()}"]},
        baseline={},
    )
    assert CoverageDropDetector(abs_floor=0.70).detect(art) == []


def test_uses_worst_of_k_runs():
    # one perfect board, one empty board -> worst-of-K = 0% -> flagged
    art = RunArtifacts(
        cases=[{"id": CID, "case_query": "x"}],
        boards={CID: [f"- ✓ {_full_board()}", "- ✓ nothing"]},
        baseline={},
    )
    assert len(CoverageDropDetector(abs_floor=0.70).detect(art)) == 1


def test_relative_regression_against_baseline():
    # fully covered now (1.0) but baseline says 1.0 -> no regression
    art = RunArtifacts(
        cases=[{"id": CID, "case_query": "x"}],
        boards={CID: [f"- ✓ {_full_board()}"]},
        baseline={CID: {"coverage": 1.0}},
    )
    assert CoverageDropDetector().detect(art) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/eval/monitor/test_coverage_drop.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.monitor.detectors'`

- [ ] **Step 3: Write minimal implementation**

```python
# eval/monitor/detectors/__init__.py
```

```python
# eval/monitor/detectors/coverage_drop.py
from __future__ import annotations

from eval.coverage import ANCHORS, score_board
from eval.monitor.baseline import is_regression
from eval.monitor.contracts import Evidence, Issue, RunArtifacts
from eval.monitor.fingerprint import fingerprint


class CoverageDropDetector:
    name = "coverage_drop"

    def __init__(self, *, rel_margin: float = 0.05, abs_floor: float = 0.70):
        self.rel_margin = rel_margin
        self.abs_floor = abs_floor

    def detect(self, art: RunArtifacts) -> list[Issue]:
        issues: list[Issue] = []
        for case in art.cases:
            cid = case["id"]
            items = ANCHORS.get(cid)
            boards = art.boards.get(cid)
            if not items or not boards:
                continue
            scored = [score_board(b, items) for b in boards]
            fracs = [len(cov) / len(items) for cov, _missing in scored]
            after = min(fracs)                       # worst-of-K
            _cov, missing = scored[fracs.index(after)]
            before = art.baseline.get(cid, {}).get("coverage")
            if not is_regression(before, after, rel_margin=self.rel_margin,
                                 abs_floor=self.abs_floor):
                continue
            signature = "|".join(sorted(missing))
            evidence = [Evidence(case_id=cid, detail=m, before=before, after=after)
                        for m in missing]
            issues.append(Issue(
                kind="coverage_drop",
                severity="high" if after < self.abs_floor else "medium",
                title=f"{cid}: coverage {after:.0%} ({len(missing)} must_cover missing)",
                evidence=evidence,
                locus="author (explore_llm.py)",
                proposed_tier="knob-only",
                proposed_fix=(
                    "Strengthen the author/critic prompt or ontology dimensions to cover: "
                    + ", ".join(missing[:3]) + ("…" if len(missing) > 3 else "")),
                fingerprint=fingerprint("coverage_drop", cid, signature),
            ))
        return issues
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/eval/monitor/test_coverage_drop.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add eval/monitor/detectors/__init__.py eval/monitor/detectors/coverage_drop.py tests/eval/monitor/test_coverage_drop.py
git commit -m "feat(monitor): coverage-drop detector (worst-of-K vs baseline)"
```

---

### Task 5: Suppression load + filter

**Files:**
- Create: `eval/monitor/suppress.py`
- Test: `tests/eval/monitor/test_suppress.py`

**Interfaces:**
- Consumes: `Issue` (Task 1).
- Produces:
  - `load_suppressions(path, *, today: datetime.date | None = None) -> set[str]` — reads `suppressions.yaml` (a list of `{fingerprint, reason, date, expires?}`); returns the set of *active* fingerprints (drops entries whose `expires` is before `today`). Missing file → empty set.
  - `filter_suppressed(issues: list[Issue], suppressed: set[str]) -> list[Issue]` — drops issues whose fingerprint is in `suppressed`.

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/monitor/test_suppress.py
from __future__ import annotations

import datetime

from eval.monitor.contracts import Issue
from eval.monitor.suppress import filter_suppressed, load_suppressions


def _issue(fp: str) -> Issue:
    return Issue(kind="coverage_drop", severity="low", title="t", evidence=[],
                 locus="author", proposed_tier="knob-only", proposed_fix="f",
                 fingerprint=fp)


def test_missing_file_returns_empty_set(tmp_path):
    assert load_suppressions(tmp_path / "nope.yaml") == set()


def test_active_suppression_is_loaded(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("- fingerprint: abc123\n  reason: known noise\n", encoding="utf-8")
    assert load_suppressions(p) == {"abc123"}


def test_expired_suppression_is_dropped(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("- fingerprint: abc123\n  expires: 2020-01-01\n", encoding="utf-8")
    assert load_suppressions(p, today=datetime.date(2026, 1, 1)) == set()


def test_filter_removes_suppressed_issues():
    issues = [_issue("keep"), _issue("drop")]
    assert filter_suppressed(issues, {"drop"}) == [issues[0]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/eval/monitor/test_suppress.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.monitor.suppress'`

- [ ] **Step 3: Write minimal implementation**

```python
# eval/monitor/suppress.py
from __future__ import annotations

import datetime
from pathlib import Path

import yaml

from eval.monitor.contracts import Issue


def load_suppressions(path, *, today: datetime.date | None = None) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    today = today or datetime.date.today()
    entries = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    active: set[str] = set()
    for entry in entries:
        fp = entry.get("fingerprint")
        if not fp:
            continue
        expires = entry.get("expires")
        if expires and datetime.date.fromisoformat(str(expires)) < today:
            continue
        active.add(fp)
    return active


def filter_suppressed(issues: list[Issue], suppressed: set[str]) -> list[Issue]:
    return [i for i in issues if i.fingerprint not in suppressed]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/eval/monitor/test_suppress.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add eval/monitor/suppress.py tests/eval/monitor/test_suppress.py
git commit -m "feat(monitor): suppression load (with expiry) + filter"
```

---

### Task 6: Orchestration — build K boards, run detectors, write cards

**Files:**
- Create: `eval/monitor/detect.py`
- Test: `tests/eval/monitor/test_detect.py`

**Interfaces:**
- Consumes: `RunArtifacts`, `Issue` (Task 1); `CoverageDropDetector` (Task 4).
- Produces:
  - `build_boards(case_query: str, k: int, build_fn) -> list[str]` — calls `build_fn(case_query)` `k` times.
  - `default_build_fn(case_query: str) -> str` — wraps `build_dossier` + `render_markdown` (the real engine; not exercised in tests).
  - `run_detection(cases: list[dict], baseline: dict, detectors: list, *, k: int, build_fn) -> list[Issue]`.
  - `write_cards(issues: list[Issue], issues_dir, *, run_id: str, git_sha: str) -> list[Path]` — writes `<fingerprint>.json` per issue (serialized issue + `status="new"` + provenance).

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/monitor/test_detect.py
from __future__ import annotations

import json

from eval.coverage import ANCHORS
from eval.monitor.contracts import Issue
from eval.monitor.detect import build_boards, run_detection, write_cards
from eval.monitor.detectors.coverage_drop import CoverageDropDetector

CID = "spine_acdf_c56"


def test_build_boards_calls_build_fn_k_times():
    calls = []
    boards = build_boards("query", 3, lambda q: calls.append(q) or "board")
    assert boards == ["board", "board", "board"]
    assert calls == ["query", "query", "query"]


def test_run_detection_flags_empty_boards():
    cases = [{"id": CID, "case_query": "C5-6 ACDF"}]
    issues = run_detection(
        cases, baseline={}, detectors=[CoverageDropDetector()],
        k=2, build_fn=lambda q: "- ✓ nothing relevant",
    )
    assert len(issues) == 1
    assert issues[0].kind == "coverage_drop"


def test_write_cards_emits_fingerprint_named_json(tmp_path):
    iss = Issue(kind="coverage_drop", severity="high", title="t", evidence=[],
                locus="author", proposed_tier="knob-only", proposed_fix="f",
                fingerprint="fp1")
    paths = write_cards([iss], tmp_path, run_id="run-1", git_sha="deadbeef")
    assert paths == [tmp_path / "fp1.json"]
    card = json.loads((tmp_path / "fp1.json").read_text())
    assert card["status"] == "new"
    assert card["provenance"] == {"run_id": "run-1", "git_sha": "deadbeef"}
    assert card["kind"] == "coverage_drop"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/eval/monitor/test_detect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.monitor.detect'`

- [ ] **Step 3: Write minimal implementation**

```python
# eval/monitor/detect.py
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from eval.monitor.contracts import Issue, RunArtifacts


def default_build_fn(case_query: str) -> str:
    from neuro_caseboard.pipeline import build_dossier
    from neuro_caseboard.render_md import render_markdown
    return render_markdown(build_dossier(case_query))


def build_boards(case_query: str, k: int, build_fn) -> list[str]:
    return [build_fn(case_query) for _ in range(k)]


def run_detection(cases: list[dict], baseline: dict, detectors: list, *,
                  k: int, build_fn) -> list[Issue]:
    boards = {c["id"]: build_boards(c["case_query"], k, build_fn) for c in cases}
    art = RunArtifacts(cases=cases, boards=boards, baseline=baseline)
    issues: list[Issue] = []
    for detector in detectors:
        issues.extend(detector.detect(art))
    return issues


def write_cards(issues: list[Issue], issues_dir, *, run_id: str,
                git_sha: str) -> list[Path]:
    out = Path(issues_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for iss in issues:
        card = dataclasses.asdict(iss)
        card["status"] = "new"
        card["provenance"] = {"run_id": run_id, "git_sha": git_sha}
        path = out / f"{iss.fingerprint}.json"
        path.write_text(json.dumps(card, indent=2), encoding="utf-8")
        paths.append(path)
    return paths
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/eval/monitor/test_detect.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add eval/monitor/detect.py tests/eval/monitor/test_detect.py
git commit -m "feat(monitor): build-K/run-detectors/write-cards orchestration"
```

---

### Task 7: Digest rendering + CLI entry + scheduling note

**Files:**
- Create: `eval/monitor/digest.py`
- Modify: `eval/monitor/detect.py` (add `main()` + `__main__` guard)
- Create: `eval/monitor/README.md`
- Test: `tests/eval/monitor/test_digest.py`

**Interfaces:**
- Consumes: `Issue` (Task 1); `load_baseline` (Task 3); `load_suppressions`, `filter_suppressed` (Task 5); `run_detection`, `write_cards`, `default_build_fn` (Task 6); `CoverageDropDetector` (Task 4).
- Produces: `render_digest(issues: list[Issue]) -> str`; `eval/monitor/detect.py:main(argv=None) -> int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/eval/monitor/test_digest.py
from __future__ import annotations

from eval.monitor.contracts import Evidence, Issue
from eval.monitor.digest import render_digest


def test_empty_digest_says_no_issues():
    out = render_digest([])
    assert "No new issues" in out


def test_digest_lists_issue_sorted_by_severity():
    low = Issue(kind="coverage_drop", severity="low", title="low one", evidence=[],
                locus="author", proposed_tier="knob-only", proposed_fix="f", fingerprint="l1")
    high = Issue(kind="coverage_drop", severity="high", title="high one",
                 evidence=[Evidence("c1", "missing X", before=0.9, after=0.4)],
                 locus="author", proposed_tier="knob-only", proposed_fix="f", fingerprint="h1")
    out = render_digest([low, high])
    assert out.index("high one") < out.index("low one")   # high sorts first
    assert "missing X" in out
    assert "`h1`" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/eval/monitor/test_digest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.monitor.digest'`

- [ ] **Step 3: Write minimal implementation**

```python
# eval/monitor/digest.py
from __future__ import annotations

from eval.monitor.contracts import Issue

_ORDER = {"high": 0, "medium": 1, "low": 2}


def render_digest(issues: list[Issue]) -> str:
    if not issues:
        return "# Monitor digest\n\nNo new issues. ✓\n"
    lines = ["# Monitor digest", "", f"{len(issues)} new issue(s):", ""]
    for iss in sorted(issues, key=lambda i: _ORDER.get(i.severity, 3)):
        lines.append(f"## [{iss.severity}] {iss.title}")
        lines.append(
            f"- **kind:** {iss.kind} · **locus:** {iss.locus} "
            f"· **proposed tier:** {iss.proposed_tier} · **fingerprint:** `{iss.fingerprint}`")
        lines.append(f"- **proposed fix:** {iss.proposed_fix}")
        for ev in iss.evidence:
            before = "—" if ev.before is None else f"{ev.before:.0%}"
            after = "—" if ev.after is None else f"{ev.after:.0%}"
            lines.append(f"  - {ev.case_id}: {ev.detail}  ({before} → {after})")
        lines.append("")
    return "\n".join(lines)
```

Append to `eval/monitor/detect.py` (after `write_cards`):

```python
def main(argv=None) -> int:
    import argparse
    import datetime
    import subprocess

    from eval.coverage import HERE as EVAL_DIR
    from eval.monitor.baseline import load_baseline
    from eval.monitor.detectors.coverage_drop import CoverageDropDetector
    from eval.monitor.digest import render_digest
    from eval.monitor.suppress import filter_suppressed, load_suppressions

    mon = Path(__file__).parent
    ap = argparse.ArgumentParser(description="Eval monitor — detection sweep")
    ap.add_argument("--k", type=int, default=3, help="builds per case (worst-of-K)")
    ap.add_argument("--cases", default=str(EVAL_DIR / "cases.json"))
    ap.add_argument("--baseline", default=str(mon / "baseline.json"))
    ap.add_argument("--suppressions", default=str(mon / "suppressions.yaml"))
    ap.add_argument("--issues-dir", default=str(mon / "issues"))
    args = ap.parse_args(argv)

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
    baseline = load_baseline(args.baseline)
    suppressed = load_suppressions(args.suppressions)

    issues = run_detection(
        cases, baseline, [CoverageDropDetector()],
        k=args.k, build_fn=default_build_fn)
    issues = filter_suppressed(issues, suppressed)

    run_id = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        git_sha = "unknown"
    write_cards(issues, args.issues_dir, run_id=run_id, git_sha=git_sha)
    Path(args.issues_dir).mkdir(parents=True, exist_ok=True)
    (Path(args.issues_dir) / "digest.md").write_text(
        render_digest(issues), encoding="utf-8")
    print(f"[monitor] {len(issues)} issue(s); digest at {args.issues_dir}/digest.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```markdown
<!-- eval/monitor/README.md -->
# Eval monitor — detection core

Unattended detection sweep. Builds each case K times, scores must_cover coverage
against `baseline.json`, and writes issue cards + `issues/digest.md`. Reads-only:
it never modifies the engine.

Run manually:

    python3 -m eval.monitor.detect --k 3

Schedule weekly (local cron — must run where the corpus + Vertex ADC live):

    # crontab -e
    0 6 * * 1 cd /home/michael/PROJECTS/neuro-caseboard && python3 -m eval.monitor.detect >> eval/monitor/cron.log 2>&1

Triage by reading `eval/monitor/issues/digest.md`. To mute a known non-issue, add
its fingerprint to `suppressions.yaml`:

    - fingerprint: <16-hex from the card>
      reason: why this is not worth fixing
      expires: 2026-12-31   # optional; omit for permanent
```

- [ ] **Step 4: Run the digest test, then the full monitor suite**

Run: `python3 -m pytest tests/eval/monitor/test_digest.py -v`
Expected: PASS (2 passed)

Run: `python3 -m pytest tests/eval/monitor/ -v`
Expected: PASS (all monitor tests green: contracts, fingerprint, baseline, coverage_drop, suppress, detect, digest)

- [ ] **Step 5: Commit**

```bash
git add eval/monitor/digest.py eval/monitor/detect.py eval/monitor/README.md tests/eval/monitor/test_digest.py
git commit -m "feat(monitor): digest render + detect CLI + scheduling doc"
```

---

## Self-Review

**Spec coverage (against `2026-06-18-eval-monitor-loop-design.md`):**
- §3 `eval/monitor/` package, detect.py orchestration, issue cards + digest → Tasks 1–7. ✓
- §4 `Detector`/`Issue`/`RunArtifacts`/`Evidence`, fingerprint dedupe, on-disk card with status+provenance → Tasks 1, 2, 6. ✓
- §5 K-sampling (worst-of-K), relative-OR-absolute regression, baseline read-only, suppression with expiry, dedupe by fingerprint → Tasks 3, 4, 5, 6. ✓
- §5 "runs locally" scheduling → Task 7 README cron note. ✓
- §10 offline unit tests via injected `build_fn` → every task. ✓
- **Deferred (not in this milestone, by design):** grounded judge + unsupported-specific/flicker detectors (§7, Milestone 2); GATE 1 triage CLI (§6, Milestone 3); remediation runner + tier allowlist + GATE 2 + baseline advance (§6/§8, Milestone 4); mechanical planner-vs-author `locus` attribution (needs engine explorer-trace instrumentation — later milestone; M1 uses a fixed `locus="author"`).

**Placeholder scan:** no TBD/TODO; every code step contains complete, runnable code. ✓

**Type consistency:** `Issue`/`Evidence`/`RunArtifacts` fields are identical across Tasks 1, 4, 6, 7; `build_fn` signature (`(case_query: str) -> str`) is consistent in Tasks 6–7; `fingerprint(kind, locus, signature)` used identically in Tasks 2 and 4; `is_regression(before, after, *, rel_margin, abs_floor)` identical in Tasks 3 and 4. ✓

---

## Milestone roadmap (context for later plans)

- **M1 (this plan):** detection core — scheduled report + suppression.
- **M2:** grounded entailment judge (`judge.py`) + `unsupported_specific` and `flicker` detectors; calibration fixture.
- **M3:** GATE 1 triage CLI (`triage.py`) — approve@tier / suppress / defer + card status lifecycle.
- **M4:** remediation runner (`remediate.py`) — subagent dispatch, tier→allowlist diff-validation, full-sweep eval delta + pytest, PR open (GATE 2), baseline advance on merge.
