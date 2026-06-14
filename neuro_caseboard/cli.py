"""`caseboard` command-line entry point: ask cited questions and build pre-op dossiers."""

from __future__ import annotations

import argparse
import sys

from neuro_caseboard.pipeline import generate, _slug


def _run_ask(args) -> int:
    from neuro_core.gpu_guard import GpuNotReadyError
    from neuro_core.query import query
    try:
        result = query(args.question, force=args.force)
    except GpuNotReadyError as e:
        print(f"GPU not ready: {e}", file=sys.stderr)
        return 1
    print(result.answer)
    print("\nSources:")
    for c in result.citations:
        loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
        print(f"  [{c.n}] {loc}")
    if result.figures:
        print("\nFigures:")
        for f in result.figures:
            print(f"  [{f.source_n}] {f.book}, p.{f.page} -> {f.image_path}")
    return 0


def _run_build(args) -> int:
    out = args.output or f"{_slug(args.topic)}-caseboard"
    dossier, artifacts = generate(
        args.topic, output_dir=out, pdf=args.pdf, enrich=not args.no_enrich,
        use_llm=False if args.no_llm else None)
    print(f"Wrote {artifacts['markdown']}")
    if "pdf" in artifacts:
        print(f"Wrote {artifacts['pdf']}")
    s = dossier.summary
    print(f"  {len(dossier.sections)} sections · "
          f"{s.supported} corpus-supported · {s.to_verify} to verify · "
          f"{s.quarantined} quarantined")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="caseboard",
        description="Neurosurgical case prep: ask cited questions and build pre-op dossiers.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ask", help="Ask a cited clinical/anatomy question")
    a.add_argument("question", help="The clinical question, in quotes")
    a.add_argument("--force", action="store_true",
                   help="Run even if the GPU readiness guard fails.")

    b = sub.add_parser("build", help="Build a dossier from a free-text case")
    b.add_argument("topic", help='Free-text case, e.g. "C5-6 corpectomy"')
    b.add_argument("-o", "--output", default=None, help="Output directory")
    b.add_argument("--pdf", action="store_true", help="Also export case-board.pdf")
    b.add_argument("--no-enrich", action="store_true",
                   help="Skip corpus enrichment (offline verify-only checklist)")
    b.add_argument("--no-llm", action="store_true",
                   help="Force the deterministic Explorer (skip the LLM case-specific Explorer)")

    args = parser.parse_args(argv)
    if args.cmd == "ask":
        return _run_ask(args)
    if args.cmd == "build":
        return _run_build(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
