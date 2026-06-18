from __future__ import annotations
from pathlib import Path
from caseprep.image_bank.figure_store import FigureRecord, FigureStore


def _rec(key="image_bank:1", emb=(1.0, 0.0)):
    return FigureRecord(
        source="image_bank", fig_id=key.split(":", 1)[1],
        tags=["aspects", "mca occlusion"], caption="ASPECTS template",
        image_path="/imgs/a.jpg", image_blob=None,
        source_ref={"pmcid": "PMC1", "pmid": "9"}, embedding=list(emb),
    )


def test_write_then_load_roundtrip(tmp_path: Path):
    store = FigureStore(tmp_path / "fs.sqlite")
    n = store.write([_rec("image_bank:1", (0.6, 0.8)),
                     FigureRecord("textbook", "t1", ["thalamus"], "fig",
                                  "", b"\x89PNG...", {"heading_path": "Ch1>Fig2"},
                                  [0.0, 1.0])])
    assert n == 2
    recs = {FigureStore.key(r): r for r in FigureStore(tmp_path / "fs.sqlite").load()}
    assert set(recs) == {"image_bank:1", "textbook:t1"}
    a = recs["image_bank:1"]
    assert a.tags == ["aspects", "mca occlusion"]
    assert a.source_ref["pmcid"] == "PMC1"
    assert abs(a.embedding[0] - 0.6) < 1e-6 and abs(a.embedding[1] - 0.8) < 1e-6
    t = recs["textbook:t1"]
    assert t.image_blob == b"\x89PNG..." and t.image_path == ""


def test_key_format():
    assert FigureStore.key(_rec("image_bank:42")) == "image_bank:42"
