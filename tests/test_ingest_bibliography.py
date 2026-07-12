"""Bibliography line-strip (FIX_PLAN §1.1): drop reference lines, keep clinical prose.

Line-level so a page that mixes prose and references keeps its prose — the failure mode a
chunk-level or page-level drop would cause.
"""
from neuro_core.ingest import _strip_bibliography, _CITATION_LINE, _FOLIO


def test_references_heading_truncates_page():
    text = "Clinical prose about the MCA.\nMore prose.\nREFERENCES\n1. Smith JD. Foo. 2020.\n2. Doe AB."
    clean, removed = _strip_bibliography(text)
    assert "Clinical prose about the MCA." in clean
    assert "Smith JD" not in clean
    assert removed > 0


def test_prose_sharing_a_page_with_refs_is_kept():
    # The 495-mixed-chunk case: prose then a reference tail on one page.
    text = "The anterior choroidal artery supplies the posterior limb.\nREFERENCES\n1. Rhoton AL, et al. 1998."
    clean, _ = _strip_bibliography(text)
    assert "anterior choroidal artery" in clean
    assert "Rhoton AL" not in clean


def test_numbered_citation_lines_dropped_without_heading():
    # .eN reference pages often have no REFERENCES heading.
    text = "12. Gurrieri F, Trask BJ, et al. Physical mapping. Nat Genet. 1993;3:247.\nReal prose here."
    clean, _ = _strip_bibliography(text)
    assert "Real prose here." in clean
    assert "Gurrieri" not in clean


def test_pure_prose_untouched():
    text = "The pterional approach exposes the sylvian fissure.\nSplit it to reach the ICA."
    clean, removed = _strip_bibliography(text)
    assert clean == text and removed == 0


def test_folio_regex_accepts_bare_and_electronic():
    assert _FOLIO.match("3357")
    assert _FOLIO.match("246.e2")
    assert _FOLIO.match("9.e22")
    assert not _FOLIO.match("Figure")
    assert not _FOLIO.match("12345")  # 5 digits is not a folio


def test_citation_line_regex():
    assert _CITATION_LINE.match("12. Smith JD, Jones AB, et al. Title.")
    assert not _CITATION_LINE.match("The patient presented with aphasia.")
