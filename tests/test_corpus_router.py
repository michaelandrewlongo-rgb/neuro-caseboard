"""Phase 2.1 domain router: scope the [D#] currency lane to the question's subspecialty so it
doesn't crowd off-topic content into the answer. Deterministic, recall-safe."""
from neuro_caseboard.corpus import route_domains, RELEVANT_DBS


def test_spine_question_routes_to_spine():
    d = route_domains("What is the fusion rate after L4-L5 lumbar interbody fusion?", RELEVANT_DBS)
    assert "spine" in d and "cerebrovascular" not in d


def test_stroke_question_routes_to_vascular_not_spine():
    d = route_domains("thrombectomy for large vessel occlusion in the late window", RELEVANT_DBS)
    assert "neurointerventional" in d and "spine" not in d


def test_trauma_question_routes_to_trauma():
    d = route_domains("decompressive craniectomy after traumatic brain injury with high ICP",
                      RELEVANT_DBS)
    assert "trauma_general" in d and "tumor_skull_base" not in d


def test_no_keyword_match_falls_back_to_all():
    # Recall-safe: an un-routable question must query everything, never nothing.
    assert route_domains("what did the authors conclude?", RELEVANT_DBS) == RELEVANT_DBS


def test_router_never_returns_empty():
    assert route_domains("", RELEVANT_DBS) == RELEVANT_DBS


def test_all_ten_domains_present():
    assert len(RELEVANT_DBS) == 10 and "functional_epilepsy" in RELEVANT_DBS
