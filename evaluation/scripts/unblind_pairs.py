#!/usr/bin/env python3
"""Unblind paired grades and compute the A/B verdict (deterministic NUMBERS, not an LLM artifact).

Reads the keymap (A/B → arm), the blinded paired grades JSONL (one object per question_id as
emitted by build_blinded_pairs.py graders), and both run.jsonl files (for latency). Produces a
per-question comparison + an overall verdict: mean baseline, mean treatment, mean paired delta,
head-to-head record, regressions (baseline beat treatment), new safety errors, and the
latency/cost read per arm.

Usage:
  unblind_pairs.py --keymap DIR/keymap.json --grades GRADES.jsonl \
      --baseline-run B/run.jsonl --treatment-run T/run.jsonl --out-prefix DIR/ab
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def latencies(run_jsonl: Path) -> dict:
    lat = {}
    for r in load_jsonl(run_jsonl):
        if r.get("status") == "completed":
            lat[r["question_id"]] = r.get("latency_seconds", 0.0) or 0.0
    return lat


def lat_stats(vals):
    vals = [v for v in vals if v]
    if not vals:
        return {"n": 0, "median": 0, "p95": 0, "mean": 0}
    s = sorted(vals)
    return {"n": len(vals), "median": round(statistics.median(s), 1),
            "p95": round(s[max(0, int(round(0.95 * (len(s) - 1))))], 1),
            "mean": round(statistics.mean(s), 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keymap", required=True)
    ap.add_argument("--grades", required=True)
    ap.add_argument("--baseline-run", required=True)
    ap.add_argument("--treatment-run", required=True)
    ap.add_argument("--out-prefix", required=True)
    args = ap.parse_args(argv)

    keymap = json.loads(Path(args.keymap).read_text(encoding="utf-8"))
    grades = {g["question_id"]: g for g in load_jsonl(Path(args.grades))}
    base_lat = latencies(Path(args.baseline_run))
    treat_lat = latencies(Path(args.treatment_run))

    rows = []
    for qid, g in sorted(grades.items()):
        km = keymap.get(qid)
        if not km:
            continue
        sA, sB = g.get("score_A"), g.get("score_B")
        score = {km["A"]: sA, km["B"]: sB}
        bscore, tscore = score.get("baseline"), score.get("treatment")
        better_arm = km.get(g.get("better")) if g.get("better") in ("A", "B") else "tie"
        delta = (tscore - bscore) if (isinstance(tscore, (int, float)) and isinstance(bscore, (int, float))) else None
        rows.append({"question_id": qid, "domain": km.get("domain", "?"),
                     "baseline": bscore, "treatment": tscore, "delta": delta,
                     "winner": better_arm, "margin": g.get("margin"),
                     "new_safety": km.get(g.get("any_new_safety_errors"), g.get("any_new_safety_errors")),
                     "rationale": g.get("rationale", "")})

    deltas = [r["delta"] for r in rows if isinstance(r["delta"], (int, float))]
    bvals = [r["baseline"] for r in rows if isinstance(r["baseline"], (int, float))]
    tvals = [r["treatment"] for r in rows if isinstance(r["treatment"], (int, float))]
    t_wins = sum(1 for r in rows if r["winner"] == "treatment")
    b_wins = sum(1 for r in rows if r["winner"] == "baseline")
    ties = sum(1 for r in rows if r["winner"] == "tie")
    regressions = [r for r in rows if isinstance(r["delta"], (int, float)) and r["delta"] < 0]
    new_safety = [r for r in rows if r["new_safety"] in ("treatment", "baseline")]

    verdict = {
        "n_graded": len(rows),
        "mean_baseline": round(statistics.mean(bvals), 2) if bvals else None,
        "mean_treatment": round(statistics.mean(tvals), 2) if tvals else None,
        "mean_delta": round(statistics.mean(deltas), 2) if deltas else None,
        "head_to_head": {"treatment": t_wins, "baseline": b_wins, "tie": ties},
        "regressions": [{"question_id": r["question_id"], "domain": r["domain"],
                         "delta": r["delta"], "rationale": r["rationale"]} for r in regressions],
        "new_safety_errors": [{"question_id": r["question_id"], "arm": r["new_safety"]} for r in new_safety],
        "latency_seconds": {"baseline": lat_stats(list(base_lat.values())),
                            "treatment": lat_stats(list(treat_lat.values()))},
    }

    out_csv = Path(f"{args.out_prefix}-comparison.csv")
    with out_csv.open("w", encoding="utf-8") as fh:
        fh.write("question_id,domain,baseline,treatment,delta,winner,margin,new_safety\n")
        for r in rows:
            fh.write(f"{r['question_id']},{r['domain']},{r['baseline']},{r['treatment']},"
                     f"{r['delta']},{r['winner']},{r['margin']},{r['new_safety']}\n")
    Path(f"{args.out_prefix}-verdict.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")

    print(json.dumps(verdict, indent=2))
    print(f"\n[unblind_pairs] {out_csv} + {args.out_prefix}-verdict.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
