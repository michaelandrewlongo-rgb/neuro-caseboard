from caseprep.case_parser import (
    CaseField,
    deterministic_parse_case,
    parse_case_input,
    select_procedure_family,
)


def assert_field_contains(field: CaseField, *needles: str) -> None:
    assert field.value is not None
    normalized = field.value.casefold()
    assert any(needle.casefold() in normalized for needle in needles)
    assert field.confidence > 0
    assert field.source != "missing"


def assert_missing(field: CaseField) -> None:
    assert field.value is None
    assert field.confidence == 0.0
    assert field.source == "missing"


def test_acdf_full_case_extracts_fields_and_family():
    case = deterministic_parse_case(
        "C5-6 anterior cervical discectomy and fusion for right C6 radiculopathy "
        "from foraminal disc osteophyte complex"
    )

    assert case.raw_input.startswith("C5-6")
    assert case.procedure_family.value == "spine_acdf"
    assert case.broad_profile.value == "spine"
    assert_field_contains(case.procedure, "anterior cervical discectomy and fusion", "ACDF")
    assert_field_contains(case.approach, "anterior cervical")
    assert_field_contains(case.laterality, "right")
    assert_field_contains(case.level_or_segment, "C5-6", "C6")
    assert_field_contains(case.pathology, "radiculopathy", "disc osteophyte")
    assert not case.degraded
    assert "fusion construct" in case.missing_critical_facts
    assert select_procedure_family(case).id == "spine_acdf"


def test_convexity_meningioma_full_case_extracts_fields_and_family():
    case = parse_case_input(
        "right frontal convexity meningioma resection near the superior sagittal sinus"
    )

    assert case.procedure_family.value == "tumor_convexity_meningioma"
    assert case.broad_profile.value == "supratentorial_tumor"
    assert_field_contains(case.pathology, "convexity meningioma", "frontal meningioma")
    assert_field_contains(case.procedure, "resection", "craniotomy")
    assert_field_contains(case.laterality, "right")
    assert_field_contains(case.anatomic_location, "frontal convexity", "superior sagittal sinus")
    assert not case.degraded


def test_chiari_full_case_extracts_fields_and_family():
    case = deterministic_parse_case(
        "suboccipital craniectomy and C1 laminectomy for Chiari I malformation "
        "with syringomyelia"
    )

    assert case.procedure_family.value == "posterior_fossa_chiari"
    assert case.broad_profile.value == "posterior_fossa"
    assert_field_contains(case.procedure, "suboccipital craniectomy and C1 laminectomy", "Chiari decompression")
    assert_field_contains(case.approach, "suboccipital")
    assert_field_contains(case.level_or_segment, "C1")
    assert_field_contains(case.pathology, "Chiari I")
    assert any("syr" in modifier.value.casefold() for modifier in case.patient_modifiers if modifier.value)
    assert not case.degraded


def test_thrombectomy_full_case_extracts_fields_and_family():
    case = deterministic_parse_case(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 "
        "middle cerebral artery occlusion"
    )

    assert case.procedure_family.value == "endovascular_thrombectomy"
    assert case.broad_profile.value == "vascular"
    assert_field_contains(case.procedure, "mechanical thrombectomy")
    assert_field_contains(case.laterality, "right")
    assert_field_contains(case.level_or_segment, "M1", "MCA")
    assert_field_contains(case.anatomic_location, "middle cerebral artery", "MCA")
    assert_field_contains(case.pathology, "acute ischemic stroke", "M1 occlusion")
    assert not case.degraded


def test_empty_input_is_degraded_with_major_missing_fields_and_no_family():
    case = deterministic_parse_case("   \n\t  ")

    assert case.degraded
    assert case.procedure_family.value is None
    assert case.broad_profile.value is None
    assert_missing(case.pathology)
    assert_missing(case.procedure)
    assert_missing(case.approach)
    missing = " ".join(case.missing_critical_facts).casefold()
    assert "pathology" in missing
    assert "procedure" in missing
    assert "supported procedure family" in missing


def test_full_thrombectomy_still_surfaces_missing_selection_and_access_facts():
    case = deterministic_parse_case(
        "mechanical thrombectomy for acute ischemic stroke due to right M1 "
        "middle cerebral artery occlusion"
    )

    assert case.procedure_family.value == "endovascular_thrombectomy"
    assert not case.degraded
    missing = " ".join(case.missing_critical_facts).casefold()
    assert "last-known-well" in missing
    assert "nihss" in missing
    assert "imaging selection" in missing
    assert "access plan" in missing


def test_convexity_meningioma_surfaces_missing_venous_relationship():
    case = deterministic_parse_case("right frontal convexity meningioma resection")

    assert case.procedure_family.value == "tumor_convexity_meningioma"
    assert "venous/sinus relationship" in case.missing_critical_facts


