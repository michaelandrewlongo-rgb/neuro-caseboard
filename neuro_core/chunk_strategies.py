"""Parsing/chunking strategies for the ingestion ablation benchmark.

The production chunker (`chunk.py::chunk_page`) is *page-anchored*: it word-windows the
text of each page independently and never crosses a page boundary. This module generalises
that into five named boundary strategies that all share ONE packer, so `max_words` and
`overlap` stay orthogonal knobs layered on top of *where boundaries are allowed*:

    strategy            atom (indivisible unit)         hard barrier
    ------------------  ------------------------------  ---------------------------
    page (baseline)     whole page text                 every page change  (== chunk.py)
    paragraph           blank-line-delimited paragraph  none (packs across pages)
    sentence            sentence (.!? split)            none (packs across pages)
    heading             heading-delimited section       every detected heading
    chapter             whole chapter text (pages cat)  every chapter change

All strategies feed `pack()`, which greedily fills a chunk up to `max_words`, closes it at
a barrier or when the next atom would overflow, and carries the trailing `overlap` words
into the next chunk. An atom longer than `max_words` is hard word-windowed (this is exactly
what the page baseline does today for a long page). A chunk's page/chapter metadata is that
of its first atom.

Run `python3 -m neuro_core.chunk_strategies` for the self-check.
"""
import re

from neuro_core.chunk import Chunk

# A sentence ends at .!? followed by whitespace and an uppercase letter / digit / paren.
# Deliberately simple: abbreviations ("e.g.", "Fig. 3") will occasionally over-split, which
# only shifts a boundary by one clause — acceptable for a chunk-boundary heuristic.
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
# Blank-line paragraph separator: one or more lines that are empty/whitespace.
_PARA = re.compile(r"\n\s*\n+")
# Heading line heuristic: a short line (<=8 words), no terminal ., that is ALL CAPS or a
# numbered/section title. Runs on individual physical lines.
_NUM_HEAD = re.compile(r"^\s*(\d+(\.\d+)*)\s+[A-Z]")


class Atom:
    __slots__ = ("text", "page", "chapter", "has_figure", "caption", "figure_path")

    def __init__(self, text, rec):
        self.text = text
        self.page = rec.page
        self.chapter = rec.chapter
        self.has_figure = rec.has_figure
        self.caption = rec.caption
        self.figure_path = rec.figure_path


def _norm(text):
    """Collapse layout newlines to spaces (PDF emits one \\n per visual line)."""
    return " ".join(text.split())


def page_atoms(records):
    return [Atom(r.text, r) for r in records if r.text.strip()]


def paragraph_atoms(records):
    out = []
    for r in records:
        parts = _PARA.split(r.text)
        if len(parts) == 1:            # book has no blank-line paragraphs on this page
            parts = [r.text]
        for p in parts:
            if p.strip():
                out.append(Atom(_norm(p), r))
    return out


def sentence_atoms(records):
    out = []
    for r in records:
        for s in _SENT.split(_norm(r.text)):
            if s.strip():
                out.append(Atom(s.strip(), r))
    return out


def _is_heading(line):
    s = line.strip()
    if not s or len(s.split()) > 8 or s.endswith("."):
        return False
    if _NUM_HEAD.match(s):
        return True
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def heading_atoms(records):
    """Split each page into sections that START at a detected heading line. The barrier is
    encoded by tagging the first atom of each section — `pack(group="heading")` restarts a
    chunk whenever an atom's `is_head` flag is set."""
    out = []
    for r in records:
        cur = []
        for line in r.text.split("\n"):
            if _is_heading(line) and cur:
                a = Atom(_norm("\n".join(cur)), r)
                a_head = True
                out.append((a, a_head))
                cur = [line]
            else:
                cur.append(line)
        if cur:
            out.append((Atom(_norm("\n".join(cur)), r), True))
    # first atom of each page-section is a barrier; return atoms with a parallel flag list
    return out


def chapter_atoms(records):
    """One atom per contiguous run of same (book, chapter) pages — text concatenated so a
    chunk can span the page breaks the baseline forbids."""
    out = []
    buf, first = [], None
    key = object()
    for r in records:
        rk = (r.chapter,)
        if rk != key and buf:
            out.append(Atom(_norm(" ".join(buf)), first))
            buf = []
        if not buf:
            first = r
            key = rk
        if r.text.strip():
            buf.append(r.text)
    if buf:
        out.append(Atom(_norm(" ".join(buf)), first))
    return out


def _split_words(words, max_words, overlap):
    """Word-window a too-long atom (the page baseline's behavior for a long page)."""
    step = max(1, max_words - overlap)
    out, start = [], 0
    while start < len(words):
        out.append(words[start:start + max_words])
        if start + max_words >= len(words):
            break
        start += step
    return out


