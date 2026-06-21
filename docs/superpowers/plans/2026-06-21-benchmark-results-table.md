# 67-Q Benchmark Results Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A self-explanatory `evaluation/RESULTS.md` table — baseline + one row per full 67-Q run (one row per arm for A/B) — kept current by `evaluation/scripts/update_results.py`, which upserts rows from existing run outputs.

**Architecture:** One CLI script. Pure functions build/parse/render a markdown table (Δ vs baseline computed at render time); thin extractors turn a single-arm `*-summary.json` or an A/B run dir into `Row`s; `write_results` preserves the file's plain-language preamble and upserts rows keyed by the Run cell. No engine/LLM/network — reads existing files only.

**Tech Stack:** Python 3.12 stdlib (`json`, `dataclasses`, `argparse`, `pathlib`, `statistics`), pytest.

## Global Constraints

- Stdlib only — no new dependencies.
- Reads existing run outputs only; never runs the engine, an LLM, or the network.
- Interpreter is `python3`. Run tests with `PYTHONPATH=vendor/caseprep python3 -m pytest <files> -v` (the vendored caseprep prefix is harmless for these tests and matches the session convention); never the full suite (~17 min). Never add `pytest-xdist`.
- Tests live under `tests/evaluation/` and use `tmp_path` (hermetic, no real run dirs mutated).
- `Mean` renders with 2 decimals; `Δ vs base` is signed 2 decimals (`+1.62`), `—` for the baseline row or when no baseline exists.
- The baseline row is identified by its `Change` cell equal to `baseline` (case-insensitive) and always renders first.
- Upsert key is the exact `Run` cell text (which encodes the arm for A/B, e.g. `youmans-full67-20260620-2210 · youmans`).
- Canonical single-arm fields: `overall_score.{n,mean}`, `grade_distribution.{A,B,C,D,F,"Not gradable"}`, `unsafe_answer_count` (from `<prefix>-summary.json`); `application_commit`, `working_tree_dirty`, `created_at` (from `run-config.json`).
- A/B fields: arms from `grading/keymap.json` key `arms`; per-arm `ab-out/<arm>-grades.jsonl` records `{question_id, score, letter_grade}` (no unsafe field → `Unsafe` renders `—`).

---

### Task 1: Row model, table render + parse (pure)

**Files:**
- Create: `evaluation/scripts/update_results.py`
- Test: `tests/evaluation/test_results_table.py`

**Interfaces:**
- Produces:
  - `@dataclass Row` with fields: `run: str`, `date: str`, `change: str`, `commit: str`, `n: str`, `mean: float`, `grades: str`, `unsafe: str`, `notes: str`. Property `is_baseline -> bool` = `self.change.strip().lower() == "baseline"`.
  - `COLUMNS: list[str]` = `["Run","Date","Change","Commit","n","Mean","Δ vs base","A/B/C/D","Unsafe","Notes"]`.
  - `render_table(rows: list[Row]) -> str` — header + separator + rows; baseline row first; `Δ vs base` computed against the baseline row's mean (`—` if no baseline).
  - `parse_table(md: str) -> list[Row]` — read rows from a rendered table back into `Row`s (ignores the derived `Δ vs base` cell).

- [ ] **Step 1: Write the failing test**

Create `tests/evaluation/test_results_table.py`:

