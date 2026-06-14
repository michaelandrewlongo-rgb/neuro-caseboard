from neuro_caseboard.board_view import board_view, BoardView
from neuro_caseboard.model import Dossier, Section, FigureItem, EvidenceSummary


def _fig(path, fid):
    return FigureItem(fig_id=fid, image_path=path, caption=f"caption {fid}",
                      citation="Book, p.1")


def test_board_view_dedups_figures_by_path_in_first_seen_order():
    d = Dossier(
        title="C5-6 ACDF",
        summary=EvidenceSummary(supported=3, to_verify=1, quarantined=0),
        sections=[
            Section(heading="Approach", figures=[_fig("/x/p1.png", "F1"),
                                                 _fig("/x/p2.png", "F2")]),
            Section(heading="Anatomy", figures=[_fig("/x/p1.png", "F1b"),  # same path
                                                _fig("/x/p3.png", "F3")]),
        ],
    )
    v = board_view(d)
    assert isinstance(v, BoardView)
    assert v.title == "C5-6 ACDF"
    assert [f.image_path for f in v.figures] == ["/x/p1.png", "/x/p2.png", "/x/p3.png"]
    assert v.summary.supported == 3 and v.summary.to_verify == 1


def test_board_view_markdown_keeps_body_but_strips_inline_images():
    d = Dossier(
        title="T", summary=EvidenceSummary(),
        sections=[Section(heading="Approach", intro="midline exposure",
                          figures=[_fig("/x/p1.png", "F1")])],
    )
    v = board_view(d)
    assert "Approach" in v.markdown            # body retained
    assert "midline exposure" in v.markdown    # intro retained
    assert "![" not in v.markdown              # inline image embeds stripped
    assert [f.image_path for f in v.figures] == ["/x/p1.png"]
