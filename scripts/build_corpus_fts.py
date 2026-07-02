#!/usr/bin/env python3
"""Build disk-lean contentless FTS5 sidecars for the frozen literature corpus (Lane C).

One sidecar per subspecialty DB: ``<FTS_DIR>/<name>_fts.sqlite`` holding a *contentless*
FTS5 table ``passages_fts(content)`` whose rowid == the source ``text_passages`` rowid.
Contentless (``content=''``) stores only the inverted index (~1/3 the text size); the
retriever joins the matched rowid back to the read-only source for content + work metadata.
The source DBs are opened read-only and never modified.

Usage:
  python scripts/build_corpus_fts.py [name ...]   # default: priority order, skips up-to-date

Env: CORPUS_SOURCE_DIR (default /mnt/c/dev/NSGY_DB_lean/fulltext),
     CORPUS_FTS_DIR    (default ~/.cache/neuro_caseboard/corpus_fts).
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

# Only the cerebrovascular-relevant subspecialties, cheapest-to-validate first.
PRIORITY = ["cerebrovascular", "neurointerventional", "radiosurgery", "neurocritical_care",
            "trauma_general", "pediatrics", "tumor_skull_base"]

SRC_DIR = Path(os.environ.get("CORPUS_SOURCE_DIR", "/mnt/c/dev/NSGY_DB_lean/fulltext"))
FTS_DIR = Path(os.environ.get("CORPUS_FTS_DIR",
                              str(Path.home() / ".cache" / "neuro_caseboard" / "corpus_fts")))


def _src_count(src: Path) -> int:
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        return con.execute("SELECT COUNT(*) FROM text_passages").fetchone()[0]
    finally:
        con.close()


def build_one(name: str) -> None:
    src = SRC_DIR / f"{name}_fulltext.sqlite"
    if not src.exists():
        print(f"[skip] {name}: source missing ({src})", flush=True)
        return
    FTS_DIR.mkdir(parents=True, exist_ok=True)
    out = FTS_DIR / f"{name}_fts.sqlite"
    want = _src_count(src)

    if out.exists():
        try:
            con = sqlite3.connect(str(out))
            have = con.execute("SELECT COUNT(*) FROM passages_fts").fetchone()[0]
            con.close()
            if have == want:
                print(f"[done] {name}: already built ({have} rows)", flush=True)
                return
            print(f"[rebuild] {name}: have {have} != want {want}", flush=True)
        except sqlite3.Error:
            pass
        out.unlink(missing_ok=True)

    t0 = time.time()
    con = sqlite3.connect(str(out), uri=True)
    try:
        con.execute("PRAGMA journal_mode=OFF")
        con.execute("PRAGMA synchronous=OFF")
        con.execute("CREATE VIRTUAL TABLE passages_fts USING "
                    "fts5(content, tokenize='porter unicode61', content='')")
        con.execute("ATTACH DATABASE ? AS src", (f"file:{src}?mode=ro",))
        con.execute("INSERT INTO passages_fts(rowid, content) "
                    "SELECT rowid, content FROM src.text_passages")
        con.commit()
        try:
            con.execute("INSERT INTO passages_fts(passages_fts) VALUES('optimize')")
            con.commit()
        except sqlite3.Error as e:
            print(f"[warn] {name}: optimize skipped ({e})", flush=True)
        have = con.execute("SELECT COUNT(*) FROM passages_fts").fetchone()[0]
        con.execute("DETACH DATABASE src")
    finally:
        con.close()
    print(f"[built] {name}: {have}/{want} rows in {time.time() - t0:.0f}s -> {out}", flush=True)


def main(argv) -> None:
    names = argv or PRIORITY
    for n in names:
        try:
            build_one(n)
        except Exception as e:  # one DB failing must not abort the batch
            print(f"[error] {n}: {e}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