```python
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "update_results",
    Path(__file__).resolve().parents[2] / "evaluation" / "scripts" / "update_results.py",
)
ur = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ur)


def _row(run, change, mean, **kw):
    return ur.Row(run=run, date=kw.get("date", "2026-06-20"), change=change,
                  commit=kw.get("commit", "abc1234"), n=kw.get("n", "66"),
                  mean=mean, grades=kw.get("grades", "0/38/22/6"),
                  unsafe=kw.get("unsafe", "0"), notes=kw.get("notes", ""))


def test_render_marks_baseline_dash_and_computes_delta():
    rows = [_row("base", "baseline", 77.74), _row("run2", "C5 guard", 79.36)]
    md = ur.render_table(rows)
    lines = [ln for ln in md.splitlines() if ln.startswith("|")]
    # header, separator, 2 data rows
    assert "Δ vs base" in lines[0]
    assert "| — |" in lines[2]              # baseline delta is a dash
    assert "+1.62" in lines[3]              # 79.36 - 77.74


def test_render_baseline_first_regardless_of_order():
    rows = [_row("run2", "C5 guard", 79.36), _row("base", "baseline", 77.74)]
    md = ur.render_table(rows)
    data = [ln for ln in md.splitlines() if ln.startswith("|")][2:]
    assert "baseline" in data[0]            # baseline pulled to the top


def test_render_no_baseline_all_delta_dash():
    md = ur.render_table([_row("r", "some change", 80.0)])
    data = [ln for ln in md.splitlines() if ln.startswith("|")][2:]
    assert data[0].count("| — |") >= 1      # delta dash when no baseline row


def test_parse_round_trip():
    rows = [_row("base", "baseline", 77.74), _row("run2", "C5 guard", 79.36, notes="keep")]
    parsed = ur.parse_table(ur.render_table(rows))
    assert [r.run for r in parsed] == ["base", "run2"]
    assert parsed[0].is_baseline and not parsed[1].is_baseline
    assert abs(parsed[1].mean - 79.36) < 1e-9
    assert parsed[1].notes == "keep"
    assert parsed[1].grades == "0/38/22/6"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=vendor/caseprep python3 -m pytest tests/evaluation/test_results_table.py -v`
Expected: FAIL — `update_results.py` does not exist (exec_module raises FileNotFoundError).

- [ ] **Step 3: Write minimal implementation**

Create `evaluation/scripts/update_results.py`:

```python
#!/usr/bin/env python3
"""Maintain evaluation/RESULTS.md — a self-explanatory log of every full 67-Q benchmark run.

One row per run (one per arm for A/B). Reads existing run outputs only (no engine/LLM/network);
upserts a row keyed by the Run cell and recomputes the Δ-vs-baseline column at render time."""
from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass
from pathlib import Path

COLUMNS = ["Run", "Date", "Change", "Commit", "n", "Mean", "Δ vs base",
           "A/B/C/D", "Unsafe", "Notes"]


@dataclass
class Row:
    run: str
    date: str
    change: str
    commit: str
    n: str
    mean: float
    grades: str
    unsafe: str
    notes: str

    @property
    def is_baseline(self) -> bool:
        return self.change.strip().lower() == "baseline"


def _ordered(rows: list[Row]) -> list[Row]:
    base = [r for r in rows if r.is_baseline]
    rest = [r for r in rows if not r.is_baseline]
    return base + rest


def render_table(rows: list[Row]) -> str:
    rows = _ordered(rows)
    base_mean = next((r.mean for r in rows if r.is_baseline), None)
    out = ["| " + " | ".join(COLUMNS) + " |",
           "|" + "|".join(["---"] * len(COLUMNS)) + "|"]
    for r in rows:
        if r.is_baseline or base_mean is None:
            delta = "—"
        else:
            delta = f"{r.mean - base_mean:+.2f}"
        cells = [r.run, r.date, r.change, r.commit, r.n, f"{r.mean:.2f}",
                 delta, r.grades, r.unsafe, r.notes]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def parse_table(md: str) -> list[Row]:
    rows: list[Row] = []
    for line in md.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) != len(COLUMNS):
            continue
        if cells[0] == "Run" or set(cells[0]) <= {"-"}:
            continue  # header or separator
        run, date, change, commit, n, mean, _delta, grades, unsafe, notes = cells
        try:
            mean_f = float(mean)
        except ValueError:
            continue
        rows.append(Row(run=run, date=date, change=change, commit=commit, n=n,
                        mean=mean_f, grades=grades, unsafe=unsafe, notes=notes))
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=vendor/caseprep python3 -m pytest tests/evaluation/test_results_table.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add evaluation/scripts/update_results.py tests/evaluation/test_results_table.py
git commit -m "feat(eval): Row model + RESULTS.md table render/parse with baseline-first Δ"
```

---

### Task 2: write_results — preamble-preserving upsert to disk

**Files:**
- Modify: `evaluation/scripts/update_results.py`
- Test: `tests/evaluation/test_results_write.py`

**Interfaces:**
- Consumes: `Row`, `render_table`, `parse_table`, `COLUMNS` (Task 1).
- Produces:
  - `PREAMBLE: str` — the plain-language header text (ends with two newlines before the table).
  - `FOOTER: str` — a fenced code block showing the `update_results.py` usage.
  - `write_results(path: Path, new_rows: list[Row]) -> None` — if `path` is missing, create it as `PREAMBLE + table + "\n\n" + FOOTER`. Otherwise split the existing file into preamble / table / footer, parse existing rows, upsert `new_rows` by the `run` cell (replace-or-append), re-render the table, and write back with the original preamble and footer preserved.

