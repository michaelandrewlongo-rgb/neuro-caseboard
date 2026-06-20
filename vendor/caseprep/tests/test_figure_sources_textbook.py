from __future__ import annotations
from caseprep.image_bank.figure_sources import textbook_records


def _row(**kw):
    base = dict(id=1, caption_vlm="Tandem occlusion on CTA", caption="",
               heading_path="Stroke>Imaging>Fig3", vlm_keywords='["tandem occlusion","CTA"]',
               vlm_anatomy='["ICA"]', vlm_pathology='["occlusion"]', vlm_procedure="",
               embedding=[0.0, 1.0], image_data=b"\x89PNG")
    base.update(kw); return base


def test_textbook_records_maps_fields():
    recs = list(textbook_records([_row()]))
    assert len(recs) == 1
    r = recs[0]
    assert r.source == "textbook" and r.fig_id == "1"
    assert "tandem occlusion" in r.tags and "ica" in r.tags
    assert r.caption == "Tandem occlusion on CTA"
    assert r.source_ref == {"heading_path": "Stroke>Imaging>Fig3"}
    assert r.image_blob == b"\x89PNG" and r.image_path == ""
    assert r.embedding == [0.0, 1.0]


def test_textbook_skips_rows_without_embedding_or_image():
    assert list(textbook_records([_row(embedding=None)])) == []
    assert list(textbook_records([_row(image_data=None)])) == []
