#!/usr/bin/env python3
"""Compute deterministic grade summaries from a grades JSONL + the run directory.

Graders (LLM subspecialists) produce per-answer judgments; this script produces the NUMBERS, so
aggregation is reproducible and not itself an LLM artifact. Merges per-domain grade files if a
single merged file is not supplied.

Outputs (next to the merged grades file, default the run dir):
  - baseline-grades.jsonl     merged, schema-shaped grade records (if merging per-domain files)
  - baseline-grades.md        human-readable per-question grades
  - baseline-summary.json     overall + per-domain stats
  - baseline-summary.md       human-readable summary

Run:
  python3 evaluation/scripts/summarize_grades.py --run-dir evaluation/runs/<run> \
      --grades-glob 'evaluation/runs/<run>/grades/*.jsonl' --out-prefix baseline
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
from pathlib import Path

LETTERS = ["A", "B", "C", "D", "F", "Not gradable"]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def numeric_scores(grades: list[dict]) -> list[float]:
    return [g["score"] for g in grades if isinstance(g.get("score"), (int, float))]


def stats(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0, "mean": None, "median": None, "stddev": None}
    return {
        "n": len(xs),
        "mean": round(statistics.mean(xs), 2),
        "median": round(statistics.median(xs), 2),
        "stddev": round(statistics.pstdev(xs), 2) if len(xs) > 1 else 0.0,
    }


def is_unsafe(g: dict) -> bool:
    if (g.get("clinical_usability") or "").lower() == "unsafe":
        return True
    return bool(g.get("safety_critical_errors"))


def verification_coverage(grades: list[dict]) -> dict:
    total_anchors = 0
    verified = 0
    unavailable = 0
    for g in grades:
        for a in g.get("evidence_anchors") or []:
            total_anchors += 1
            vs = (a.get("verification_status") if isinstance(a, dict) else None) or ""
            if vs == "verified":
                verified += 1
            elif vs == "verification_unavailable":
                unavailable += 1
    return {
        "total_evidence_anchors": total_anchors,
        "verified": verified,
        "verification_unavailable": unavailable,
        "verified_fraction": round(verified / total_anchors, 3) if total_anchors else 0.0,
    }


def build_summary(grades: list[dict], run_rows: list[dict]) -> dict:
    by_domain: dict[str, list[dict]] = {}
    qid_domain = {r["question_id"]: r.get("domain", "?") for r in run_rows}
    qid_latency = {r["question_id"]: r.get("latency_seconds", 0.0) for r in run_rows}
    qid_status = {r["question_id"]: r.get("status") for r in run_rows}
    for g in grades:
        d = qid_domain.get(g["question_id"], g.get("domain", "?"))
        by_domain.setdefault(d, []).append(g)

    dist = {L: 0 for L in LETTERS}
    for g in grades:
        lg = g.get("letter_grade", "Not gradable")
        dist[lg] = dist.get(lg, 0) + 1

    lat = list(qid_latency.values())
    completion = sum(1 for s in qid_status.values() if s == "completed")
    summary = {
        "n_graded": len(grades),
        "n_run_records": len(run_rows),
        "overall_score": stats(numeric_scores(grades)),
        "grade_distribution": dist,
        "completion_rate": round(completion / len(run_rows), 4) if run_rows else 0,
        "error_rate": round(1 - completion / len(run_rows), 4) if run_rows else 0,
        "unsafe_answer_count": sum(1 for g in grades if is_unsafe(g)),
        "latency": {
            "median": round(statistics.median(lat), 1) if lat else 0,
            "p95": round(sorted(lat)[max(0, int(round(0.95 * (len(lat) - 1))))], 1) if lat else 0,
        },
        "evidence_verification": verification_coverage(grades),
        "by_domain": {
            d: {
                "score": stats(numeric_scores(gs)),
                "grade_distribution": {L: sum(1 for g in gs if g.get("letter_grade") == L) for L in LETTERS if any(g.get("letter_grade") == L for g in gs)},
                "unsafe": sum(1 for g in gs if is_unsafe(g)),
            }
            for d, gs in sorted(by_domain.items())
        },
    }
    return summary


def write_summary_md(summary: dict, out: Path) -> None:
    s = summary["overall_score"]
    md = ["# Baseline grading summary\n",
          f"- answers graded: {summary['n_graded']} / {summary['n_run_records']}",
          f"- **overall score**: mean {s['mean']}, median {s['median']}, stddev {s['stddev']} (n={s['n']})",
          f"- grade distribution: {summary['grade_distribution']}",
          f"- completion rate: {summary['completion_rate']:.2%} | error rate: {summary['error_rate']:.2%}",
          f"- **unsafe answers**: {summary['unsafe_answer_count']}",
          f"- latency: median {summary['latency']['median']}s, p95 {summary['latency']['p95']}s",
          f"- evidence verification: {summary['evidence_verification']}\n",
          "## Per-domain\n",
          "| domain | n | mean | median | stddev | unsafe | distribution |",
          "|---|---|---|---|---|---|---|"]
    for d, v in summary["by_domain"].items():
        sc = v["score"]
        md.append(f"| {d} | {sc['n']} | {sc['mean']} | {sc['median']} | {sc['stddev']} | {v['unsafe']} | {v['grade_distribution']} |")
    out.write_text("\n".join(md) + "\n", encoding="utf-8")


def write_grades_md(grades: list[dict], out: Path) -> None:
    lines = ["# Baseline grades (per question)\n"]
    for g in sorted(grades, key=lambda x: x["question_id"]):
        lines.append(f"## {g['question_id']} — {g.get('letter_grade','?')} / {g.get('score','?')}\n")
        lines.append(f"**Clinical usability:** {g.get('clinical_usability','?')}\n")
        lines.append(f"**Reason:** {g.get('reason','')}\n")
        for key, label in [("got_right", "Got right"),
                           ("important_inaccuracies", "Important inaccuracies"),
                           ("safety_critical_errors", "Safety-critical errors"),
                           ("outdated_claims", "Outdated claims"),
                           ("missing_content", "Missing content"),
                           ("overabsolute_claims", "Over-absolute claims")]:
            items = g.get(key) or []
            if items:
                lines.append(f"**{label}:**")
                lines.extend(f"- {it}" for it in items)
                lines.append("")
        lines.append("\n---\n")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--grades-glob", help="glob of per-domain grade JSONL files to merge")
    ap.add_argument("--grades-file", help="single merged grades JSONL (instead of glob)")
    ap.add_argument("--out-prefix", default="baseline")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    run_rows = load_jsonl(run_dir / "run.jsonl")

    grades: list[dict] = []
    if args.grades_file:
        grades = load_jsonl(Path(args.grades_file))
    else:
        for fp in sorted(glob.glob(args.grades_glob or str(run_dir / "grades" / "*.jsonl"))):
            grades.extend(load_jsonl(Path(fp)))

    # de-dup by question_id (last wins) and merge
    by_id = {g["question_id"]: g for g in grades}
    grades = [by_id[k] for k in sorted(by_id)]

    merged = run_dir / f"{args.out_prefix}-grades.jsonl"
    with merged.open("w", encoding="utf-8") as fh:
        for g in grades:
            fh.write(json.dumps(g, ensure_ascii=False) + "\n")

    summary = build_summary(grades, run_rows)
    (run_dir / f"{args.out_prefix}-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_summary_md(summary, run_dir / f"{args.out_prefix}-summary.md")
    write_grades_md(grades, run_dir / f"{args.out_prefix}-grades.md")

    print(f"merged {len(grades)} grades -> {merged}")
    print(f"overall: {summary['overall_score']}, dist {summary['grade_distribution']}, unsafe {summary['unsafe_answer_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
