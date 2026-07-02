#!/usr/bin/env python3
"""Validate a claim↔citation verifier against the 40-claim blind gold set, or re-score a saved
benchmark run offline with it.

Gold-set mode (default): run the verifier over evaluation/groundedness-gold-set.jsonl and score it
against the frontier-judge labels (S=supported, P=partial, N=not). The two numbers that matter:

  * flag precision — of the claims the verifier flags, how many the judge agrees are bad (P/N).
    The shipped LexicalVerifier's known weakness: ~10% (18/20 flags were false alarms).
  * false-pass rate — of the claims the verifier passes, how many the judge says are bad. The
    dangerous direction for a medical RAG; lexical baseline 5% (1/20).

Run-rescore mode (--rescore RUN_JSONL): rebuild each answer's premises from its saved citations and
recompute verify_answer() with the chosen verifier, reporting the corpus-lane groundedness — the
same offline methodology used for the PR#50 precision-gate fix in evaluation/RESULTS.md.

Examples:
  python3 evaluation/scripts/validate_verifier.py                        # lexical baseline
  python3 evaluation/scripts/validate_verifier.py --nli cross-encoder/nli-deberta-v3-base
  python3 evaluation/scripts/validate_verifier.py --nli MODEL --threshold 0.7 \
      --rescore evaluation/runs/pr50-groundedness-20260622-125141/run.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from neuro_caseboard.answer_verify import _strip_markers, verify_answer  # noqa: E402
from neuro_caseboard.entailment import LexicalVerifier, NLIVerifier, should_cite  # noqa: E402

GOLD = Path(__file__).resolve().parents[1] / "groundedness-gold-set.jsonl"


def build_verifier(args):
    if args.nli:
        return NLIVerifier(args.nli, entail_threshold=args.threshold), f"nli:{args.nli}@{args.threshold}"
    return LexicalVerifier(), "lexical"


def gold_set_report(verifier, name: str) -> None:
    rows = [json.loads(line) for line in GOLD.read_text().splitlines() if line.strip()]
    t0 = time.perf_counter()
    results = []
    for r in rows:
        premise = " ".join(p["text"] for p in r["passages"])
        passed = should_cite(premise, _strip_markers(r["claim"]), verifier)
        results.append((r, passed))
    elapsed = time.perf_counter() - t0

    def is_bad(r):  # judge says the claim is not (fully) supported
        return r["frontier_judge_label"] in ("P", "N")

    flags = [(r, p) for r, p in results if not p]
    passes = [(r, p) for r, p in results if p]
    true_flags = sum(1 for r, _ in flags if is_bad(r))
    false_passes = sum(1 for r, _ in passes if is_bad(r))
    print(f"\n== {name} ==  ({len(rows)} claims, {elapsed:.1f}s, {elapsed / len(rows) * 1000:.0f} ms/claim)")
    print(f"flags: {len(flags)}  flag precision: {true_flags}/{len(flags)}"
          f" = {true_flags / len(flags):.2f}" if flags else "flags: 0")
    print(f"passes: {len(passes)}  false-pass: {false_passes}/{len(passes)}"
          f" = {false_passes / len(passes) if passes else 0:.2f}")
    caught = sum(1 for r, p in results if is_bad(r) and not p)
    n_bad = sum(1 for r, _ in results if is_bad(r))
    print(f"bad-claim recall: {caught}/{n_bad}")
    for r, p in results:
        if is_bad(r) and p:
            print(f"  DANGEROUS PASS item {r['item']} ({r['frontier_judge_label']}): {r['claim'][:100]}")
    disagree = [r["item"] for r, p in results
                if (r["checker_verdict"] == "supported") != p]
    print(f"verdict changes vs shipped lexical checker: {len(disagree)} items: {disagree}")


def rescore_run(verifier, name: str, run_jsonl: Path) -> None:
    n_claims = n_unsup = 0
    n_answers = 0
    t0 = time.perf_counter()
    for line in run_jsonl.read_text().splitlines():
        rec = json.loads(line)
        if rec.get("status") != "completed" or not rec.get("answer"):
            continue
        premises = {str(c["n"]): c.get("text") or "" for c in rec.get("citations") or []}
        v = verify_answer(rec["answer"], premises, verifier=verifier)
        n_claims += v.n_cited_claims
        n_unsup += v.n_unsupported
        n_answers += 1
    elapsed = time.perf_counter() - t0
    print(f"\n== rescore {run_jsonl} with {name} ==")
    print(f"{n_answers} answers, {n_claims} cited claims, {elapsed:.0f}s")
    print(f"groundedness: {1 - n_unsup / n_claims:.3f}  unsupported rate: {n_unsup / n_claims:.3f}"
          f"  ({n_unsup} flagged)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nli", help="NLI cross-encoder model name (default: lexical baseline)")
    ap.add_argument("--threshold", type=float, default=0.5, help="NLI entailment threshold")
    ap.add_argument("--rescore", type=Path, help="run.jsonl to re-score instead of the gold set")
    args = ap.parse_args()
    verifier, name = build_verifier(args)
    if args.rescore:
        rescore_run(verifier, name, args.rescore)
    else:
        gold_set_report(verifier, name)


if __name__ == "__main__":
    main()
