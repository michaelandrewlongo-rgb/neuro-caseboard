from neuro_caseboard.answer_verify import segment_claims


def test_segment_associates_markers_per_sentence():
    ans = "The MCA supplies the lateral cortex [1]. Bridging therapy is debated [L2][3]. No citation here."
    spans = segment_claims(ans)
    assert [s.markers for s in spans] == [["1"], ["L2", "3"], []]
    assert spans[0].text.startswith("The MCA")


def test_segment_handles_empty():
    assert segment_claims("") == []