- [ ] **Step 1: Write the failing test**

Create `tests/evaluation/test_results_write.py`:

```python
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "update_results",
    Path(__file__).resolve().parents[2] / "evaluation" / "scripts" / "update_results.py",
)
ur = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ur)


def _row(run, change, mean, notes=""):
    return ur.Row(run=run, date="2026-06-20", change=change, commit="abc1234",
                  n="66", mean=mean, grades="0/38/22/6", unsafe="0", notes=notes)


def test_creates_file_with_preamble_and_row(tmp_path):
    p = tmp_path / "RESULTS.md"
    ur.write_results(p, [_row("base", "baseline", 77.74)])
    text = p.read_text()
    assert text.startswith("# 67-Question Benchmark")   # preamble present
    assert "Unsafe" in text and "must stay" in text     # explains itself
    assert "| base |" in text
    assert "update_results.py" in text                  # footer usage block


def test_upsert_is_idempotent(tmp_path):
    p = tmp_path / "RESULTS.md"
    ur.write_results(p, [_row("base", "baseline", 77.74)])
    ur.write_results(p, [_row("run2", "C5 guard", 79.36)])
    ur.write_results(p, [_row("run2", "C5 guard", 81.00, notes="rescored")])  # same run id
    text = p.read_text()
    assert text.count("| run2 |") == 1                  # updated, not duplicated
    assert "81.00" in text and "79.36" not in text
    assert "+3.26" in text                              # 81.00 - 77.74, Δ recomputed


def test_preamble_preserved_across_upserts(tmp_path):
    p = tmp_path / "RESULTS.md"
    ur.write_results(p, [_row("base", "baseline", 77.74)])
    first = p.read_text().split("| Run |")[0]
    ur.write_results(p, [_row("run2", "C5 guard", 79.36)])
    second = p.read_text().split("| Run |")[0]
    assert first == second                              # preamble byte-identical
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=vendor/caseprep python3 -m pytest tests/evaluation/test_results_write.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'write_results'`.

- [ ] **Step 3: Write minimal implementation**

Append to `evaluation/scripts/update_results.py`:

```python
PREAMBLE = """# 67-Question Benchmark — Run Results

One row per full run of the frozen 67-question neurosurgery benchmark. The **baseline** row is the
reference point; every other row shows what changed and how the score moved.

**How to read it:** **Mean** is the average answer score from 0–100 (higher is better). **Δ vs
base** is this run's mean minus the baseline's — positive means better than baseline. **Unsafe** is
the count of answers a grader flagged as unsafe; this must stay **0**. **A/B/C/D** is how many
answers earned each letter grade. Small mean differences (±2–3) are usually run-to-run noise, not a
real change.

**How it's updated:** after a full run, `evaluation/scripts/update_results.py` adds or refreshes
that run's row from its score files (see the command at the bottom). Do not hand-edit rows.

"""

FOOTER = """

---

Update a row after a full run:

```bash
# single-arm run (canonical *-summary.json):
python3 evaluation/scripts/update_results.py \\
    --summary evaluation/runs/<run>/<prefix>-summary.json \\
    --run <run-dir-name> --label "<what changed>"   # add --baseline for the anchor row

