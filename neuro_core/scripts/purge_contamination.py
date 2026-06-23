"""Re-runnable corpus contamination audit + guarded purge for the LanceDB index.

Some scraped textbook PDFs in this corpus have a *non-medical* book appended after the
real content (the known case: three copies of David Icke's "Perceptions of a Renegade
Mind" tacked onto the Youmans PDF). The shipped ingest guard (``neuro_core.ingest``)
already excludes those pages on any *future* re-index, but an index built before that
guard still carries the contaminated rows. This tool finds and removes them from the live
artifacts — without re-indexing, without touching the legit corpus.

Design (three principles):

1. **content_end is authoritative.** Detection reuses the *exact* shipped slice-2 logic:
   for each corpus PDF we open its TOC and call ``neuro_core.ingest._classify_toc`` →
   ``content_end``, the 1-based page where an appended non-medical region starts (``None``
   for a clean book). Rows with ``page >= content_end`` for that book are the contamination.
   This is generic — it is NOT hardcoded to Youmans/6330. The index ``book`` label is the
   PDF stem (see ``build_index``/``ingest.extract_pages``), so the PDF→book mapping is just
   ``Path(pdf).stem``.

2. **Markers are a REPORT-ONLY cross-check, never a delete trigger.** A word-boundary
   conspiracy-marker regex is scanned over chunk text and any hit that falls *outside* an
   already-detected ``content_end`` boundary is reported, so contamination with a different
   shape can't hide. But markers have false positives ("rothschild" can be a citation
   author *Rothschild B*; "reptilian" is also the reptilian-brain neuroscience term), so
   marker hits are printed for a human, NOT deleted, and do NOT change the exit code. Only
   ``content_end``-authoritative rows gate the exit code and drive deletion.

3. **Audit first, back up before any destructive op.** ``audit`` (default, read-only)
   exits non-zero iff contamination is found, so it works as a CI/operator gate. ``--apply``
   copies ``chunks.lance``, ``figures.lance`` and ``_gemini_captions.jsonl`` into a
   timestamped ``INDEX_DIR/_backup_purge_<UTC>/`` *first*, then deletes by
   ``book = '<b>' AND page >= <content_end>`` on both tables and rewrites the captions JSONL
   dropping the deleted figures. Idempotent: a second run finds nothing and makes no backup.

Caption mapping assumption: each ``_gemini_captions.jsonl`` line carries an ``id`` equal to
the ``figures`` table ``id`` (``"<book>::<plate>"``, where ``plate`` is the figure PNG stem;
see ``recaption_figures``/``build_visual_index``). Rather than parse pages out of paths, we
collect the *exact* set of figure ids being deleted straight from the ``figures`` table
(before deletion) and drop only those caption lines. Fail-safe: any caption line we cannot
parse, or whose id is not in the delete set, is KEPT (we never over-delete captions).

Usage:
  python -m neuro_core.scripts.purge_contamination                 # audit (read-only)
  python -m neuro_core.scripts.purge_contamination --apply         # back up + purge
  python -m neuro_core.scripts.purge_contamination --index-dir DIR --corpus-dir DIR
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import lancedb

from neuro_core.ingest import _classify_toc
from neuro_core.index import _sql_str, _table_names

CHUNKS_TABLE = "chunks"
FIGURES_TABLE = "figures"
CAPTIONS_FILE = "_gemini_captions.jsonl"

# Word-boundary conspiracy markers (cross-check only — see module docstring). Single-word
# markers are anchored with \b so substrings ("ick" in "Frederick", "free" in "freeze")
# don't trip; the multi-word phrases are distinctive enough not to need anchoring.
MARKER_RE = re.compile(
    r"\b(?:david\s+icke|reptilian|illuminati|annunaki|anunnaki|freemason|rothschild|icke)\b"
    r"|renegade perception|who controls the cult|perceptions of a renegade mind",
    re.IGNORECASE,
)


def detect_content_ends(corpus_dir) -> dict[str, Optional[int]]:
    """Map each corpus PDF's index ``book`` label (its stem) to its slice-2 ``content_end``.

    Reuses the shipped ``_classify_toc`` so detection stays in lockstep with the ingest
    guard. ``content_end`` is the 1-based page where an appended non-medical region starts,
    or ``None`` for a clean book. Isolated as a function so it can be monkeypatched in tests
    (no real PDF needed). A PDF that fails to open is treated as clean (``None``).
    """
    import fitz  # PyMuPDF — imported lazily so this module imports without a TOC to read

    out: dict[str, Optional[int]] = {}
    for pdf in sorted(Path(corpus_dir).glob("*.pdf")):
        try:
            doc = fitz.open(pdf)
            try:
                _entries, content_end = _classify_toc(doc)
            finally:
                doc.close()
        except Exception:
            content_end = None
        out[pdf.stem] = content_end
    return out


def _load_cols(db, table, cols):
    """Read named columns from a LanceDB table as parallel python lists.

    Returns empty lists when the table is absent and ``[None] * n`` for a missing column,
    so callers can ``zip`` without special-casing schema drift.
    """
    if table not in _table_names(db):
        return {c: [] for c in cols}
    at = db.open_table(table).to_arrow()
    names = set(at.schema.names)
    return {c: (at.column(c).to_pylist() if c in names else [None] * at.num_rows)
            for c in cols}


def gather(db, content_ends):
    """Compute the contamination picture from the index (pure read).

    Returns ``(per_book, marker_hits, total, deleted_fig_ids)`` where:
      - ``per_book``: ``{book: {content_end, chunks, figures}}`` for every book with a
        non-``None`` ``content_end`` (the deletable region; counts are ``page >= end``);
      - ``marker_hits``: sorted, de-duplicated ``(book, page)`` marker hits that fall
        OUTSIDE any detected boundary (report-only cross-check);
      - ``total``: total content_end-authoritative contaminated rows (chunks + figures) —
        this is what the exit code keys on;
      - ``deleted_fig_ids``: the exact ``figures`` ids in the deletable region (used to
        filter the captions JSONL).
    """
    ch = _load_cols(db, CHUNKS_TABLE, ["book", "page", "text"])
    fg = _load_cols(db, FIGURES_TABLE, ["id", "book", "page"])

    per_book: dict[str, dict] = {}
    deleted_fig_ids: set = set()
    for book in sorted(b for b, e in content_ends.items() if e is not None):
        end = content_ends[book]
        n_chunks = sum(1 for b, p in zip(ch["book"], ch["page"])
                       if b == book and p is not None and p >= end)
        n_figs = 0
        for fid, b, p in zip(fg["id"], fg["book"], fg["page"]):
            if b == book and p is not None and p >= end:
                n_figs += 1
                if fid is not None:
                    deleted_fig_ids.add(fid)
        per_book[book] = {"content_end": end, "chunks": n_chunks, "figures": n_figs}

    marker_hits: list = []
    seen: set = set()
    for b, p, t in zip(ch["book"], ch["page"], ch["text"]):
        if not t or not MARKER_RE.search(t):
            continue
        end = content_ends.get(b)
        covered = end is not None and p is not None and p >= end
        if not covered:
            key = (b, p)
            if key not in seen:
                seen.add(key)
                marker_hits.append(key)
    marker_hits.sort(key=lambda kp: (str(kp[0]), kp[1] if kp[1] is not None else -1))

    total = sum(v["chunks"] + v["figures"] for v in per_book.values())
    return per_book, marker_hits, total, deleted_fig_ids


def _print_report(per_book, marker_hits, total):
    print("Contamination audit (content_end-authoritative)\n")
    if per_book:
        print(f"  {'book':40s} {'content_end':>11s} {'chunks':>7s} {'figures':>7s}")
        for book, v in sorted(per_book.items()):
            print(f"  {book:40.40s} {v['content_end']:>11d} "
                  f"{v['chunks']:>7d} {v['figures']:>7d}")
    else:
        print("  No book has a content_end boundary (nothing deletable).")

    print(f"\n  Out-of-boundary marker hits (cross-check, report-only): {len(marker_hits)}")
    for book, page in marker_hits[:50]:
        print(f"    MARKER {book} p{page}")
    if len(marker_hits) > 50:
        print(f"    ... and {len(marker_hits) - 50} more")

    books = sorted(b for b, v in per_book.items() if v["chunks"] or v["figures"])
    print(f"\nSUMMARY: {total} contaminated rows across {len(books)} book(s)"
          + (f": {', '.join(books)}" if books else ""))
    if marker_hits and total == 0:
        print("  NOTE: marker hits exist but none is content_end-authoritative — these are "
              "likely false positives (e.g. citation author 'Rothschild', the reptilian "
              "brain). Review manually; they do NOT gate this exit code.")
    return total, books


def do_audit(db, content_ends):
    per_book, marker_hits, total, _ = gather(db, content_ends)
    _print_report(per_book, marker_hits, total)
    return 1 if total > 0 else 0


def _filter_caption_lines(lines, deleted_ids):
    """Drop caption JSONL lines whose figure ``id`` is in ``deleted_ids`` (fail-safe keep).

    A line we cannot parse as JSON, or whose ``id`` we don't recognise, is KEPT — we never
    over-delete captions. Blank lines are normalised away. Returns ``(kept_lines, dropped)``.
    """
    kept, dropped = [], 0
    for line in lines:
        s = line.strip()
        if not s:
            continue
        try:
            fid = json.loads(s).get("id")
        except Exception:
            kept.append(line)  # unparseable -> fail safe, keep
            continue
        if fid in deleted_ids:
            dropped += 1
        else:
            kept.append(line)
    return kept, dropped


def do_apply(db, index_dir, content_ends):
    index_dir = Path(index_dir)
    per_book, marker_hits, total, deleted_fig_ids = gather(db, content_ends)
    _print_report(per_book, marker_hits, total)

    if total == 0:
        print("\nNo content_end-authoritative contamination — nothing to purge (no-op).")
        return 0

    # (1) Back up FIRST — copy whole .lance dirs + the captions file before any delete.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    backup = index_dir / f"_backup_purge_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    backed_up = []
    for name in (f"{CHUNKS_TABLE}.lance", f"{FIGURES_TABLE}.lance"):
        src = index_dir / name
        if src.exists():
            shutil.copytree(src, backup / name)
            backed_up.append(name)
    caps_path = index_dir / CAPTIONS_FILE
    if caps_path.exists():
        shutil.copy2(caps_path, backup / CAPTIONS_FILE)
        backed_up.append(CAPTIONS_FILE)
    print(f"\nBacked up {', '.join(backed_up)} -> {backup}")

    # (2) Delete the content_end-authoritative region from both tables.
    names = _table_names(db)
    deleted_chunks = deleted_figs = 0
    for book, info in per_book.items():
        if not (info["chunks"] or info["figures"]):
            continue
        pred = f"book = {_sql_str(book)} AND page >= {int(info['content_end'])}"
        if CHUNKS_TABLE in names:
            db.open_table(CHUNKS_TABLE).delete(pred)
            deleted_chunks += info["chunks"]
        if FIGURES_TABLE in names:
            db.open_table(FIGURES_TABLE).delete(pred)
            deleted_figs += info["figures"]
        print(f"  deleted {book}: {info['chunks']} chunks + {info['figures']} figures "
              f"(page >= {info['content_end']})")

    # (3) Rewrite the captions JSONL, dropping lines for deleted figures.
    dropped_caps = 0
    if caps_path.exists() and deleted_fig_ids:
        kept, dropped_caps = _filter_caption_lines(
            caps_path.read_text().splitlines(), deleted_fig_ids)
        caps_path.write_text(("\n".join(kept) + "\n") if kept else "")

    print(f"\nPurged {deleted_chunks} chunks + {deleted_figs} figures; "
          f"dropped {dropped_caps} caption line(s). Backup: {backup}")

    # (4) Verify clean now (and signal via exit code).
    _, _, total_after, _ = gather(db, content_ends)
    if total_after:
        print(f"WARNING: {total_after} contaminated rows still present after purge.")
        return 1
    print("Verified clean (0 content_end-authoritative contaminated rows remain).")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="purge_contamination",
        description="Audit (default, read-only) or --apply a guarded purge of appended "
                    "non-medical contamination from the LanceDB index.")
    ap.add_argument("--apply", action="store_true",
                    help="back up then DELETE content_end-authoritative contaminated rows "
                         "(default is read-only audit)")
    ap.add_argument("--index-dir", default=None,
                    help="LanceDB index dir (default: config INDEX_DIR)")
    ap.add_argument("--corpus-dir", default=None,
                    help="corpus PDF dir for content_end detection (default: config CORPUS_DIR)")
    args = ap.parse_args(argv)

    # Only touch config (which may read .env / stale defaults) when an override is missing,
    # so callers passing both dirs stay fully self-contained.
    if args.index_dir is None or args.corpus_dir is None:
        from neuro_core.config import load_config
        cfg = load_config()
        index_dir = args.index_dir or str(cfg.index_dir)
        corpus_dir = args.corpus_dir or str(cfg.corpus_dir)
    else:
        index_dir, corpus_dir = args.index_dir, args.corpus_dir

    content_ends = detect_content_ends(corpus_dir)
    db = lancedb.connect(str(index_dir))
    if args.apply:
        return do_apply(db, index_dir, content_ends)
    return do_audit(db, content_ends)


if __name__ == "__main__":
    sys.exit(main())