def test_parasagittal_meningioma_abutting_sss_routes_to_tumor_family_without_silent_guessing():
    case = deterministic_parse_case("right parasagittal 4cm meningioma abutting SSS")

    assert case.procedure_family.value == "tumor_convexity_meningioma"
    assert case.broad_profile.value == "supratentorial_tumor"
    assert_field_contains(case.pathology, "parasagittal meningioma")
    assert_field_contains(case.procedure, "meningioma resection", "craniotomy prep")
    assert case.procedure.source == "inferred"
    assert_field_contains(case.laterality, "right")
    assert_field_contains(case.size, "4cm")
    assert_field_contains(case.anatomic_location, "parasagittal", "superior sagittal sinus")
    assert "booked procedure confirmation" in case.missing_critical_facts
    assert not case.degraded


def test_topic_only_family_match_has_lower_confidence_than_full_canonical_case():
    full = deterministic_parse_case(
        "suboccipital craniectomy and C1 laminectomy for Chiari I malformation"
    )
    topic_only = deterministic_parse_case("Chiari")

    assert full.procedure_family.value == topic_only.procedure_family.value
    assert topic_only.procedure_family.confidence < full.procedure_family.confidence
    assert topic_only.broad_profile.confidence == topic_only.procedure_family.confidence


TOPIC_ONLY_CASES = [
    "vestibular schwannoma",
    "MCA aneurysm",
    "cervical radiculopathy",
    "Chiari",
    "stroke thrombectomy",
]


def test_topic_only_cases_are_degraded_and_do_not_guess_approach_or_procedure():
    for raw in TOPIC_ONLY_CASES:
        case = deterministic_parse_case(raw)
        assert case.degraded, raw
        assert case.degradation_reason, raw
        assert case.missing_critical_facts, raw
        assert case.raw_input == raw
        assert case.approach.source == "missing", raw
        if raw != "stroke thrombectomy":
            assert_missing(case.procedure)
        else:
            assert_field_contains(case.procedure, "stroke thrombectomy", "thrombectomy")
            assert "occlusion location" in " ".join(case.missing_critical_facts).casefold()


def test_topic_only_inputs_extract_known_pathology_or_family_without_silent_guessing():
    cervical = deterministic_parse_case("cervical radiculopathy")
    assert cervical.procedure_family.value == "spine_acdf"
    assert_field_contains(cervical.pathology, "cervical radiculopathy")
    assert_missing(cervical.procedure)
    assert "procedure" in " ".join(cervical.missing_critical_facts).casefold()

    chiari = deterministic_parse_case("Chiari")
    assert chiari.procedure_family.value == "posterior_fossa_chiari"
    assert_field_contains(chiari.pathology, "Chiari")
    assert_missing(chiari.procedure)
    assert_missing(chiari.approach)

    vestibular = deterministic_parse_case("vestibular schwannoma")
    assert vestibular.procedure_family.value is None
    assert_field_contains(vestibular.pathology, "vestibular schwannoma")
    assert_missing(vestibular.procedure)
    assert_missing(vestibular.approach)

    aneurysm = deterministic_parse_case("MCA aneurysm")
    assert aneurysm.procedure_family.value is None
    assert_field_contains(aneurysm.pathology, "MCA aneurysm")
    assert_missing(aneurysm.procedure)
    assert_missing(aneurysm.approach)


def test_case_fields_can_be_serialized_to_dicts():
    case = deterministic_parse_case("stroke thrombectomy")
    data = case.to_dict()

    assert data["raw_input"] == "stroke thrombectomy"
    assert data["procedure"]["value"] == case.procedure.value
    assert isinstance(data["patient_modifiers"], list)
    assert isinstance(data["missing_critical_facts"], list)


def test_thrombectomy_prompt_extracts_structured_facts():
    prompt = (
        "left M1 MCA occlusion NIHSS 18 ASPECTS 7 LKW 10h CT perfusion mismatch "
        "planned transfemoral BGC aspiration stent-retriever thrombectomy"
    )

    case = deterministic_parse_case(prompt)
    data = case.to_dict()
    facts = data["facts"]
    missing = " ".join(case.missing_critical_facts).casefold()

    assert case.procedure_family.value == "endovascular_thrombectomy"
    assert_field_contains(case.procedure, "thrombectomy")
    assert facts["nihss"]["value"] == "18"
    assert facts["aspects"]["value"] == "7"
    assert facts["last_known_well"]["value"] == "10h"
    assert facts["perfusion_selection"]["value"] == "CT perfusion mismatch"
    assert facts["access_route"]["value"] == "transfemoral"
    assert facts["balloon_guide"]["value"] == "BGC"
    assert facts["aspiration"]["value"] == "aspiration"
    assert facts["stent_retriever"]["value"] == "stent-retriever"
    assert "nihss" not in missing
    assert "last-known-well" not in missing
    assert "imaging selection" not in missing
    assert "access plan" not in missing
    assert "procedure" not in missing


def test_last_known_well_duration_words_normalize_to_compact_units():
    case = deterministic_parse_case(
        "left M1 MCA occlusion acute ischemic stroke mechanical thrombectomy; "
        "NIHSS 18; ASPECTS 7; last known well 10 hours ago"
    )
    facts = case.to_dict()["facts"]
    assert isinstance(facts, dict)

    assert facts["last_known_well"]["value"] == "10h"
    assert facts["last_known_well"]["value"] != "10hours"

    minute_case = deterministic_parse_case(
        "left M1 MCA occlusion mechanical thrombectomy NIHSS 18 ASPECTS 7 LKW 45 minutes"
    )
    minute_facts = minute_case.to_dict()["facts"]
    assert isinstance(minute_facts, dict)
    assert minute_facts["last_known_well"]["value"] == "45min"