# A/B run (one row per arm, read from grading/keymap.json + ab-out/<arm>-grades.jsonl):
python3 evaluation/scripts/update_results.py --ab evaluation/runs/<run> --label "<what changed>"
```
"""

_TABLE_HEADER = "| " + " | ".join(COLUMNS) + " |"


def _split_existing(text: str) -> tuple[str, list[Row], str]:
    """Return (preamble, parsed_rows, footer) for an existing RESULTS.md."""
    lines = text.splitlines()
    tbl_idx = [i for i, ln in enumerate(lines) if ln.strip().startswith("| Run |")]
    if not tbl_idx:
        return text, [], ""
    start = tbl_idx[0]
    end = start
    while end < len(lines) and lines[end].strip().startswith("|"):
        end += 1
    preamble = "\n".join(lines[:start])
    table_md = "\n".join(lines[start:end])
    footer = "\n".join(lines[end:])
    return preamble, parse_table(table_md), footer


def write_results(path: Path, new_rows: list[Row]) -> None:
    if path.exists():
        preamble, rows, footer = _split_existing(path.read_text())
    else:
        preamble, rows, footer = PREAMBLE, [], FOOTER
    by_key = {r.run: r for r in rows}
    for r in new_rows:
        by_key[r.run] = r
    table = render_table(list(by_key.values()))
    body = preamble.rstrip("\n") + "\n\n" + table + "\n" + footer.rstrip("\n") + "\n"
    path.write_text(body)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=vendor/caseprep python3 -m pytest tests/evaluation/test_results_write.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add evaluation/scripts/update_results.py tests/evaluation/test_results_write.py
git commit -m "feat(eval): write_results upsert preserving the self-explaining preamble"
```

---

### Task 3: Single-arm extractor + CLI `--summary`

**Files:**
- Modify: `evaluation/scripts/update_results.py`
- Test: `tests/evaluation/test_results_summary.py`

**Interfaces:**
- Consumes: `Row`, `write_results` (Tasks 1–2).
- Produces:
  - `row_from_summary(summary_path: Path, run: str, label: str, *, commit: str | None = None, date: str | None = None, note: str = "", baseline: bool = False) -> Row` — reads `overall_score.{n,mean}`, `grade_distribution`, `unsafe_answer_count`; when `commit`/`date` are None, fills them from a sibling `run-config.json` if present (`application_commit` short + ` dirty` if `working_tree_dirty`; `created_at` date part). `change` is `"baseline"` when `baseline` else `label`. Grades cell is `"{A}/{B}/{C}/{D}"`; if `"Not gradable"` > 0 and `note` is empty, set note to `"{k} not-gradable"`.
  - `main(argv=None)` wiring `--summary/--run/--label/--commit/--date/--note/--baseline` → `row_from_summary` → `write_results(Path("evaluation/RESULTS.md"), [row])`. (A/B flags added in Task 4.)

- [ ] **Step 1: Write the failing test**

Create `tests/evaluation/test_results_summary.py`:

```python
import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "update_results",
    Path(__file__).resolve().parents[2] / "evaluation" / "scripts" / "update_results.py",
)
ur = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ur)


def _write_summary(d: Path, mean=77.74, ng=0):
    (d / "s-summary.json").write_text(json.dumps({
        "overall_score": {"n": 66, "mean": mean},
        "grade_distribution": {"A": 0, "B": 38, "C": 22, "D": 6, "F": 0, "Not gradable": ng},
        "unsafe_answer_count": 0,
    }))
    (d / "run-config.json").write_text(json.dumps({
        "application_commit": "28a6e30ab5b2697acc4dafe0a46824c8c3c42e6a",
        "working_tree_dirty": True,
        "created_at": "2026-06-20T13:47:23.871700+00:00",
    }))


def test_row_from_summary_reads_metrics_and_runconfig(tmp_path):
    _write_summary(tmp_path)
    row = ur.row_from_summary(tmp_path / "s-summary.json", run="baseline-x",
                              label="baseline", baseline=True)
    assert row.is_baseline
    assert abs(row.mean - 77.74) < 1e-9
    assert row.n == "66"
    assert row.grades == "0/38/22/6"
    assert row.unsafe == "0"
    assert row.commit == "28a6e30 dirty"        # short sha + dirty marker
    assert row.date == "2026-06-20"


def test_row_from_summary_notes_not_gradable(tmp_path):
    _write_summary(tmp_path, ng=1)
    row = ur.row_from_summary(tmp_path / "s-summary.json", run="r", label="chg")
    assert row.change == "chg"
    assert "1 not-gradable" in row.notes


def test_cli_summary_writes_results(tmp_path, monkeypatch):
    _write_summary(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evaluation").mkdir()
    rc = ur.main(["--summary", str(tmp_path / "s-summary.json"),
                  "--run", "baseline-x", "--label", "baseline", "--baseline"])
    assert rc == 0
    text = (tmp_path / "evaluation" / "RESULTS.md").read_text()
    assert "| baseline-x |" in text and "77.74" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=vendor/caseprep python3 -m pytest tests/evaluation/test_results_summary.py -v`
