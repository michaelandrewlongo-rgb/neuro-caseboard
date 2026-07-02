#!/usr/bin/env python3
"""Render chunking_benchmark JSON result files into Markdown tables.

    python3 scripts/chunking_report.py eval/chunking-benchmark/results_*.json
"""
import argparse
import json
import sys
from pathlib import Path

COLS = [
    ("arm", "arm"), ("recall@40_ceiling", "ceil"), ("recall@12_window", "win@12"),
    ("recall@5", "@5"), ("mrr", "MRR"), ("n_chunks", "chunks"),
    ("median_words", "med w"), ("frag_pct_lt50w", "frag%"), ("dup_pct", "dup%"),
    ("index_mb", "MB"), ("build_s", "build s"), ("query_ms", "q ms"),
]


def table(arms, rerank_k=12, retrieve_k=40):
    ceil_key = f"recall@{retrieve_k}_ceiling"
    win_key = f"recall@{rerank_k}_window"
    cols = [(k.replace("40", str(retrieve_k)).replace("12", str(rerank_k)), lbl)
            for k, lbl in COLS]
    head = "| " + " | ".join(lbl for _, lbl in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    rows = [head, sep]
    for a in arms:
        cells = []
        for k, _ in cols:
            v = a.get(k, a.get(ceil_key if "ceiling" in k else k, ""))
            cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args()
    for f in args.files:
        d = json.loads(f.read_text())
        print(f"\n### {f.name}")
        print(f"embed={d['embed_model']} rerank={d['rerank_model']} "
              f"retrieve_k={d['retrieve_k']} rerank_k={d['rerank_k']} "
              f"books={len(d['books'])} gold={d['n_gold']}\n")
        print(table(d["arms"], d["rerank_k"], d["retrieve_k"]))
        # collect union of misses
        allmiss = {}
        for a in d["arms"]:
            for m in a.get("misses", []):
                allmiss.setdefault(m, []).append(a["arm"])
        if allmiss:
            print("\n**Gold questions missed (arm list):**")
            for q, arms in sorted(allmiss.items(), key=lambda kv: -len(kv[1])):
                print(f"- `{q}` — {len(arms)}/{len(d['arms'])} arms")


if __name__ == "__main__":
    main()
