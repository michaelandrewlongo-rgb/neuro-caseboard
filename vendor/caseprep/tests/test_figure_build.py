from __future__ import annotations
import sqlite3
from pathlib import Path
from caseprep.image_bank.figure_build import build_figure_store
from caseprep.image_bank.figure_store import FigureStore


def _bank(tmp: Path) -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.executescript(
        "CREATE TABLE images (fig_id TEXT, cluster TEXT, pmcid TEXT, pmid TEXT, caption TEXT, local_path TEXT);"
        "CREATE TABLE labels (fig_id TEXT, is_neurosurgical INTEGER, anatomy TEXT, pathology TEXT, procedure TEXT, keywords TEXT, caption_summary TEXT);"
    )
    img = tmp / "a.jpg"; img.write_bytes(b"x")
    c.execute("INSERT INTO images VALUES ('f1','s','PMC1','9','c',?)", (str(img),))
    c.execute("INSERT INTO labels VALUES ('f1',1,'[]','[]','','[\"aspects\"]','cap')")
    c.commit(); return c


def test_build_merges_both_sources(tmp_path: Path):
    out = tmp_path / "figure_store.sqlite"
    textbook = [dict(id=7, caption_vlm="fig", heading_path="H", vlm_keywords='["thalamus"]',
                     vlm_anatomy="", vlm_pathology="", vlm_procedure="",
                     embedding=[0.0, 1.0], image_data=b"PNG")]
    n = build_figure_store(
        out, bank_conn=_bank(tmp_path),
        embed_fn=lambda texts: [[1.0, 0.0] for _ in texts],
        textbook_rows=textbook,
    )
    assert n == 2
    keys = {FigureStore.key(r) for r in FigureStore(out).load()}
    assert keys == {"image_bank:f1", "textbook:7"}
