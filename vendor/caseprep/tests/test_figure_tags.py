from __future__ import annotations
from caseprep.image_bank.figure_store import FigureRecord
from caseprep.figure_tags import build_vocabulary, find_marks, STOP_TAGS


def _rec(key, tags):
    s, i = key.split(":", 1)
    return FigureRecord(s, i, tags, "cap", "/x.jpg", None, {"pmcid": "P"}, [1.0, 0.0])


def test_vocabulary_filters_generic_keeps_clinical():
    recs = [_rec("image_bank:1", ["aspects", "mri", "patient", "tandem occlusion"]),
            _rec("textbook:2", ["aspects"])]
    vocab = build_vocabulary(recs)
    assert "mri" not in vocab and "patient" not in vocab
    assert "aspects" in vocab and "tandem occlusion" in vocab
    assert set(vocab["aspects"]) == {"image_bank:1", "textbook:2"}


def test_find_marks_whole_word_first_occurrence():
    recs = [_rec("image_bank:1", ["aspects"])]
    vocab = build_vocabulary(recs)
    text = "ASPECTS guides EVT. A second ASPECTS mention. Subaspects is not a hit."
    marks = find_marks(text, vocab)
    assert len(marks) == 1
    m = marks[0]
    assert text[m.start:m.end].lower() == "aspects"
    assert m.start == 0
    assert m.candidate_keys == ["image_bank:1"]


def test_stop_tags_nonempty():
    assert "patient" in STOP_TAGS and "mri" in STOP_TAGS