Expected: FAIL — `AttributeError: ... 'row_from_summary'`.

- [ ] **Step 3: Write minimal implementation**

Append to `evaluation/scripts/update_results.py`:

```python
def _commit_from_config(cfg: dict) -> str:
    sha = (cfg.get("application_commit") or "")[:7]
    if cfg.get("working_tree_dirty"):
        sha = (sha + " dirty").strip()
    return sha


def row_from_summary(summary_path: Path, run: str, label: str, *,
                     commit: str | None = None, date: str | None = None,
                     note: str = "", baseline: bool = False) -> Row:
    data = json.loads(Path(summary_path).read_text())
    score = data.get("overall_score") or {}
    gd = data.get("grade_distribution") or {}
    cfg = {}
    cfg_path = Path(summary_path).parent / "run-config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text())
    if commit is None:
        commit = _commit_from_config(cfg)
    if date is None:
        date = (cfg.get("created_at") or "")[:10]
    grades = f"{gd.get('A', 0)}/{gd.get('B', 0)}/{gd.get('C', 0)}/{gd.get('D', 0)}"
    ng = gd.get("Not gradable", 0)
    if ng and not note:
        note = f"{ng} not-gradable"
    return Row(run=run, date=date, change=("baseline" if baseline else label),
               commit=commit, n=str(score.get("n", "")),
               mean=float(score.get("mean", 0.0)), grades=grades,
               unsafe=str(data.get("unsafe_answer_count", "—")), notes=note)


_RESULTS_PATH = Path("evaluation/RESULTS.md")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Upsert a row into evaluation/RESULTS.md")
    ap.add_argument("--summary", help="path to a single-arm <prefix>-summary.json")
    ap.add_argument("--ab", help="path to an A/B run dir (one row per arm)")
    ap.add_argument("--run", help="run id / dir name (single-arm mode)")
    ap.add_argument("--label", required=True, help="plain-language change descriptor")
    ap.add_argument("--commit", default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("--note", default="")
    ap.add_argument("--decision", choices=["keep", "revert"], default=None)
    ap.add_argument("--baseline", action="store_true")
    args = ap.parse_args(argv)

    note = args.note
    if args.decision:
        note = (note + f"; {args.decision}").strip("; ") if note else args.decision

    if args.summary:
        row = row_from_summary(Path(args.summary), run=args.run, label=args.label,
                               commit=args.commit, date=args.date, note=note,
                               baseline=args.baseline)
        write_results(_RESULTS_PATH, [row])
        return 0
    if args.ab:
        rows = rows_from_ab(Path(args.ab), label=args.label, note=note)
        write_results(_RESULTS_PATH, rows)
        return 0
    ap.error("one of --summary or --ab is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=vendor/caseprep python3 -m pytest tests/evaluation/test_results_summary.py -v`
Expected: PASS (3 tests). (Note: `main` references `rows_from_ab`, added in Task 4; the `--summary` path under test never calls it, so these tests pass. If running the `--ab` branch before Task 4, it would raise `NameError` — not exercised here.)

- [ ] **Step 5: Commit**

```bash
git add evaluation/scripts/update_results.py tests/evaluation/test_results_summary.py
git commit -m "feat(eval): single-arm summary extractor + update_results CLI"
```

---

### Task 4: A/B extractor + CLI `--ab`

**Files:**
- Modify: `evaluation/scripts/update_results.py`
- Test: `tests/evaluation/test_results_ab.py`

**Interfaces:**
- Consumes: `Row`, `write_results`, `main` (Tasks 1–3).
- Produces:
  - `rows_from_ab(run_dir: Path, label: str, *, note: str = "") -> list[Row]` — reads `grading/keymap.json` (`arms` list); for each arm reads `ab-out/<arm>-grades.jsonl` (one JSON object per line with `score` and `letter_grade`), computes `mean` of scores, `n`, and grade counts. `run` cell = `f"{run_dir.name} · {arm}"`; `change` = `f"{label} ({arm})"`; `unsafe` = `"—"` (A/B grades carry no unsafe flag). Commit/date come from the run dir's `run-config.json` when present.

- [ ] **Step 1: Write the failing test**

Create `tests/evaluation/test_results_ab.py`:

