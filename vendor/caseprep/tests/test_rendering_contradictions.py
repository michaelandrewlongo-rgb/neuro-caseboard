from caseprep.case_parser import deterministic_parse_case, select_procedure_family
from caseprep.renderers.markdown import render_caseprep_files
from caseprep.schema import build_caseprep_schema


def _render_thrombectomy_case(case_text: str) -> dict[str, str]:
    case = deterministic_parse_case(case_text)
    family = select_procedure_family(case)
    assert family is not None
    schema = build_caseprep_schema(
        case.raw_input,
        profile="vascular",
        structured_case=case.to_dict(),
        procedure_family={
            "id": family.id,
            "display_name": family.display_name,
            "broad_profile": family.broad_profile,
            "required_fields": list(family.required_fields),
            "missing_fact_prompts": list(family.missing_fact_prompts),
        },
    )
    return render_caseprep_files(schema)


def _combined_thrombectomy(case_text: str) -> str:
    return "\n".join(_render_thrombectomy_case(case_text).values())


def test_left_m1_supplied_facts_do_not_render_right_m1_as_target():
    combined = _combined_thrombectomy(
        "left M1 MCA occlusion NIHSS 18 ASPECTS 7 LKW 10h CT perfusion mismatch "
        "planned transfemoral BGC aspiration stent-retriever thrombectomy"
    )

    assert "left M1 MCA occlusion" in combined
    assert "Left M1 MCA syndrome prep" in combined
    assert "right M1 MCA occlusion" not in combined
    assert "Right M1 MCA syndrome prep" not in combined


def test_basilar_thrombectomy_does_not_leak_mca_primary_target_or_mca_edema():
    combined = _combined_thrombectomy(
        "mechanical thrombectomy for basilar artery occlusion acute ischemic stroke"
    )

    assert "basilar artery occlusion" in combined
    assert "posterior circulation" in combined
    assert "vertebral-basilar circulation" in combined
    assert "right M1 MCA occlusion" not in combined
    assert "left M1 MCA occlusion" not in combined
    assert "ICA terminus/M1 anatomy" not in combined
    assert "malignant MCA edema" not in combined


def test_underspecified_stroke_thrombectomy_does_not_invent_target_and_requests_anatomy_input():
    combined = _combined_thrombectomy("stroke thrombectomy")

    assert "target LVO" in combined
    assert "access/occlusion anatomy needs input" in combined
    assert "right M1 MCA occlusion" not in combined
    assert "left M1 MCA occlusion" not in combined
    assert "basilar artery occlusion" not in combined
    assert "ICA terminus/M1 anatomy" not in combined