def test_last_known_well_clock_times_preserve_human_readable_spacing():
    evening_case = deterministic_parse_case(
        "left M1 MCA occlusion mechanical thrombectomy NIHSS 18 ASPECTS 7 LKW 8 pm"
    )
    evening_facts = evening_case.to_dict()["facts"]
    assert isinstance(evening_facts, dict)
    assert evening_facts["last_known_well"]["value"] == "8 pm"

    timestamp_case = deterministic_parse_case(
        "left M1 MCA occlusion mechanical thrombectomy NIHSS 18 ASPECTS 7 LKW 10:30 pm"
    )
    timestamp_facts = timestamp_case.to_dict()["facts"]
    assert isinstance(timestamp_facts, dict)
    assert timestamp_facts["last_known_well"]["value"] == "10:30 pm"


def test_thrombectomy_prompt_rejects_invalid_values_and_negated_presence_facts():
    prompt = (
        "left M1 MCA occlusion NIHSS 99 ASPECTS 99 LKW 123 "
        "no CT perfusion mismatch planned transfemoral no BGC no aspiration "
        "without stent-retriever thrombectomy"
    )

    case = deterministic_parse_case(prompt)
    facts = case.to_dict()["facts"]
    assert isinstance(facts, dict)

    assert case.procedure_family.value == "endovascular_thrombectomy"
    assert facts["access_route"]["value"] == "transfemoral"
    for key in (
        "nihss",
        "aspects",
        "last_known_well",
        "perfusion_selection",
        "balloon_guide",
        "aspiration",
        "stent_retriever",
    ):
        assert key not in facts

    alternate_negations = deterministic_parse_case(
        "left M1 MCA occlusion NIHSS 18 ASPECTS 7 LKW 10h "
        "without perfusion mismatch planned transfemoral without balloon guide "
        "without aspiration no stent retriever thrombectomy"
    ).to_dict()["facts"]
    assert isinstance(alternate_negations, dict)
    assert alternate_negations["nihss"]["value"] == "18"
    assert alternate_negations["aspects"]["value"] == "7"
    assert alternate_negations["last_known_well"]["value"] == "10h"
    assert alternate_negations["access_route"]["value"] == "transfemoral"
    for key in ("perfusion_selection", "balloon_guide", "aspiration", "stent_retriever"):
        assert key not in alternate_negations


def test_thrombectomy_rejected_facts_remain_missing_when_no_valid_alternative():
    prompt = (
        "left M1 MCA occlusion NIHSS 99 ASPECTS 99 LKW 123 "
        "no CT perfusion mismatch BGC not used aspiration not planned "
        "not using stent retriever thrombectomy"
    )

    case = deterministic_parse_case(prompt)
    facts = case.to_dict()["facts"]
    missing = " ".join(case.missing_critical_facts).casefold()
    assert isinstance(facts, dict)

    assert case.procedure_family.value == "endovascular_thrombectomy"
    assert "nihss" not in facts
    assert "aspects" not in facts
    assert "last_known_well" not in facts
    assert "perfusion_selection" not in facts
    assert "balloon_guide" not in facts
    assert "aspiration" not in facts
    assert "stent_retriever" not in facts
    assert "nihss" in missing
    assert "last-known-well time" in missing
    assert "imaging selection" in missing
    assert "access plan" in missing


def test_thrombectomy_decimal_and_range_scores_are_not_exact_known_facts():
    for prompt in (
        "left M1 MCA occlusion NIHSS 4.5 ASPECTS 7.5 LKW 10h thrombectomy",
        "left M1 MCA occlusion NIHSS 4-5 ASPECTS 7-8 LKW 10h thrombectomy",
    ):
        case = deterministic_parse_case(prompt)
        facts = case.to_dict()["facts"]
        missing = " ".join(case.missing_critical_facts).casefold()
        assert isinstance(facts, dict)

        assert "nihss" not in facts
        assert "aspects" not in facts
        assert "nihss" in missing
        assert "imaging selection" in missing


def test_thrombectomy_post_and_pre_term_negations_do_not_create_known_facts():
    case = deterministic_parse_case(
        "left M1 MCA occlusion NIHSS 18 ASPECTS 7 LKW 10h "
        "BGC not used aspiration not planned not using stent retriever "
        "not using perfusion mismatch thrombectomy"
    )
    facts = case.to_dict()["facts"]
    missing = " ".join(case.missing_critical_facts).casefold()
    assert isinstance(facts, dict)

    assert facts["nihss"]["value"] == "18"
    assert facts["aspects"]["value"] == "7"
    assert facts["last_known_well"]["value"] == "10h"
    assert "balloon_guide" not in facts
    assert "aspiration" not in facts
    assert "stent_retriever" not in facts
    assert "perfusion_selection" not in facts
    assert "access plan" in missing
