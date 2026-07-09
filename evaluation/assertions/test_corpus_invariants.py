"""Deterministic corpus/index invariants — D1-D8 (FIX_PLAN §6.2).

Free, offline, zero-LLM, zero-human. Run against a built LanceDB index:

    INDEX_DIR=~/neuro-textbook-rag/index python -m pytest evaluation/assertions/test_corpus_invariants.py -q

NOT collected by CI (testpaths = tests/, vendor/caseprep/tests/) because CI has no index. This
suite IS the Phase-1 gate: on the CURRENT index most of these FAIL, and that failure is the
measured "before". After the guarded rebuild they must pass. Skips cleanly if no index is present.

Run `python evaluation/assertions/test_corpus_invariants.py` (no pytest) to print the baseline
numbers without asserting — useful for logging the before/after in the experiment ledger.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

INDEX_DIR = os.environ.get("INDEX_DIR", str(Path.home() / "neuro-textbook-rag" / "index"))
EXPECTED_BOOKS = 19


def _load_chunks():
    try:
        import lancedb
    except Exception:  # pragma: no cover
        pytest.skip("lancedb not installed")
    try:
        db = lancedb.connect(INDEX_DIR)
        if "chunks" not in db.table_names():
            pytest.skip(f"no chunks table at {INDEX_DIR}")
        return db.open_table("chunks").to_pandas()
    except Exception as e:  # pragma: no cover
        pytest.skip(f"index unreadable at {INDEX_DIR}: {e}")


# ---- detectors (shared by the asserting tests and the baseline printer) --------------------------
_CITE_SIGNALS = [
    re.compile(r"\bet al\b"),
    re.compile(r"\b(19|20)\d\d;\s?\d+"),            # journal vol: 1993;3
    re.compile(r"\b\d+\(\d+\):\d+"),                 # 45(3):123
    re.compile(r"\b[A-Z][a-z]+ [A-Z]{1,3},"),       # Smith JD,
    re.compile(r"\bdoi:", re.I),
]


def _is_bibliography(text: str) -> bool:
    """A reference-list chunk: dense in citation punctuation, sparse in prose.

    >=6 'et al' OR a starts-with-REFERENCES tail OR >=0.4 citation-signals per 100 words.
    """
    t = text or ""
    words = max(len(t.split()), 1)
    signals = sum(len(p.findall(t)) for p in _CITE_SIGNALS)
    density = signals / (words / 100.0)
    return t.count("et al") >= 6 or density >= 40.0


def _chapter_is_junk(ch: str) -> bool:
    c = (ch or "").strip()
    if not c:
        return True
    if len(c) > 60:                          # a filename or hash blob
        return True
    if re.search(r"\.pdf|p\.\d+-\d+", c):     # embedded filename/page-range
        return True
    if c.lower() in {"copyright", "dedication", "contributor", "contributors",
                     "preface", "index", "front matter"}:
        return True
    if re.match(r"^[A-Za-z0-9]{40,}$", c):    # pure hash token
        return True
    return False


# ---- D1: bibliography fraction < 1% --------------------------------------------------------------
def test_D1_bibliography_fraction_under_1pct():
    c = _load_chunks()
    frac = c.text.fillna("").map(_is_bibliography).mean()
    assert frac < 0.01, f"D1: {frac:.1%} of chunks are bibliography (target <1%)"


# ---- D2: chapter label is a real label, not a filename/hash/front-matter, >=95% ------------------
def test_D2_chapter_labels_are_real():
    c = _load_chunks()
    junk = c.chapter.fillna("").map(_chapter_is_junk).mean()
    assert junk < 0.05, f"D2: {junk:.1%} of chunks have a junk chapter label (target <5%)"


# ---- D2b: Youmans in-text CHAPTER header agrees with the stored label, >=95% ---------------------
def test_D2b_youmans_chapter_agreement():
    c = _load_chunks()
    y = c[c.book.str.contains("Youmans", case=False, na=False)].copy()
    y["true_ch"] = y.text.str.extract(r"CHAPTER (\d{1,3})\b")[0]
    y["lbl_ch"] = y.chapter.str.extract(r"^(\d{1,3}) - ")[0]
    m = y.dropna(subset=["true_ch", "lbl_ch"])
    if len(m) == 0:
        pytest.skip("no Youmans chunks with both an in-text and a labelled chapter number")
    agree = (m.true_ch == m.lbl_ch).mean()
    assert agree >= 0.95, f"D2b: only {agree:.1%} of Youmans labels match the in-text CHAPTER header"


# ---- D3: every chunk carries a printed_page (folio) ----------------------------------------------
def test_D3_printed_page_present():
    c = _load_chunks()
    assert "printed_page" in c.columns, "D3: no printed_page column (folio never extracted)"
    resolved = c.printed_page.notna().mean()
    assert resolved >= 0.90, f"D3: only {resolved:.1%} of chunks resolved a printed_page (target >=90%)"


# ---- D6: chunk length sanity ---------------------------------------------------------------------
def test_D6_chunk_length_sanity():
    c = _load_chunks()
    lens = c.text.fillna("").str.len()
    assert (lens < 50).sum() == 0, f"D6: {(lens < 50).sum()} chunks under 50 chars"


# ---- corpus completeness -------------------------------------------------------------------------
def test_book_count():
    c = _load_chunks()
    n = c.book.nunique()
    assert n == EXPECTED_BOOKS, f"expected {EXPECTED_BOOKS} books, found {n}"


# ---- baseline printer (no asserts): python evaluation/assertions/test_corpus_invariants.py --------
def _print_baseline():
    import lancedb

    c = lancedb.connect(INDEX_DIR).open_table("chunks").to_pandas()
    n = len(c)
    bib = c.text.fillna("").map(_is_bibliography).mean()
    junk = c.chapter.fillna("").map(_chapter_is_junk).mean()
    has_folio = "printed_page" in c.columns
    y = c[c.book.str.contains("Youmans", case=False, na=False)].copy()
    y["true_ch"] = y.text.str.extract(r"CHAPTER (\d{1,3})\b")[0]
    y["lbl_ch"] = y.chapter.str.extract(r"^(\d{1,3}) - ")[0]
    m = y.dropna(subset=["true_ch", "lbl_ch"])
    agree = (m.true_ch == m.lbl_ch).mean() if len(m) else float("nan")
    print(f"index: {INDEX_DIR}")
    print(f"chunks: {n:,}  books: {c.book.nunique()}")
    print(f"D1 bibliography fraction:   {bib:6.1%}   (target <1%)")
    print(f"D2 junk chapter labels:     {junk:6.1%}   (target <5%)")
    print(f"D2b Youmans label agreement:{agree:6.1%}   (target >=95%)  [n={len(m)}]")
    print(f"D3 printed_page column:     {'present' if has_folio else 'ABSENT':>6}   (target present, >=90% resolved)")


if __name__ == "__main__":
    _print_baseline()
