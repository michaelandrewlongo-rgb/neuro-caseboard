from neuro_caseboard.answer_verify import segment_claims, verify_answer


def test_segment_associates_markers_per_sentence():
    ans = "The MCA supplies the lateral cortex [1]. Bridging therapy is debated [L2][3]. No citation here."
    spans = segment_claims(ans)
    assert [s.markers for s in spans] == [["1"], ["L2", "3"], []]
    assert spans[0].text.startswith("The MCA")


def test_segment_handles_empty():
    assert segment_claims("") == []


def test_supported_claim_passes():
    v = verify_answer("The middle cerebral artery supplies the lateral cerebral cortex [1].",
                      {"1": "The middle cerebral artery supplies the lateral cerebral cortex and the insula."})
    assert v.n_cited_claims == 1 and v.n_unsupported == 0 and v.groundedness() == 1.0


def test_unsupported_claim_flagged():
    v = verify_answer("Endovascular thrombectomy improves functional outcomes in distal vessel occlusion [1].",
                      {"1": "The corpus callosum is a broad band of commissural white-matter fibers connecting the left and right cerebral hemispheres."})
    assert v.n_unsupported == 1 and v.groundedness() == 0.0 and "1" in v.unsupported_markers()


def test_uncited_excluded_from_denominator():
    v = verify_answer("Background prose with no marker. The MCA supplies the lateral cortex [1].",
                      {"1": "The MCA supplies the lateral cerebral cortex."})
    assert v.n_cited_claims == 1


def test_missing_premise_is_non_destructive():
    v = verify_answer("A figure-only reference [3].", {})
    assert v.n_unsupported == 0
