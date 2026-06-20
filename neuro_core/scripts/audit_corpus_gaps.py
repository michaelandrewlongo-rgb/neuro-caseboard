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
