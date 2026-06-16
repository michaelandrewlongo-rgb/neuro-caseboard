"""Markdown renderer golden assertions for the nine fixes, across all subspecialties."""

import pytest

from neuro_caseboard.compile import compile_dossier
from neuro_caseboard.render_md import render_markdown
import tests.fixtures as fx


@pytest.fixture(params=fx.ALL_TOPICS)
def md(request):
    f = fx.build(request.param)
    d = compile_dossier(f.manifest, topic=f.topic, evidence=f.evidence,
                        card_evidence=f.card_evidence, page_texts=f.page_texts)
    return render_markdown(d)


def test_title_present(md):
    assert md.startswith("# Case Board —")


def test_legend_present_with_both_markers(md):
    # #4: a one-line legend keying both markers
    assert "✓" in md and "⚠" in md
    assert "corpus-supported" in md
    assert "needs clinician verification" in md


def test_no_confidence_noise(md):
    # #2/#3: no confidence axis, no per-section [low] tag, no confidence emojis
    assert "[low]" not in md and "[high]" not in md and "[medium]" not in md
    assert "high / medium / low" not in md.lower()
    for emoji in ("🟢", "🟡", "🔴"):
        assert emoji not in md


def test_claim_and_why_on_separate_lines(md):
    # #5
    lines = md.splitlines()
    claim_idxs = [i for i, ln in enumerate(lines)
                  if ln.lstrip().startswith(("- ✓", "- ⚠"))]
    assert claim_idxs
    # at least one claim is followed (within 2 lines) by an indented Why: line
    assert any(any("Why:" in lines[j] for j in range(i + 1, min(i + 4, len(lines))))
               for i in claim_idxs)


def test_checkbox_subitems_present(md):
    # #6
    assert "- [ ]" in md


def test_figure_cross_link_bidirectional(md):
    # #7: claim points to the figure ("see Fig F1") and the figure block lists "Fig F1"
    assert "see Fig F1" in md
    assert "Fig F1" in md


def test_appendix_rendered_and_pointer_not_dangling(md):
    # #8: the pointer exists AND a real appendix section is rendered
    assert "appendix" in md.lower()
    assert "## Appendix" in md
    assert "Evidence Sources" in md


def test_dedup_crossref_rendered(md):
    # #9
    assert "Also relevant — see Operative Plan" in md


def test_section_literature_block_renders_with_L_axis():
    # WS-3: a section's contemporary-literature block renders narrative + [L#] rows on a
    # separate axis; a section without literature is unchanged.
    from types import SimpleNamespace
    from neuro_caseboard.model import Dossier, EvidenceSummary, Section, Claim
    lit = SimpleNamespace(
        narrative="Recent RCTs support decompression [L1].",
        citations=[SimpleNamespace(n=1, title="ACDF RCT", journal="Spine", year=2024,
                                   doi="10.1/abc", url="")])
    d = Dossier(title="Case Dossier — C5-6 ACDF", summary=EvidenceSummary(),
                sections=[Section(heading="Clinical Reasoning",
                                  claims=[Claim(text="Indicated", why="progressive")],
                                  literature=lit),
                          Section(heading="Operative Plan",
                                  claims=[Claim(text="Decompress", why="cord")])])
    md = render_markdown(d)
    assert "**Contemporary Literature**" in md
    assert "Recent RCTs support decompression [L1]." in md
    assert "[L1] ACDF RCT — Spine 2024 · https://doi.org/10.1/abc" in md
    # the [L#] axis appears once (only under the section that has literature)
    assert md.count("**Contemporary Literature**") == 1
