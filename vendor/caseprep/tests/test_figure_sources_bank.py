from __future__ import annotations
import sqlite3
from pathlib import Path
from caseprep.image_bank.figure_sources import image_bank_records, normalize_tags


def test_normalize_tags_handles_json_and_csv():
    assert normalize_tags('["MCA Occlusion", "ASPECTS"]', "thalamus, MCA Occlusion") == \
        ["mca occlusion", "aspects", "thalamus"]


def _bank(tmp: Path) -> Path:
    db = tmp / "bank.db"
    c = sqlite3.connect(db)
    c.executescript(
        "CREATE TABLE images (fig_id TEXT, cluster TEXT, pmcid TEXT, pmid TEXT, "
        "caption TEXT, local_path TEXT);"
        "CREATE TABLE labels (fig_id TEXT, is_neurosurgical INTEGER, anatomy TEXT, "
        "pathology TEXT, procedure TEXT, keywords TEXT, caption_summary TEXT);"
    )
    img = tmp / "a.jpg"; img.write_bytes(b"x")
    c.execute("INSERT INTO images VALUES ('f1','stroke','PMC1','9','cap',?)", (str(img),))
    c.execute("INSERT INTO labels VALUES ('f1',1,'[\"MCA\"]','[\"occlusion\"]',"
              "'thrombectomy','[\"ASPECTS\"]','short cap')")
    c.execute("INSERT INTO images VALUES ('f2','stroke','PMC2','8','cap','/nope.jpg')")
    c.execute("INSERT INTO labels VALUES ('f2',1,'[]','[]','','[]','x')")
    c.commit(); c.close()
    return db


def test_image_bank_records(tmp_path: Path):
    db = _bank(tmp_path)
    stub = lambda texts: [[1.0, 0.0] for _ in texts]
    recs = list(image_bank_records(sqlite3.connect(db), embed_fn=stub))
    assert len(recs) == 1  # f2 excluded (missing file)
    r = recs[0]
    assert r.source == "image_bank" and r.fig_id == "f1"
    assert "aspects" in r.tags and "mca" in r.tags and "thrombectomy" in r.tags
    assert r.source_ref == {"pmcid": "PMC1", "pmid": "9"}
    assert r.image_path.endswith("a.jpg") and r.image_blob is None
    assert r.embedding == [1.0, 0.0]
