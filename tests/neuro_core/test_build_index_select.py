from pathlib import Path

from neuro_core.scripts.build_index import select_pdfs


def _pdfs(*names):
    return [Path(f"/corpus/{n}.pdf") for n in names]


def test_default_is_full_overwrite():
    pdfs = _pdfs("A", "B")
    sel, mode = select_pdfs(pdfs, book_args=[], new_only=False, indexed_books=set())
    assert sel == pdfs
    assert mode == "overwrite"


def test_new_only_skips_already_indexed():
    pdfs = _pdfs("A", "B", "C")
    sel, mode = select_pdfs(pdfs, book_args=[], new_only=True, indexed_books={"A", "B"})
    assert [p.stem for p in sel] == ["C"]
    assert mode == "append"


def test_new_only_when_nothing_indexed_takes_all_as_append():
    pdfs = _pdfs("A", "B")
    sel, mode = select_pdfs(pdfs, book_args=[], new_only=True, indexed_books=set())
    assert [p.stem for p in sel] == ["A", "B"]
    assert mode == "append"


def test_book_filters_by_stem():
    pdfs = _pdfs("A", "B")
    sel, mode = select_pdfs(pdfs, book_args=["B"], new_only=False, indexed_books=set())
    assert [p.stem for p in sel] == ["B"]
    assert mode == "append"


def test_book_accepts_a_path_argument():
    pdfs = _pdfs("A", "B")
    sel, mode = select_pdfs(pdfs, book_args=["/some/dir/B.pdf"], new_only=False, indexed_books=set())
    assert [p.stem for p in sel] == ["B"]
    assert mode == "append"
