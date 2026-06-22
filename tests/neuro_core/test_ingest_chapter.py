# tests/neuro_core/test_ingest_chapter.py
"""Chapter attribution + corpus-contamination guard in neuro_core.ingest.

Uses synthetic ``get_toc()``-shaped fixtures (list of ``[level, title, page]``) so no
real PDF is needed in CI. Reproduces the real Youmans failure modes:
  * a sparse TOC that blankets huge un-bookmarked gaps with one distant label, and
  * three copies of David Icke's "Perceptions of a Renegade Mind" appended after the
    medical content.
"""
from neuro_core.ingest import (
    _is_medical_chapter,
    _chapter_for_page,
    _classify_toc,
)


class _FakeDoc:
    """Minimal stand-in for a PyMuPDF document exposing ``get_toc()``."""

    def __init__(self, toc):
        self._toc = toc

    def get_toc(self):
        return self._toc


# --- _is_medical_chapter ----------------------------------------------------

def test_is_medical_chapter_true_for_numbered_chapter():
    assert _is_medical_chapter("25 - Positioning for Spine Surgery") is True
    assert _is_medical_chapter("1 - History") is True
    assert _is_medical_chapter("300 - Radiosurgery for Intracranial Vascular") is True


def test_is_medical_chapter_false_for_junk_and_contamination():
    assert _is_medical_chapter("Copyright") is False
    assert _is_medical_chapter("Chapter 5: There is no 'virus'") is False
    assert _is_medical_chapter("Perceptions of a Renegade Mind") is False
    assert _is_medical_chapter("5yk4n23ycnpq9lc2A5dqvlhvrs2rhdbs9c6jz5gnc3xpr788") is False
    assert _is_medical_chapter("") is False


# --- _chapter_for_page: cap-the-gap -----------------------------------------

def test_far_page_beyond_max_gap_is_unknown():
    # A medical bookmark at 649, then nothing until 3000 — a page at 2000 is far past
    # the only preceding bookmark, so the sparse TOC cannot identify its chapter.
    entries = [(649, "25 - Positioning for Spine Surgery"), (3000, "26 - Next")]
    assert _chapter_for_page(entries, 2000) is None


def test_page_within_max_gap_gets_the_label():
    entries = [(649, "25 - Positioning for Spine Surgery"), (3000, "26 - Next")]
    assert _chapter_for_page(entries, 700) == "25 - Positioning for Spine Surgery"
    # exactly at the boundary (gap == max_gap) still labels
    assert _chapter_for_page(entries, 649 + 120) == "25 - Positioning for Spine Surgery"
    # one page past the boundary is unknown
    assert _chapter_for_page(entries, 649 + 121) is None


def test_page_before_first_bookmark_is_unknown():
    entries = [(78, "1 - History")]
    assert _chapter_for_page(entries, 10) is None


def test_custom_max_gap_is_respected():
    entries = [(100, "1 - A")]
    assert _chapter_for_page(entries, 150, max_gap=30) is None
    assert _chapter_for_page(entries, 120, max_gap=30) == "1 - A"


# --- densely-bookmarked normal book: no regression --------------------------

def test_dense_normal_book_labels_every_page():
    # Bookmarks every ~30 pages — every page is close to a bookmark, so every page is
    # labelled (the cap never trips). Titles need not be the numbered medical pattern.
    toc = [[1, f"Chapter {n} - Topic {n}", 1 + n * 30] for n in range(20)]
    entries, content_end = _classify_toc(_FakeDoc(toc))
    assert content_end is None
    assert len(entries) == 20
    for page in range(1, 1 + 20 * 30):
        assert _chapter_for_page(entries, page) is not None


# --- content_end / contamination exclusion ----------------------------------

def _youmans_like_toc():
    return [
        [1, "front youmans cover", 1],
        [2, "Copyright", 4],
        [2, "DEDICATION", 8],
        [2, "1 - History", 78],
        [2, "25 - Positioning for Spine Surgery", 649],
        [1, "5yk4n23ycnpq9lc2A5dqvlhvrs2rhdbs9c6jz5gnc3xpr788fm4zwd2", 3002],
        [2, "300 - Radiosurgery for Intracranial Vascular", 4181],
        [1, "Perceptions of a Renegade Mind by David Icke (z-lib.org)", 6330],
        [2, "Chapter 1: 'I'm thinking' - Oh, but are you?", 6345],
        [2, "Chapter 2: Renegade perception", 6371],
    ]


def test_content_end_is_first_contamination_after_medical():
    entries, content_end = _classify_toc(_FakeDoc(_youmans_like_toc()))
    # boundary is the "Perceptions of a Renegade Mind" bookmark, before the colon-chapters
    assert content_end == 6330


def test_pages_at_or_after_content_end_are_excluded():
    _, content_end = _classify_toc(_FakeDoc(_youmans_like_toc()))
    # extract_pages skips pageno >= content_end (1-based)
    assert content_end is not None
    for pageno in (6330, 6345, 6500, 7865):
        assert pageno >= content_end           # would be excluded
    for pageno in (78, 649, 4181, 6329):
        assert pageno < content_end             # still indexed


def test_classify_drops_contamination_and_junk_from_labels():
    entries, _ = _classify_toc(_FakeDoc(_youmans_like_toc()))
    titles = [t for _pg, t in entries]
    # medical chapters kept
    assert "1 - History" in titles
    assert "25 - Positioning for Spine Surgery" in titles
    # front-matter, random-string and contamination dropped
    assert "Copyright" not in titles
    assert "DEDICATION" not in titles
    assert not any("renegade" in t.lower() for t in titles)
    assert not any(t.startswith("Chapter 1:") for t in titles)
    assert not any(len(t) > 25 and " " not in t for t in titles)


def test_no_medical_chapters_means_no_boundary():
    # A book with no numbered medical chapters and no contamination indexes fully.
    toc = [
        [1, "Introduction", 1],
        [1, "Methods", 3],
        [1, "Results", 5],
    ]
    entries, content_end = _classify_toc(_FakeDoc(toc))
    assert content_end is None
    assert [t for _pg, t in entries] == ["Introduction", "Methods", "Results"]


def test_colon_chapter_without_medical_anchor_is_not_contamination():
    # A clean book that legitimately uses "Chapter N:" must NOT be truncated, because the
    # colon-chapter signal is only trusted past the last medical chapter (none here).
    toc = [
        [1, "Chapter 1: Getting Started", 1],
        [1, "Chapter 2: Going Deeper", 40],
    ]
    _entries, content_end = _classify_toc(_FakeDoc(toc))
    assert content_end is None
