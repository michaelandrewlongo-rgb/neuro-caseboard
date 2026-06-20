"""Preflight corpus PDFs before an expensive GPU index build.

    python -m neuro_core.scripts.probe_book PATH.pdf      # one file
    python -m neuro_core.scripts.probe_book --corpus      # every *.pdf in CORPUS_DIR

Exit 0 if all probed books are OK, 1 if any book is scanned/empty (do not index it).
"""
import argparse
import sys
from pathlib import Path

from neuro_core.config import load_config
from neuro_core.ingest import probe_book


def _fmt(r):
    flag = "OK  " if r["ok"] else "SKIP"
    return (f"[{flag}] {r['book']}: {r['pages']}p text={r['coverage']:.2f} "
            f"chapters={r['chapters']} figpages={r['pages_with_figures']} — {r['reason']}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="probe_book")
    ap.add_argument("pdf", nargs="?", help="PDF path to probe")
    ap.add_argument("--corpus", action="store_true", help="probe every *.pdf in CORPUS_DIR")
    args = ap.parse_args(argv)
    if args.corpus:
        paths = sorted(load_config().corpus_dir.glob("*.pdf"))
    elif args.pdf:
        paths = [Path(args.pdf)]
    else:
        ap.error("give a PDF path or --corpus")
    all_ok = True
    for p in paths:
        r = probe_book(p)
        print(_fmt(r))
        all_ok = all_ok and r["ok"]
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
