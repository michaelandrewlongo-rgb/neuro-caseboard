from __future__ import annotations
from caseprep.image_bank.figure_store import FigureRecord
from caseprep.figure_rank import best_figure


def _rec(key, emb, tags=("aspects",)):
    s, i = key.split(":", 1)
    return FigureRecord(s, i, list(tags), "cap", "/x.jpg", None, {"pmcid": "P"}, list(emb))


def test_best_figure_picks_highest_cosine():
    cands = [_rec("image_bank:1", [1.0, 0.0]), _rec("textbook:2", [0.0, 1.0])]
    stub = lambda texts: [[0.1, 0.99]]
    r = best_figure("aspects in this case", cands, embed_fn=stub, floor=0.2)
    assert r is not None and r.fig_id == "2"


def test_best_figure_floor_returns_none():
    cands = [_rec("image_bank:1", [1.0, 0.0])]
    stub = lambda texts: [[0.0, 1.0]]
    assert best_figure("x", cands, embed_fn=stub, floor=0.2) is None


def test_fallback_when_no_embed_fn():
    cands = [_rec("image_bank:1", [1.0, 0.0], tags=["aspects"]),
             _rec("textbook:2", [0.0, 1.0], tags=["aspects", "collaterals"])]
    r = best_figure("good collaterals here", cands, embed_fn=None, floor=0.2)
    assert r is not None and r.fig_id == "2"
