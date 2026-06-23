"""Re-runnable corpus contamination audit + guarded purge for the LanceDB index.

Some scraped textbook PDFs in this corpus have a *non-medical* book appended after the
real content (the known case: David Icke's "Perceptions of a Renegade Mind" tacked onto the
Youmans PDF). The shipped ingest guard (``neuro_core.ingest``) already excludes those pages
on any *future* re-index, but an index built before that guard still carries the contaminated
rows. This tool finds and removes them from the live artifacts — without re-indexing, without
touching the legit corpus.

Why detection is **index-based** (not PDF-TOC based)
----------------------------------------------------
The first version of this script derived the contamination boundary from the *PDF* TOC
(``ingest._classify_toc -> content_end``). That is unreliable against a live index: the
Youmans PDF was re-modified after indexing, so the appended David-Icke book sits at *PDF*
pages 7354+ while the *index* (built earlier) carries it at *index* pages 6330+ — a ~1024
page offset — and ``_classify_toc`` returns ``None`` on the current PDF anyway. The PDF and
the index page numbers are simply out of sync, so detection MUST come from the index itself.

We therefore detect the boundary purely from the indexed ``chunks`` rows
(``book``/``page``/``chapter``/``text``), independent of any PDF:

1. **STRONG signature.** A curated, case-insensitive regex of the appended book's distinctive
   chapter titles (e.g. "Renegade perception", "Who controls the Cult?", "The Pushbacker
   sting", "Escaping Wetiko") plus book-level phrases ("perceptions of a renegade mind",
   "david icke"). A chunk is *strong* if its ``chapter`` matches. These phrases never occur in
   legitimate neurosurgery. A book with fewer than ``MIN_STRONG`` strong chunks is treated as
   clean (avoids firing on a stray phrase).
2. **Boundary.** ``P0`` = the lowest page among strong chunks. The boundary ``B`` is the page
   just after the *last legit chunk below* ``P0`` — the highest-page chunk below ``P0`` whose
   ``chapter`` is neither a strong (David-Icke) label nor a generic front-matter label
   (Copyright / Dedication / Contents / …). Setting ``B = last_legit_page + 1`` also captures
   a title page that has figures but no text chunk. For Youmans this yields ``B = 6330``.
3. **Safety purity check (fail-safe).** Every chunk in ``[B, max_page]`` of that book must be
   NON-medical (``ingest._is_medical_chapter`` False) AND the region must contain at least one
   conspiracy text marker (``reptilian|illuminati|annunaki|freemason|\\bicke\\b|renegade|
   wetiko``). If a *medical*-labelled chunk is found inside ``[B, max_page]`` the book is
   **excluded** from the purge with a loud warning — we never over-delete legit content.

**Markers are a SECONDARY, report-only cross-check, never a delete trigger.** A word-boundary
conspiracy-marker regex is scanned over chunk text and any hit that falls *outside* an
already-detected region is reported, so contamination with a different shape can't hide. But
markers have false positives ("rothschild" can be a citation author *Rothschild B*; "reptilian"
is also the reptilian-brain neuroscience term), so marker hits are printed for a human, NOT
deleted, and do NOT change what gets purged.

**Audit first, back up before any destructive op.** ``audit`` (default, read-only) exits
non-zero iff contamination is found, so it works as a CI/operator gate. ``--apply`` copies
``chunks.lance``, ``figures.lance`` and ``_gemini_captions.jsonl`` into a timestamped
``INDEX_DIR/_backup_purge_<UTC>/`` *first*, then deletes by ``book = '<b>' AND page >= <B>`` on
both tables and rewrites the captions JSONL dropping the deleted figures. Idempotent: a second
run finds nothing and makes no backup.

Caption mapping assumption: each ``_gemini_captions.jsonl`` line carries an ``id`` equal to
the ``figures`` table ``id`` (``"<book>::<plate>"``; see ``recaption_figures`` /
``build_visual_index``). We collect the *exact* set of figure ids being deleted straight from
the ``figures`` table (before deletion) and drop only those caption lines. Fail-safe: any
caption line we cannot parse, or whose id is not in the delete set, is KEPT.

Usage:
  python -m neuro_core.scripts.purge_contamination                 # audit (read-only)
  python -m neuro_core.scripts.purge_contamination --apply         # back up + purge
  python -m neuro_core.scripts.purge_contamination --index-dir DIR
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import lancedb

from neuro_core.ingest import _is_medical_chapter
from neuro_core.index import _sql_str, _table_names

CHUNKS_TABLE = "chunks"
FIGURES_TABLE = "figures"
CAPTIONS_FILE = "_gemini_captions.jsonl"

# A book needs at least this many STRONG-signature chunks before we treat it as contaminated.
# The known case carries >1000; the floor only rules out a single stray phrase.
MIN_STRONG = 15

# STRONG signature: distinctive chapter titles of the appended David-Icke book + book-level
# phrases. Matched against a *normalised* chapter label (smart quotes/dashes folded, lowercased)
# so the index's curly-quote titles ("'I'm thinking' - Oh, but are you?") still match. These
# phrases are zero-false-positive against neurosurgery (verified across all 18 corpus books).
_STRONG_PHRASES = (
    "oh, but are you",            # ch1  "'I'm thinking' – Oh, but are you?"
    "i'm thinking",               # ch1
    "renegade perception",        # ch2
    "pushbacker",                 # ch3  "The Pushbacker sting"
    "calculated catastrophe",     # ch4  "'Covid': The calculated catastrophe"
    "there is no 'virus'",        # ch5
    "sequence of deceit",         # ch6
    "war on your mind",           # ch7
    "'reframing' insanity",       # ch8
    "so what is it",              # ch9  "We must have it? So what is it?"
    "human 2.0",                  # ch10
    "who controls the cult",      # ch11
    "escaping wetiko",            # ch12
    "perceptions of a renegade mind",
    "renegade mind",
    "david icke",
    "wetiko",
)
_STRONG_RE = re.compile("|".join(re.escape(p) for p in _STRONG_PHRASES))

# Generic front-matter labels the appended book carries between the legit content and its first
# real chapter. Matched as a case-insensitive prefix on the stripped chapter label.
_FRONT_MATTER_PREFIXES = (
    "copyright", "dedication", "contents", "table of contents", "title page",
    "acknowledg", "foreword", "preface",
)

# Conspiracy text markers for the PURITY check (word-boundary; the region must contain >=1).
_PURITY_MARKER_RE = re.compile(
    r"reptilian|illuminati|annunaki|anunnaki|freemason|\bicke\b|renegade|wetiko",
    re.IGNORECASE,
)

# Secondary, report-only cross-check (see module docstring). Single-word markers are anchored
# with \b so substrings ("ick" in "Frederick") don't trip; multi-word phrases are distinctive.
MARKER_RE = re.compile(
    r"\b(?:david\s+icke|reptilian|illuminati|annunaki|anunnaki|freemason|rothschild|icke)\b"
    r"|renegade perception|who controls the cult|perceptions of a renegade mind",
    re.IGNORECASE,
)

_SMART = {0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x2013: "-", 0x2014: "-"}


def _normalize(label) -> str:
    """Fold smart quotes/dashes, lowercase and collapse whitespace for robust matching."""
    return " ".join((label or "").translate(_SMART).lower().split())


def _is_strong(chapter) -> bool:
    return bool(_STRONG_RE.search(_normalize(chapter)))


def _is_front_matter(chapter) -> bool:
    t = (chapter or "").strip().lower()
    return any(t.startswith(p) for p in _FRONT_MATTER_PREFIXES)


def _analyze_book(rows, *, min_strong=MIN_STRONG):
    """Analyse one book's ``(page, chapter, text)`` rows; ``None`` if not contaminated.

    Returns a finding dict: ``boundary`` (first contaminated page), ``strong`` (strong-chunk
    count), ``region_chunks``, ``max_page``, ``n_medical_in_region``, ``n_markers_in_region``,
    ``purity_ok``. ``purity_ok`` False means the appended region is impure (a medical chunk
    leaked in, or no conspiracy marker) → the caller must NOT purge that book.
    """
    strong_pages = [p for (p, ch, _t) in rows if p is not None and _is_strong(ch)]
    if len(strong_pages) < min_strong:
        return None

    p0 = min(strong_pages)
    legit_below = [p for (p, ch, _t) in rows
                   if p is not None and p < p0
                   and not _is_strong(ch) and not _is_front_matter(ch)]
    if legit_below:
        boundary = max(legit_below) + 1
    else:
        # No legit content below the first appended chapter: take the earliest page of the
        # appended block (its strong chapters or front matter) as the boundary.
        appended = [p for (p, ch, _t) in rows
                    if p is not None and (_is_strong(ch) or _is_front_matter(ch))]
        boundary = min(appended) if appended else p0

    region = [(p, ch, t) for (p, ch, t) in rows if p is not None and p >= boundary]
    n_medical = sum(1 for (_p, ch, _t) in region if _is_medical_chapter(ch))
    n_markers = sum(1 for (_p, ch, t) in region
                    if _PURITY_MARKER_RE.search(f"{ch or ''} {t or ''}"))
    return {
        "boundary": boundary,
        "strong": len(strong_pages),
        "region_chunks": len(region),
        "max_page": max(p for (p, _ch, _t) in rows if p is not None),
        "n_medical_in_region": n_medical,
        "n_markers_in_region": n_markers,
        "purity_ok": n_medical == 0 and n_markers >= 1,
    }


def analyze_contamination(chunks_df, *, min_strong=MIN_STRONG) -> dict:
    """Per-book findings computed purely from the indexed chunks.

    ``chunks_df`` is any mapping of column-name -> sequence with ``book``, ``page``,
    ``chapter`` and ``text`` (a pandas DataFrame or a plain dict of parallel lists — both
    support ``df["col"]``), so it is trivially injectable in tests. Returns
    ``{book: finding}`` for every book that crosses the strong-signature floor (including
    impure ones, whose ``purity_ok`` is False).
    """
    by_book: dict[str, list] = {}
    for book, page, chapter, text in zip(
            chunks_df["book"], chunks_df["page"], chunks_df["chapter"], chunks_df["text"]):
        if book is None:
            continue
        by_book.setdefault(book, []).append((page, chapter, text))

    findings: dict[str, dict] = {}
    for book, rows in by_book.items():
        f = _analyze_book(rows, min_strong=min_strong)
        if f is not None:
            findings[book] = f
    return findings


def detect_contaminated_regions(chunks_df, *, min_strong=MIN_STRONG) -> dict:
    """Map ``book -> boundary_page`` for every contaminated book that PASSES the purity check.

    Impure books (a medical chunk leaked into the appended region) are deliberately omitted —
    they must never be auto-purged. This is the function the hermetic test drives directly on
    an in-memory DataFrame.
    """
    return {book: f["boundary"]
            for book, f in analyze_contamination(chunks_df, min_strong=min_strong).items()
            if f["purity_ok"]}


def _load_cols(db, table, cols):
    """Read named columns from a LanceDB table as parallel python lists.

    Projects only the requested columns (skips the heavy ``vector`` column) with a fallback to
    a full ``to_arrow`` for older LanceDB versions. Returns empty lists when the table is
    absent and ``[None] * n`` for a missing column, so callers can ``zip`` without special-
    casing schema drift.
    """
    if table not in _table_names(db):
        return {c: [] for c in cols}
    tbl = db.open_table(table)
    try:
        at = tbl.to_lance().to_table(columns=list(cols))
    except Exception:
        at = tbl.to_arrow()
    names = set(at.schema.names)
    return {c: (at.column(c).to_pylist() if c in names else [None] * at.num_rows)
            for c in cols}


def gather(db):
    """Compute the contamination picture from the index (pure read).

    Returns ``(per_book, aborted, marker_hits, total, deleted_fig_ids)`` where:
      - ``per_book``: ``{book: {boundary, chunks, figures, strong, markers}}`` for every
        contaminated book that PASSED the purity check (the deletable region; counts are
        ``page >= boundary``);
      - ``aborted``: ``{book: finding}`` for contaminated books that FAILED the purity check —
        excluded from deletion, reported loudly (fail-safe);
      - ``marker_hits``: sorted, de-duplicated ``(book, page)`` secondary marker hits that fall
        OUTSIDE any detected region (report-only cross-check);
      - ``total``: total deletable rows (chunks + figures) across purity-passing books — what
        the exit code keys on alongside ``aborted``;
      - ``deleted_fig_ids``: the exact ``figures`` ids in the deletable regions (used to filter
        the captions JSONL).
    """
    ch = _load_cols(db, CHUNKS_TABLE, ["book", "page", "chapter", "text"])
    fg = _load_cols(db, FIGURES_TABLE, ["id", "book", "page"])

    findings = analyze_contamination(ch)
    regions = {b: f["boundary"] for b, f in findings.items() if f["purity_ok"]}
    aborted = {b: f for b, f in findings.items() if not f["purity_ok"]}

    per_book: dict[str, dict] = {}
    deleted_fig_ids: set = set()
    for book in sorted(regions):
        b = regions[book]
        n_chunks = sum(1 for bk, p in zip(ch["book"], ch["page"])
                       if bk == book and p is not None and p >= b)
        n_figs = 0
        for fid, bk, p in zip(fg["id"], fg["book"], fg["page"]):
            if bk == book and p is not None and p >= b:
                n_figs += 1
                if fid is not None:
                    deleted_fig_ids.add(fid)
        f = findings[book]
        per_book[book] = {"boundary": b, "chunks": n_chunks, "figures": n_figs,
                          "strong": f["strong"], "markers": f["n_markers_in_region"]}

    marker_hits: list = []
    seen: set = set()
    for bk, p, t in zip(ch["book"], ch["page"], ch["text"]):
        if not t or not MARKER_RE.search(t):
            continue
        b = regions.get(bk)
        covered = b is not None and p is not None and p >= b
        if not covered:
            key = (bk, p)
            if key not in seen:
                seen.add(key)
                marker_hits.append(key)
    marker_hits.sort(key=lambda kp: (str(kp[0]), kp[1] if kp[1] is not None else -1))

    total = sum(v["chunks"] + v["figures"] for v in per_book.values())
    return per_book, aborted, marker_hits, total, deleted_fig_ids


def _print_report(per_book, aborted, marker_hits, total):
    print("Contamination audit (index-based detection)\n")
    if per_book:
        print(f"  {'book':40s} {'boundary':>8s} {'chunks':>7s} {'figures':>7s} "
              f"{'strong':>7s} {'markers':>7s}  purity")
        for book, v in sorted(per_book.items()):
            print(f"  {book:40.40s} {v['boundary']:>8d} {v['chunks']:>7d} "
                  f"{v['figures']:>7d} {v['strong']:>7d} {v['markers']:>7d}  OK")
    else:
        print("  No contaminated book passed detection (nothing deletable).")

    if aborted:
        print("\n  !! PURITY CHECK FAILED — these books are EXCLUDED from purge (fail-safe):")
        for book, f in sorted(aborted.items()):
            print(f"     {book}: boundary {f['boundary']}, "
                  f"{f['n_medical_in_region']} MEDICAL-labelled chunk(s) inside "
                  f"[{f['boundary']}, {f['max_page']}] / {f['n_markers_in_region']} marker(s). "
                  f"NOT purged — investigate manually before any delete.")

    print(f"\n  Out-of-region marker hits (secondary cross-check, report-only): "
          f"{len(marker_hits)}")
    for book, page in marker_hits[:50]:
        print(f"    MARKER {book} p{page}")
    if len(marker_hits) > 50:
        print(f"    ... and {len(marker_hits) - 50} more")

    books = sorted(b for b, v in per_book.items() if v["chunks"] or v["figures"])
    print(f"\nSUMMARY: {total} contaminated rows across {len(books)} purgeable book(s)"
          + (f": {', '.join(books)}" if books else "")
          + (f"; {len(aborted)} book(s) flagged but EXCLUDED (purity failed)" if aborted else ""))
    if marker_hits and total == 0 and not aborted:
        print("  NOTE: marker hits exist but none is in a detected region — these are likely "
              "false positives (e.g. citation author 'Rothschild', the reptilian brain). "
              "Review manually; they do NOT gate this exit code.")
    return total, books


def do_audit(db):
    per_book, aborted, marker_hits, total, _ = gather(db)
    _print_report(per_book, aborted, marker_hits, total)
    return 1 if (total > 0 or aborted) else 0


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


def do_apply(db, index_dir):
    index_dir = Path(index_dir)
    per_book, aborted, marker_hits, total, deleted_fig_ids = gather(db)
    _print_report(per_book, aborted, marker_hits, total)

    if aborted:
        print("\nWARNING: one or more books failed the purity check and were EXCLUDED from "
              "this purge (see above). They were NOT modified.")

    if total == 0:
        if aborted:
            print("\nNo purity-passing contamination to purge, but flagged book(s) remain — "
                  "resolve them manually. No backup written, no rows deleted.")
            return 1
        print("\nNo contamination detected — nothing to purge (no-op).")
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

    # (2) Delete the detected region from both tables.
    names = _table_names(db)
    deleted_chunks = deleted_figs = 0
    for book, info in per_book.items():
        if not (info["chunks"] or info["figures"]):
            continue
        pred = f"book = {_sql_str(book)} AND page >= {int(info['boundary'])}"
        if CHUNKS_TABLE in names:
            db.open_table(CHUNKS_TABLE).delete(pred)
            deleted_chunks += info["chunks"]
        if FIGURES_TABLE in names:
            db.open_table(FIGURES_TABLE).delete(pred)
            deleted_figs += info["figures"]
        print(f"  deleted {book}: {info['chunks']} chunks + {info['figures']} figures "
              f"(page >= {info['boundary']})")

    # (3) Rewrite the captions JSONL, dropping lines for deleted figures.
    # Atomic write (tmp + os.replace) so a crash mid-rewrite can't corrupt the file.
    dropped_caps = 0
    if caps_path.exists() and deleted_fig_ids:
        kept, dropped_caps = _filter_caption_lines(
            caps_path.read_text().splitlines(), deleted_fig_ids)
        tmp_caps = caps_path.with_suffix(caps_path.suffix + ".tmp")
        tmp_caps.write_text(("\n".join(kept) + "\n") if kept else "")
        os.replace(tmp_caps, caps_path)

    print(f"\nPurged {deleted_chunks} chunks + {deleted_figs} figures; "
          f"dropped {dropped_caps} caption line(s). Backup: {backup}")

    # (4) Verify the purged regions are gone (and signal via exit code).
    per_after, _aborted_after, _mh, total_after, _ = gather(db)
    if total_after:
        print(f"WARNING: {total_after} contaminated rows still present after purge.")
        return 1
    print("Verified clean (0 deletable contaminated rows remain).")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="purge_contamination",
        description="Audit (default, read-only) or --apply a guarded purge of appended "
                    "non-medical contamination from the LanceDB index. Detection is computed "
                    "from the indexed chunks (no PDF needed).")
    ap.add_argument("--apply", action="store_true",
                    help="back up then DELETE detected contaminated rows "
                         "(default is read-only audit)")
    ap.add_argument("--index-dir", default=None,
                    help="LanceDB index dir (default: config INDEX_DIR)")
    args = ap.parse_args(argv)

    if args.index_dir is None:
        from neuro_core.config import load_config
        index_dir = str(load_config().index_dir)
    else:
        index_dir = args.index_dir

    db = lancedb.connect(str(index_dir))
    if args.apply:
        return do_apply(db, index_dir)
    return do_audit(db)


if __name__ == "__main__":
    sys.exit(main())
