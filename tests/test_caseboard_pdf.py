"""Guard the build (Dossier) Executive-Navy HTML builder — proves the exec_navy extraction
left the build pathway's output intact (this builder had no offline test before)."""
from neuro_caseboard.caseboard_pdf import build_caseboard_html
from neuro_caseboard.model import Dossier, EvidenceSummary, Section, Claim


def _dossier():
    return Dossier(
        title="C5–6 ACDF",
        summary=EvidenceSummary(supported=2, to_verify=1, quarantined=0),
        sections=[Section(
            heading="Anatomy at risk", intro="Structures near the approach.",
            claims=[Claim(text="The **vertebral artery** runs in the foramen transversarium.",
                          why="Avoid far-lateral dissection.", status="supported")])])


def test_build_caseboard_html_carries_exec_navy_tokens_and_content():
    doc = build_caseboard_html(_dossier(), subtitle="cervical case")
    assert "NEURO·CASEBOARD" in doc                 # masthead brand
    assert "Archivo" in doc and "Source+Serif+4" in doc  # three-font role system
    assert "#0e7490" in doc                              # deep-teal accent
    assert "C5–6 ACDF" in doc                       # title
    assert "<b>vertebral artery</b>" in doc              # inline bold via shared helper
    assert "Corpus-supported" in doc                     # status-marker label
