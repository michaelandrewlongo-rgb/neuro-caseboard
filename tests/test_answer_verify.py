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


def test_figure_only_empty_premise_is_non_destructive():
    # A real figure-only source IS a PRESENT key with empty premise text (no body to verify
    # against) -> abstain and keep, not flagged. Contrast: an ABSENT key is a dangling marker
    # (see the dangling-marker tests below). This is the pipeline shape: build_citations appends
    # figure sources whose Citation.text == "" so premises["3"] == "".
    v = verify_answer("A figure-only reference [3].", {"3": ""})
    assert v.n_unsupported == 0
    assert v.dangling_markers() == []


def test_dangling_marker_is_flagged():
    # [9] resolves to NO key in the premises map -> an invented/dangling citation. A1: a marker
    # that points at a source that does not exist must be flagged, not abstain-kept as supported.
    v = verify_answer(
        "The middle cerebral artery supplies the lateral cerebral cortex [9].",
        {"1": "The middle cerebral artery supplies the lateral cerebral cortex and the insula."})
    assert v.n_unsupported == 1
    assert "9" in v.unsupported_markers()
    assert v.dangling_markers() == ["9"]
    assert v.groundedness() == 0.0


def test_dangling_literature_marker_is_flagged():
    v = verify_answer(
        "Bridging therapy improves recanalization in proximal occlusion [L5].",
        {"L1": "Bridging therapy improves recanalization and functional outcomes in proximal occlusion."})
    assert v.n_unsupported == 1
    assert "L5" in v.dangling_markers()


def test_dangling_marker_flagged_even_with_valid_cocitation():
    # A claim citing both a real [1] (which entails) and an invented [9] must still surface the
    # dangling [9]; the claim as a whole is not clean.
    v = verify_answer(
        "The middle cerebral artery supplies the lateral cerebral cortex [1][9].",
        {"1": "The middle cerebral artery supplies the lateral cerebral cortex and the insula."})
    assert v.dangling_markers() == ["9"]
    assert v.n_unsupported == 1


def test_verification_to_dict_includes_dangling_markers_when_present():
    from neuro_caseboard.answer_verify import verification_to_dict
    v = verify_answer("Claim with a fabricated source [7].", {"1": "Unrelated real premise text about anatomy."})
    d = verification_to_dict(v)
    assert d["dangling_markers"] == ["7"]


def test_verification_notice_names_dangling_distinctly():
    from neuro_caseboard.answer_verify import verification_notice
    v = verify_answer("Claim with a fabricated source [7].", {"1": "Unrelated real premise text about anatomy."})
    note = verification_notice(v).lower()
    assert "[7]" in note
    assert "not in the source list" in note or "does not exist" in note


def test_merge_verifications_concatenates_counts_and_markers():
    from neuro_caseboard.answer_verify import merge_verifications, AnswerVerification, ClaimVerdict
    a = AnswerVerification([ClaimVerdict("x [1].", ["1"], True, 20)], 1, 0)
    b = AnswerVerification([ClaimVerdict("y [L1].", ["L1"], False, 30)], 1, 1)
    merged = merge_verifications(a, None, b)
    assert merged.n_cited_claims == 2 and merged.n_unsupported == 1
    assert merged.groundedness() == 0.5
    assert merged.unsupported_markers() == ["L1"]
    assert len(merged.claims) == 2


def test_merge_verifications_all_none_is_empty():
    from neuro_caseboard.answer_verify import merge_verifications
    merged = merge_verifications(None, None)
    assert merged.n_cited_claims == 0 and merged.n_unsupported == 0
    assert merged.groundedness() == 1.0 and merged.claims == []


def test_verification_to_dict_shape():
    from neuro_caseboard.answer_verify import verification_to_dict, AnswerVerification, ClaimVerdict
    v = AnswerVerification([ClaimVerdict("x [1].", ["1"], False, 10)], 1, 1)
    assert verification_to_dict(v) == {"n_cited_claims": 1, "n_unsupported": 1,
                                       "groundedness": 0.0, "unsupported_markers": ["1"]}
    assert verification_to_dict(None) is None


def test_verification_notice_lists_unsupported_markers():
    from neuro_caseboard.answer_verify import verification_notice, AnswerVerification, ClaimVerdict
    v = AnswerVerification([ClaimVerdict("x [1].", ["1"], False, 5),
                            ClaimVerdict("y [2].", ["2"], True, 20)], 2, 1)
    note = verification_notice(v)
    assert "needs-verification" in note.lower()
    assert "[1]" in note and "[2]" not in note


def test_verification_notice_empty_when_supported_or_none():
    from neuro_caseboard.answer_verify import verification_notice, AnswerVerification, ClaimVerdict
    assert verification_notice(None) == ""
    assert verification_notice(AnswerVerification([ClaimVerdict("x [1].", ["1"], True, 20)], 1, 0)) == ""
