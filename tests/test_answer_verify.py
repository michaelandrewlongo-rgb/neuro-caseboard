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


def test_uncited_clinical_sentence_with_named_pathology_is_flagged():
    # A2: an uncited sentence asserting a named pathology/operation is an uncited clinical claim and
    # must be flagged (no silent uncited clinical claims), not auto-supported.
    v = verify_answer(
        "The glioma was resected via a craniotomy. The dural repair was watertight [1].",
        {"1": "A watertight dural repair was achieved at closure."})
    flagged = v.uncited_clinical_claims()
    assert any("glioma" in s.lower() for s in flagged)


def test_uncited_connective_prose_is_not_flagged():
    # Plain non-clinical connective tissue (no named entity, no measurement) is fine uncited.
    v = verify_answer(
        "In summary, these structures are closely related. The MCA supplies the cortex [1].",
        {"1": "The middle cerebral artery supplies the lateral cerebral cortex."})
    assert v.uncited_clinical_claims() == []


def test_uncited_measurement_sentence_is_flagged():
    v = verify_answer(
        "The maintenance dose is 0.5 g/kg. Further detail is in the cited passage [1].",
        {"1": "Osmotic therapy detail is provided in the referenced textbook passage here."})
    assert v.uncited_clinical_claims()


def test_uncited_clinical_in_dict_and_notice():
    from neuro_caseboard.answer_verify import verification_to_dict, verification_notice
    v = verify_answer(
        "A meningioma recurred postoperatively. The dural repair held [1].",
        {"1": "The dural repair was watertight and intact on follow-up imaging."})
    d = verification_to_dict(v)
    assert d["n_uncited_clinical"] == 1
    assert "no citation" in verification_notice(v).lower()


def test_numeric_not_in_premise_is_flagged():
    # A3: a dose asserted in a cited claim but absent from the cited premise is a possible
    # model-originated numeric. Lexical overlap alone passes (mannitol/ICP words match), so the
    # numeric backstop is what catches the wrong dose.
    v = verify_answer(
        "Give mannitol 0.5 g/kg for raised intracranial pressure [1].",
        {"1": "Mannitol is an osmotic diuretic used to lower intracranial pressure; the usual "
              "dose is 0.25 g/kg."})
    assert v.n_unsupported == 1
    assert "0.5" in v.numeric_flags()
    assert "1" in v.unsupported_markers()


def test_numeric_present_in_premise_passes():
    v = verify_answer(
        "Give mannitol 0.25 g/kg for raised intracranial pressure [1].",
        {"1": "Mannitol is an osmotic diuretic used to lower intracranial pressure; the usual "
              "dose is 0.25 g/kg."})
    assert v.n_unsupported == 0
    assert v.numeric_flags() == []


def test_non_measurement_integers_not_flagged():
    # Anatomical levels / figure refs / counts are NOT measurement numbers -> must not false-flag
    # (high precision: only unit-adjacent numbers and decimals are checked).
    v = verify_answer(
        "A C5-6 anterior cervical discectomy addresses the disc at that level [1].",
        {"1": "Anterior cervical discectomy removes a herniated cervical disc to decompress the "
              "spinal cord and the exiting nerve roots."})
    assert v.n_unsupported == 0
    assert v.numeric_flags() == []


def test_percentage_not_in_premise_is_flagged():
    # Integer percentages are a safety-critical threshold class (A3): a wrong stenosis threshold
    # must flag. (Regression guard: a trailing \b after the non-word '%' previously never matched,
    # so integer percentages silently passed.)
    v = verify_answer(
        "Carotid endarterectomy is indicated for 50% symptomatic stenosis [1].",
        {"1": "Carotid endarterectomy is indicated for symptomatic carotid stenosis of 70% or "
              "greater on imaging."})
    assert "50" in v.numeric_flags()
    assert v.n_unsupported == 1


def test_percentage_present_in_premise_passes():
    v = verify_answer(
        "Carotid endarterectomy is indicated for 70% symptomatic stenosis [1].",
        {"1": "Carotid endarterectomy is indicated for symptomatic carotid stenosis of 70% or "
              "greater on imaging."})
    assert v.numeric_flags() == []


def test_duration_numbers_not_flagged_for_precision():
    # Follow-up durations are paraphrase-prone and not safety-critical dosing; excluded from the
    # measurement set to keep the backstop high-precision (avoid cry-wolf).
    v = verify_answer(
        "Follow-up imaging at 6 months showed no tumor recurrence [1].",
        {"1": "Surveillance magnetic resonance imaging showed no tumor recurrence at clinical "
              "follow-up after the operation."})
    assert v.numeric_flags() == []


def test_numeric_flag_in_dict_and_notice():
    from neuro_caseboard.answer_verify import verification_to_dict, verification_notice
    v = verify_answer(
        "The recommended CPP treatment threshold is 70 mmHg [1].",
        {"1": "Cerebral perfusion pressure should generally be maintained above 60 mmHg in this "
              "clinical setting per the cited guidance passage."})
    assert "70" in v.numeric_flags()
    d = verification_to_dict(v)
    assert d["numeric_flags"] == ["70"]
    assert "70" in verification_notice(v)


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
