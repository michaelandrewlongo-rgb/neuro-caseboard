from neuro_caseboard.literature.precision import gate_records, GateResult
from neuro_caseboard.literature.retriever import LiteratureRecord


def _rec(pmid, title, abstract):
    return LiteratureRecord(pmid=pmid, title=title, journal="J", year=2024, doi="",
                            url="u", abstract=abstract, sections={}, pub_types=["Review"])


def test_drops_offtopic_keeps_ontopic():
    on = _rec("1", "Middle meningeal artery embolization for subdural hematoma", "MMA outcomes")
    off = _rec("2", "Lumbar fusion hardware failure", "spine screws")
    res = gate_records([on, off], "subdural hematoma MMA embolization")
    assert isinstance(res, GateResult)
    assert [r.pmid for r in res.records] == ["1"]
    assert res.note == ""


def test_empty_input_returns_empty():
    res = gate_records([], "anything")
    assert res.records == [] and res.note == ""


def test_empty_concepts_passes_through():
    # build_query_terms drops <3-char tokens and stopwords; "of to" yields no concepts.
    a, b = _rec("1", "x", "y"), _rec("2", "p", "q")
    res = gate_records([a, b], "of to")
    assert [r.pmid for r in res.records] == ["1", "2"]
    assert res.note == ""


def test_all_offtopic_falls_back_to_top1_with_note():
    a = _rec("1", "Lumbar fusion", "spine")
    b = _rec("2", "Cervical plate", "spine")
    res = gate_records([a, b], "glioblastoma temozolomide")
    assert [r.pmid for r in res.records] == ["1"]  # single most-relevant kept
    assert "caution" in res.note.lower()


def test_min_overlap_threshold():
    # Needs >=2 shared concepts to survive at min_overlap=2.
    one = _rec("1", "subdural hemorrhage", "only one concept present")
    two = _rec("2", "subdural hematoma MMA embolization", "two-plus concepts")
    res = gate_records([one, two], "subdural hematoma MMA embolization", min_overlap=2)
    assert [r.pmid for r in res.records] == ["2"]


def test_rank_ceiling_caps_pool():
    recs = [_rec(str(i), "subdural hematoma MMA", "embolization") for i in range(5)]
    res = gate_records(recs, "subdural hematoma MMA embolization", rank_ceiling=3)
    assert [r.pmid for r in res.records] == ["0", "1", "2"]
