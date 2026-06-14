import argparse
import sys

from engine.gpu_guard import GpuNotReadyError
from engine.query import query


def main():
    ap = argparse.ArgumentParser(
        description="Ask the neurosurgery textbook RAG a clinical question.")
    ap.add_argument("question", help="The clinical question, in quotes")
    ap.add_argument("--force", action="store_true",
                    help="Run even if the GPU readiness guard fails.")
    args = ap.parse_args()

    try:
        result = query(args.question, force=args.force)
    except GpuNotReadyError as e:
        print(f"GPU not ready: {e}", file=sys.stderr)
        sys.exit(1)

    print(result.answer)
    print("\nSources:")
    for c in result.citations:
        loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
        print(f"  [{c.n}] {loc}")
    if result.figures:
        print("\nFigures:")
        for f in result.figures:
            print(f"  [{f.source_n}] {f.book}, p.{f.page} -> {f.image_path}")


if __name__ == "__main__":
    main()
