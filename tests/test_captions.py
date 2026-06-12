"""Figure caption completion (#7): recover the full caption from page text, plus a
subspecialty-neutral relevance line."""

import pytest

from neuro_caseboard.captions import assemble_caption, complete_caption, relevance_line
import tests.fixtures as fx


def test_assemble_joins_continuation_lines_until_blank():
    lines = [
        "Figure 69-1. Anterior cervical construct",
        "spanning the corpectomy defect from C4 to C6",
        "with an interbody cage and anterior plate fixation.",
        "",
        "Unrelated body text that must not be captured.",
    ]
    out = assemble_caption(lines[0], lines[1:])
    assert out.startswith("Figure 69-1. Anterior cervical construct spanning")
    assert out.endswith("fixation.")
    assert "Unrelated body text" not in out


def test_assemble_stops_at_next_figure_label():
    out = assemble_caption("Figure 1. First caption",
                           ["continues here", "Figure 2. Second caption"])
    assert "First caption continues here" in out
    assert "Second caption" not in out


@pytest.mark.parametrize("topic", fx.ALL_TOPICS)
def test_complete_caption_recovers_full_text_for_every_topic(topic):
    f = fx.build(topic)
    rec = f.evidence[0]
    truncated = rec.metadata["caption"]
    full = complete_caption(rec, page_text=f.page_texts[rec.metadata["figure_path"]])
    # the recovered caption must be longer than the first-line truncation and complete
    assert len(full) > len(truncated)
    assert full.endswith(".")
    assert truncated.split(".")[0] in full  # keeps the figure label


def test_complete_caption_without_page_text_returns_the_first_line():
    f = fx.build("spine")
    rec = f.evidence[0]
    out = complete_caption(rec, page_text=None)
    assert out == rec.metadata["caption"]


def test_relevance_line_is_subspecialty_neutral():
    line = relevance_line("Confirm vertebral artery course", "Benzel Spine, p.592")
    assert "Benzel Spine, p.592" in line
    # neutral: no fabricated clinical claims, just links figure to the claim + source
    assert "vertebral artery" in line.lower()