```python
import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "update_results",
    Path(__file__).resolve().parents[2] / "evaluation" / "scripts" / "update_results.py",
)
ur = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ur)


def _make_ab(tmp_path):
    run = tmp_path / "myab-20260620-2210"
    (run / "grading").mkdir(parents=True)
    (run / "ab-out").mkdir()
    (run / "grading" / "keymap.json").write_text(json.dumps(
        {"arms": ["recent", "youmans"], "questions": {}}))
    (run / "run-config.json").write_text(json.dumps(
        {"application_commit": "deadbeef1234", "working_tree_dirty": False,
         "created_at": "2026-06-20T22:10:00+00:00"}))

    def _grades(arm, scores, letters):
        lines = [json.dumps({"question_id": f"Q{i}", "score": s, "letter_grade": g})
                 for i, (s, g) in enumerate(zip(scores, letters))]
        (run / "ab-out" / f"{arm}-grades.jsonl").write_text("\n".join(lines) + "\n")

    _grades("recent", [80, 90], ["B", "A"])     # mean 85.0
    _grades("youmans", [70, 80], ["C", "B"])    # mean 75.0
    return run


def test_rows_from_ab_one_row_per_arm(tmp_path):
    run = _make_ab(tmp_path)
    rows = ur.rows_from_ab(run, label="3-arm corpus")
    by_run = {r.run: r for r in rows}
    assert set(by_run) == {f"{run.name} · recent", f"{run.name} · youmans"}
    recent = by_run[f"{run.name} · recent"]
    assert abs(recent.mean - 85.0) < 1e-9
    assert recent.n == "2"
    assert recent.grades == "1/1/0/0"            # A=1,B=1,C=0,D=0
    assert recent.unsafe == "—"                  # no unsafe field in A/B grades
    assert recent.change == "3-arm corpus (recent)"
    assert recent.commit == "deadbee"            # clean tree -> no dirty marker
    assert recent.date == "2026-06-20"


def test_cli_ab_writes_two_rows(tmp_path, monkeypatch):
    run = _make_ab(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evaluation").mkdir()
    rc = ur.main(["--ab", str(run), "--label", "3-arm corpus"])
    assert rc == 0
    text = (tmp_path / "evaluation" / "RESULTS.md").read_text()
    assert f"| {run.name} · recent |" in text
    assert f"| {run.name} · youmans |" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=vendor/caseprep python3 -m pytest tests/evaluation/test_results_ab.py -v`
Expected: FAIL — `AttributeError: ... 'rows_from_ab'`.

- [ ] **Step 3: Write minimal implementation**

Append to `evaluation/scripts/update_results.py` (above the `if __name__` guard):

```python
def rows_from_ab(run_dir: Path, label: str, *, note: str = "") -> list[Row]:
    run_dir = Path(run_dir)
    keymap = json.loads((run_dir / "grading" / "keymap.json").read_text())
    arms = keymap.get("arms", [])
    cfg = {}
    cfg_path = run_dir / "run-config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text())
    commit = _commit_from_config(cfg)
    date = (cfg.get("created_at") or "")[:10]
    rows: list[Row] = []
    for arm in arms:
        gpath = run_dir / "ab-out" / f"{arm}-grades.jsonl"
        if not gpath.exists():
            continue
        scores, counts = [], {"A": 0, "B": 0, "C": 0, "D": 0}
        for line in gpath.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("score") is not None:
                scores.append(float(rec["score"]))
            lg = (rec.get("letter_grade") or "").strip().upper()
            if lg in counts:
                counts[lg] += 1
        mean = statistics.mean(scores) if scores else 0.0
        grades = f"{counts['A']}/{counts['B']}/{counts['C']}/{counts['D']}"
        rows.append(Row(run=f"{run_dir.name} · {arm}", date=date,
                        change=f"{label} ({arm})", commit=commit,
                        n=str(len(scores)), mean=mean, grades=grades,
                        unsafe="—", notes=note))
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=vendor/caseprep python3 -m pytest tests/evaluation/test_results_ab.py tests/evaluation/ -v`
Expected: PASS (all evaluation tests, including Tasks 1–3).

- [ ] **Step 5: Commit**

```bash
git add evaluation/scripts/update_results.py tests/evaluation/test_results_ab.py
git commit -m "feat(eval): A/B extractor (one row per arm) for update_results"
```

---

### Task 5: Seed real runs, generate RESULTS.md, wire into skill + reproduce doc

