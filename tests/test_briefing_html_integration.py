from __future__ import annotations
from caseprep.image_bank.figure_store import FigureRecord, FigureStore
from caseprep.renderers.briefing_html import render_briefing_html


def test_end_to_end_store_to_hovercard(tmp_path):
    img = tmp_path / "aspects.jpg"; img.write_bytes(b"IMGDATA")
    store_path = tmp_path / "figure_store.sqlite"
    FigureStore(store_path).write([
        FigureRecord("image_bank", "1", ["aspects"], "ASPECTS 10-point template",
                     str(img), None, {"pmcid": "PMC42", "pmid": "1"}, [1.0, 0.0]),
    ])
    records = FigureStore(store_path).load()
    md = "# Imaging Review\n\nReport the ASPECTS score before EVT.\n"
    html = render_briefing_html(md, records, embed_fn=lambda t: [[1.0, 0.0]], floor=0.2)
    assert "fig-card" in html and "ASPECTS 10-point template" in html and "PMC42" in html
