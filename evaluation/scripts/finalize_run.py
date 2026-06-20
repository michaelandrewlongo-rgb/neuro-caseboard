#!/usr/bin/env python3
"""Finalize a benchmark run directory into human-readable + analysis artifacts.

Reads ``<run-dir>/run.jsonl`` (+ ``run-config.json``) and writes, into the SAME run dir:
  - answers.md            human-readable: each question heading + full untruncated answer + citations
  - errors.log            every non-`completed` record (engine_error / timeout / not_gradable)
  - timing-summary.json   latency stats overall + per-domain, completion/error counts
  - disambiguation-log.jsonl   one line per question where a variant was selected

Idempotent and generic: usable for baseline AND post-improvement runs. Never mutates run.jsonl.

Run:  python3 evaluation/scripts/finalize_run.py --run-dir evaluation/runs/<run>
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
    return s[idx]


def write_answers_md(rows: list[dict], cfg: dict, out: Path) -> None:
    lines: list[str] = []
    lines.append("# Benchmark run — answers\n")
    lines.append(f"- run_id: `{cfg.get('run_id', '?')}`")
    lines.append(f"- application_commit: `{cfg.get('application_commit', '?')}`")
    lines.append(f"- model: {cfg.get('model_configuration', {})}")
    lines.append(f"- created_at: {cfg.get('created_at', '?')}\n")
    lines.append("Answers are reproduced in full (untruncated). Citations are listed as captured.\n")
    for r in rows:
        lines.append(f"## {r['question_id']} — {r.get('domain', '')}\n")
        lines.append(f"**Question:** {r['question']}\n")
        if r.get("selected_variant"):
            lines.append(f"**Disambiguation — selected variant:** {r['selected_variant']}\n")
        lines.append(f"**Status:** {r['status']}  |  **latency:** {r.get('latency_seconds', 0):.1f}s  "
                     f"|  **attempts:** {r.get('attempts', 1)}\n")
        ans = r.get("answer")
        if ans:
            lines.append(ans.rstrip() + "\n")
        else:
            lines.append(f"_No answer captured (status={r['status']}; "
                         f"error_details={r.get('error_details')!r})._\n")
        cits = r.get("citations") or []
        if cits:
            lines.append("\n**Citations:**\n")
            for c in cits:
                if isinstance(c, dict):
                    lines.append(f"- [{c.get('n','?')}] {c.get('book','')} — {c.get('chapter','')} "
                                 f"(p. {c.get('page','')})")
                else:
                    lines.append(f"- {c}")
            lines.append("")
        lines.append("\n---\n")
    out.write_text("\n".join(lines), encoding="utf-8")


def write_errors_log(rows: list[dict], out: Path) -> None:
    bad = [r for r in rows if r.get("status") != "completed"]
    lines = [f"# Error log — {len(bad)} non-completed record(s)\n"]
    for r in bad:
        lines.append(f"## {r['question_id']} — status={r['status']} attempts={r.get('attempts')}")
        lines.append(f"question: {r['question']}")
        lines.append(f"selected_variant: {r.get('selected_variant')}")
        lines.append(f"error_details: {r.get('error_details')!r}")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def write_timing_summary(rows: list[dict], out_json: Path, out_md: Path) -> dict:
    lat = [r.get("latency_seconds", 0.0) for r in rows]
    by_domain: dict[str, list[float]] = {}
    for r in rows:
        by_domain.setdefault(r.get("domain", "?"), []).append(r.get("latency_seconds", 0.0))
    status_counts: dict[str, int] = {}
    for r in rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    summary = {
        "n": len(rows),
        "completion_rate": round(status_counts.get("completed", 0) / len(rows), 4) if rows else 0,
        "status_counts": status_counts,
        "latency_overall": {
            "min": round(min(lat), 1) if lat else 0,
            "max": round(max(lat), 1) if lat else 0,
            "mean": round(statistics.mean(lat), 1) if lat else 0,
            "median": round(statistics.median(lat), 1) if lat else 0,
            "p95": round(pct(lat, 0.95), 1),
            "total_minutes": round(sum(lat) / 60, 1),
        },
        "latency_by_domain": {
            d: {"n": len(v), "median": round(statistics.median(v), 1), "max": round(max(v), 1)}
            for d, v in sorted(by_domain.items())
        },
        "disambiguations": sum(1 for r in rows if r.get("selected_variant")),
    }
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md = ["# Timing summary\n",
          f"- records: {summary['n']}",
          f"- completion rate: {summary['completion_rate']:.2%}",
          f"- status counts: {summary['status_counts']}",
          f"- latency overall (s): {summary['latency_overall']}",
          f"- disambiguations: {summary['disambiguations']}\n",
          "| domain | n | median s | max s |",
          "|---|---|---|---|"]
    for d, v in summary["latency_by_domain"].items():
        md.append(f"| {d} | {v['n']} | {v['median']} | {v['max']} |")
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    return summary


def write_disambiguation_log(rows: list[dict], out: Path) -> None:
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            if r.get("selected_variant"):
                fh.write(json.dumps({
                    "question_id": r["question_id"],
                    "question": r["question"],
                    "selected_variant": r["selected_variant"],
                    "status": r["status"],
                }, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Finalize a benchmark run directory.")
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    rows = load_jsonl(run_dir / "run.jsonl")
    cfg_path = run_dir / "run-config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}

    write_answers_md(rows, cfg, run_dir / "answers.md")
    write_errors_log(rows, run_dir / "errors.log")
    summary = write_timing_summary(rows, run_dir / "timing-summary.json", run_dir / "timing-summary.md")
    write_disambiguation_log(rows, run_dir / "disambiguation-log.jsonl")

    print(f"finalized {run_dir}: {summary['n']} records, "
          f"{summary['status_counts']}, {summary['disambiguations']} disambiguations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
