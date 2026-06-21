#!/usr/bin/env python3
"""Phase 0A: measure textbook crowd-out, grader-independently.

Runs each benchmark question through retrieval (NO synthesis, NO grader) and records the
full ranked candidate ordering at both gates. Then computes, by post-hoc removal of a
target ``--book`` from the ordering, exactly which other passages that book evicts from
the answer context -- the mechanistic test the council asked for, to distinguish real
crowd-out from the regression-to-the-mean artifact in the score deltas.

No reindex is needed: removing a book's chunks from the captured ordering and re-taking
the top-k is an exact counterfactual for "the same corpus minus that book".

Usage (needs the live index + models; respects .env CORPUS_DIR/INDEX_DIR):
    # observe the SELECTION gate (top-RERANK_K) -- default
    python3 scripts/retrieval_displacement.py --book youmans

    # also observe the RECALL gate (top-RETRIEVE_K) by widening the pool first:
    RETRIEVE_K=120 python3 scripts/retrieval_displacement.py --book youmans --lane recall

    # limit to a few questions for a smoke test:
    python3 scripts/retrieval_displacement.py --book youmans --limit 3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (REPO / ".claude/worktrees/session-2026-06-20-1253/evaluation/"
                    "inputs/benchmark-manifest.jsonl")


def load_questions(manifest: Path, limit=None):
    rows = []
    for line in Path(manifest).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("enabled", True):
            rows.append((r["id"], r.get("domain", ""), r["question"]))
    return rows[:limit] if limit else rows


def run(manifest, book, lane, limit, out_dir, top_k=None):
    from neuro_core.query import get_engine
    from neuro_core.retrieval_trace import aggregate_displacement

    engine = get_engine()
    questions = load_questions(manifest, limit)
    traces, domains = [], {}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "traces.jsonl"
    with trace_path.open("w") as fh:
        for qid, domain, question in questions:
            _top, trace = engine.retrieve_traced(question, qid=qid)
            domains[qid] = domain
            traces.append(trace)
            fh.write(json.dumps(trace.to_dict()) + "\n")
            print(f"  traced {qid} ({len(trace.selection)} scored, "
                  f"{sum(c.selected for c in trace.selection)} selected)", flush=True)

    agg = aggregate_displacement(traces, book, lane=lane, top_k=top_k)
    # per-domain rollup
    by_domain = {}
    for row in agg["rows"]:
        d = domains.get(row["qid"], "")
        b = by_domain.setdefault(d, {"q": 0, "displaced": 0})
        b["q"] += 1
        b["displaced"] += row["n_displaced"]

    summary = {
        "book": book, "lane": lane,
        "n_questions": agg["n_questions"],
        "questions_with_intruder": agg["questions_with_intruder"],
        "questions_with_displacement": agg["questions_with_displacement"],
        "total_displaced": agg["total_displaced"],
        "mean_displaced_per_q": round(agg["mean_displaced_per_q"], 3),
        "mean_marginal_gap": (round(agg["mean_marginal_gap"], 4)
                              if agg["mean_marginal_gap"] is not None else None),
        "by_domain": by_domain,
        "per_question": [
            {"qid": r["qid"], "n_intruders": r["n_intruders"],
             "n_displaced": r["n_displaced"],
             "min_intruder_score": r["min_intruder_score"],
             "max_displaced_score": r["max_displaced_score"]}
            for r in agg["rows"]],
    }
    (out_dir / "displacement-summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\n=== Crowd-out by '{book}' at the {lane} gate "
          f"(n={summary['n_questions']}) ===")
    print(f"questions where {book} took >=1 slot : "
          f"{summary['questions_with_intruder']}/{summary['n_questions']}")
    print(f"questions with >=1 evicted passage   : "
          f"{summary['questions_with_displacement']}/{summary['n_questions']}")
    print(f"total passages evicted               : {summary['total_displaced']}")
    print(f"mean evicted / question              : {summary['mean_displaced_per_q']}")
    print(f"mean marginal gap (small => evicted strong incumbents): "
          f"{summary['mean_marginal_gap']}")
    print(f"\nwrote {trace_path} and {out_dir / 'displacement-summary.json'}")
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", default="youmans", help="target book stem (substring match)")
    ap.add_argument("--lane", default="selection", choices=["selection", "recall"])
    ap.add_argument("--top-k", type=int, default=None,
                    help="cutoff to analyse (default: RERANK_K for selection, RETRIEVE_K "
                         "for recall). For the recall gate, set RETRIEVE_K high to capture a "
                         "deep pool and pass --top-k 40 to analyse the real cutoff.")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(REPO / "eval" / "displacement"))
    args = ap.parse_args(argv)

    if not Path(args.manifest).exists():
        sys.exit(f"manifest not found: {args.manifest}")
    run(args.manifest, args.book, args.lane, args.limit, args.out, top_k=args.top_k)


if __name__ == "__main__":
    main()
