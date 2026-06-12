"""`caseboard` command-line entry point."""

from __future__ import annotations

import argparse

from neuro_caseboard.pipeline import generate, _slug


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="caseboard",
        description="Build a unified neurosurgical case-prep dossier.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build a dossier from a free-text case")
    b.add_argument("topic", help='Free-text case, e.g. "C5-6 corpectomy"')
    b.add_argument("-o", "--output", default=None, help="Output directory")
    b.add_argument("--pdf", action="store_true", help="Also export case-board.pdf")
    b.add_argument("--no-enrich", action="store_true",
                   help="Skip corpus enrichment (offline verify-only checklist)")

    args = parser.parse_args(argv)
    if args.cmd == "build":
        out = args.output or f"{_slug(args.topic)}-caseboard"
        dossier, artifacts = generate(
            args.topic, output_dir=out, pdf=args.pdf, enrich=not args.no_enrich)
        print(f"Wrote {artifacts['markdown']}")
        if "pdf" in artifacts:
            print(f"Wrote {artifacts['pdf']}")
        s = dossier.summary
        print(f"  {len(dossier.sections)} sections · "
              f"{s.supported} corpus-supported · {s.to_verify} to verify · "
              f"{s.quarantined} quarantined")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