**Files:**
- Create: `evaluation/RESULTS.md` (generated, then committed)
- Modify: `.claude/skills/neuro-caseboard-ab-test/SKILL.md`, `NEURO_CASEBOARD_EVALUATION.md`

**Interfaces:**
- Consumes: the finished `update_results.py` CLI.

- [ ] **Step 1: Seed the three existing runs**

Run from the worktree root:

```bash
python3 evaluation/scripts/update_results.py \
  --summary evaluation/runs/baseline-20260620-134705/baseline-summary.json \
  --run baseline-20260620-134705 --label baseline --baseline

python3 evaluation/scripts/update_results.py \
  --summary evaluation/runs/post-improvement-20260620-182930/post-summary.json \
  --run post-improvement-20260620-182930 --label "C5 empty-answer guard" \
  --note "delta within run-to-run noise"

python3 evaluation/scripts/update_results.py \
  --ab evaluation/runs/youmans-full67-20260620-2210 \
  --label "3-arm corpus A/B" --note "length confound on composed arm"
```

- [ ] **Step 2: Verify the generated table**

Run: `cat evaluation/RESULTS.md`
Expected: a preamble, a table whose first data row is `baseline-20260620-134705` with `Mean` `77.74` and `Δ vs base` `—`; a `post-improvement-…` row with `Δ` `+1.62`; three `youmans-full67-… · {recent,youmans,youmans_pubmed}` rows each with a Δ vs the baseline mean; and the footer usage block. Confirm no row is duplicated.

If the post-improvement summary file has a different prefix, locate it first:
`ls evaluation/runs/post-improvement-20260620-182930/*summary.json` and use that exact path.

- [ ] **Step 3: Wire the updater into the ab-test skill**

In `.claude/skills/neuro-caseboard-ab-test/SKILL.md`, in step 7 (Export & verdict), add this line after the export instruction:

```markdown
- **Record the run in the results table** so it is never lost: run
  `python3 evaluation/scripts/update_results.py --ab evaluation/runs/<run> --label "<what changed>"`
  (or the `--summary <…-summary.json> --run <run> --label "<what changed>"` form for a single-arm
  run). This upserts one row per arm into `evaluation/RESULTS.md`.
```

- [ ] **Step 4: Wire the updater into the reproduce block**

In `NEURO_CASEBOARD_EVALUATION.md`, at the end of the "Reproduce" bash block, append:

```bash
# 7) record this run in the results table (evaluation/RESULTS.md)
python3 evaluation/scripts/update_results.py \
    --summary "$RUN"/<prefix>-summary.json --run "$(basename "$RUN")" --label "<what changed>"
```

- [ ] **Step 5: Commit**

```bash
git add evaluation/RESULTS.md .claude/skills/neuro-caseboard-ab-test/SKILL.md NEURO_CASEBOARD_EVALUATION.md
git commit -m "feat(eval): seed RESULTS.md (3 runs) and wire update_results into the ab-test flow"
```

---

## Self-Review

**Spec coverage:**
- Self-explanatory `evaluation/RESULTS.md` with preamble → Task 2 (PREAMBLE) + Task 5 (generated).
- Baseline first, one row per run, per-arm for A/B → Task 1 (render `_ordered`), Task 4 (per-arm rows).
- Change label distinguishes runs → Tasks 3/4 (`--label`, baseline label).
- Script upsert keyed by (run,arm), Δ recompute → Tasks 1–2.
- Single-arm + A/B input modes → Tasks 3 + 4.
- Seed 3 existing runs → Task 5.
- Wire into ab-test skill + reproduce block → Task 5.
- Tests (single-arm row, baseline+Δ, idempotency, baseline pinned, A/B expansion, missing file, preamble preserved) → Tasks 1–4. ✓

**Placeholder scan:** No TBD/TODO; every code/test step is complete. The `<prefix>` tokens in Task 5 docs are literal documentation placeholders for the operator (the seed commands use real paths). ✓

**Type consistency:** `Row` fields and `is_baseline` consistent across tasks; `render_table`/`parse_table`/`write_results`/`row_from_summary`/`rows_from_ab`/`main` signatures match their consumers; `_commit_from_config` defined in Task 3 and reused in Task 4; `main` (Task 3) references `rows_from_ab` resolved in Task 4 (noted). ✓