def pack(atoms, max_words, overlap, *, group=None):
    """Greedily merge atoms into <=max_words chunks with word overlap.

    `group`: barrier key. "page"/"chapter" close the chunk on a metadata change; "heading"
    expects `atoms` as (atom, is_head) tuples and closes on is_head; None never barriers on
    metadata (packs across pages). An atom longer than max_words is hard word-windowed.
    """
    if group == "heading":
        pairs = atoms
    else:
        pairs = [(a, False) for a in atoms]

    chunks = []
    cur_words, cur_meta = [], None
    last_key = None

    def flush():
        nonlocal cur_words
        if cur_words:
            chunks.append((cur_words, cur_meta))
            cur_words = []

    for a, is_head in pairs:
        key = a.page if group == "page" else (a.chapter if group == "chapter" else None)
        barrier = (group == "heading" and is_head) or (
            group in ("page", "chapter") and last_key is not None and key != last_key)
        if barrier:
            flush()
        last_key = key
        if cur_meta is None or not cur_words:
            cur_meta = a
        words = a.text.split()
        if len(cur_words) + len(words) > max_words:
            if not cur_words and len(words) > max_words:
                # single oversized atom -> hard word-window it
                for win in _split_words(words, max_words, overlap):
                    chunks.append((win, a))
                cur_meta = None
                continue
            flush()
            # overlap carry from the just-closed chunk
            if overlap and chunks:
                cur_words = chunks[-1][0][-overlap:] + words
            else:
                cur_words = list(words)
            cur_meta = a
            # if carry+atom still overflow, window it down
            if len(cur_words) > max_words:
                wins = _split_words(cur_words, max_words, overlap)
                for win in wins[:-1]:
                    chunks.append((win, a))
                cur_words = wins[-1]
        else:
            cur_words.extend(words)
    flush()

    out = []
    for i, (words, meta) in enumerate(chunks):
        out.append(Chunk(
            id=f"{'strat'}::{meta.page}::{i}",
            book=getattr(meta, "book", "") or "",
            chapter=meta.chapter, page=meta.page,
            text=" ".join(words),
            has_figure=meta.has_figure, caption=meta.caption,
            figure_path=meta.figure_path,
        ))
    return out


def chunk_records(records, strategy, max_words, overlap):
    """Chunk `records` (a book's PageRecords) with `strategy` at (max_words, overlap).
    Chunk ids are made unique per book by the caller if needed."""
    if strategy == "page":
        return pack(page_atoms(records), max_words, overlap, group="page")
    if strategy == "paragraph":
        return pack(paragraph_atoms(records), max_words, overlap, group=None)
    if strategy == "sentence":
        return pack(sentence_atoms(records), max_words, overlap, group=None)
    if strategy == "heading":
        return pack(heading_atoms(records), max_words, overlap, group="heading")
    if strategy == "chapter":
        return pack(chapter_atoms(records), max_words, overlap, group="chapter")
    raise ValueError(f"unknown strategy {strategy!r}")


STRATEGIES = ("page", "paragraph", "sentence", "heading", "chapter")


def _selfcheck():
    class R:
        def __init__(self, text, page, chapter="C1"):
            self.text = text
            self.page = page
            self.chapter = chapter
            self.book = "B"
            self.has_figure = False
            self.caption = None
            self.figure_path = None

    # page barrier: two 5-word pages, max_words 100 -> must stay 2 chunks (no cross-page)
    recs = [R("one two three four five", 1), R("six seven eight nine ten", 2)]
    cp = chunk_records(recs, "page", 100, 0)
    assert len(cp) == 2, [c.text for c in cp]
    # chapter packs across pages -> 1 chunk
    cc = chunk_records(recs, "chapter", 100, 0)
    assert len(cc) == 1, [c.text for c in cc]
    assert cc[0].text.split() == "one two three four five six seven eight nine ten".split()
    # sentence atoms never split a sentence; max_words forces a boundary between sentences
    recs2 = [R("Alpha beta gamma delta. Epsilon zeta eta theta. Iota kappa.", 1)]
    cs = chunk_records(recs2, "sentence", 5, 0)
    assert all(len(c.text.split()) <= 5 for c in cs), [c.text for c in cs]
    assert cs[0].text == "Alpha beta gamma delta."
    # overlap carry: 10 words, max 5, overlap 2 -> second chunk starts with last 2 of first
    recs3 = [R(" ".join(f"w{i}" for i in range(10)), 1)]
    co = chunk_records(recs3, "page", 5, 2)
    assert co[0].text.split() == ["w0", "w1", "w2", "w3", "w4"]
    assert co[1].text.split()[:2] == ["w3", "w4"], co[1].text
    # oversized single atom is word-windowed, not dropped
    assert sum(len(c.text.split()) for c in co) >= 10
    # heading barrier: a heading line starts a new chunk
    recs4 = [R("intro words here\nAORTA\naorta facts follow here", 1)]
    ch = chunk_records(recs4, "heading", 100, 0)
    assert len(ch) == 2, [c.text for c in ch]
    print("chunk_strategies selfcheck OK")


if __name__ == "__main__":
    _selfcheck()
