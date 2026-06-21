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
