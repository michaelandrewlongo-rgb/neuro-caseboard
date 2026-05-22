from caseprep.case_parser import deterministic_parse_case, select_procedure_family
from caseprep.renderers.markdown import render_caseprep_files
from caseprep.schema import _case_facts, build_caseprep_schema


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


def _render_fact_rich_thrombectomy_case() -> dict[str, str]:
    return _render_thrombectomy_case(
        "left M1 MCA occlusion NIHSS 18 ASPECTS 7 LKW 10h CT perfusion mismatch "
        "planned transfemoral BGC aspiration stent-retriever thrombectomy"
    )


def _render_sparse_thrombectomy_case() -> dict[str, str]:
    return _render_thrombectomy_case("stroke thrombectomy")


def test_build_schema_preserves_structured_case_facts():
    case = deterministic_parse_case(
        "left M1 MCA occlusion NIHSS 18 ASPECTS 7 LKW 10h CT perfusion mismatch "
        "planned transfemoral BGC aspiration stent-retriever thrombectomy"
    )

    schema = build_caseprep_schema(
        case.raw_input,
        profile="vascular",
        structured_case=case.to_dict(),
    )

    facts = schema["case"]["facts"]
    assert facts["nihss"]["value"] == "18"
    assert facts["aspects"]["value"] == "7"
    assert facts["last_known_well"]["value"] == "10h"
    assert _case_facts(schema) is facts


def test_thrombectomy_morning_page_renders_supplied_facts_as_known():
    rendered = _render_fact_rich_thrombectomy_case()
    morning = rendered["00-morning-of-case.md"]

    assert "NIHSS: 18" in morning
    assert "ASPECTS: 7" in morning
    assert "Last known well: 10h" in morning
    assert "CT perfusion mismatch" in morning
    assert "transfemoral" in morning
    assert "LKW/time window | incomplete/needs input" not in morning
    assert "NIHSS/disabling deficit | incomplete/needs input" not in morning
    assert "ASPECTS/core | incomplete/needs input" not in morning


def test_fact_rich_thrombectomy_rendering_has_no_stale_incomplete_contradictions():
    rendered = _render_fact_rich_thrombectomy_case()
    combined = "\n".join(
        rendered[name]
        for name in (
            "00-morning-of-case.md",
            "01-case-summary.md",
            "02-imaging-review.md",
            "04-operative-plan.md",
            "09-open-questions.md",
        )
    )

    for stale in (
        "Last-known-well/time window: incomplete/needs input",
        "NIHSS/disabling deficit: incomplete/needs input",
        "Imaging selection: incomplete/needs input",
        "ASPECTS numeric score and involved regions: incomplete/needs input",
        "Core volume (mL), penumbra/hypoperfusion volume (mL), mismatch ratio, and Tmax/CBF thresholds if CTP used: incomplete/needs input",
    ):
        assert stale not in combined

    for known in (
        "NIHSS: 18",
        "ASPECTS: 7",
        "Last known well: 10h",
        "CT perfusion mismatch",
        "Confirm current NIHSS/exam",
        "Confirm ASPECTS 7",
    ):
        assert known in combined


def test_thrombectomy_imaging_and_operative_plan_use_supplied_facts():
    rendered = _render_fact_rich_thrombectomy_case()
    imaging = rendered["02-imaging-review.md"]
    operative = rendered["04-operative-plan.md"]

    assert "ASPECTS: 7" in imaging
    assert "CT perfusion mismatch" in imaging
    assert "ASPECTS: incomplete/needs input" not in imaging
    assert "transfemoral" in operative
    assert "balloon guide" in operative.casefold()
    assert "aspiration" in operative.casefold()
    assert "stent retriever" in operative.casefold()


def test_open_questions_do_not_ask_for_supplied_thrombectomy_facts():
    rendered = _render_fact_rich_thrombectomy_case()
    open_questions = rendered["09-open-questions.md"]

    assert "What is the NIHSS" not in open_questions
    assert "NIHSS?" not in open_questions
    assert "What is the ASPECTS" not in open_questions
    assert "ASPECTS?" not in open_questions
    assert "What is the last-known-well" not in open_questions
    assert "Confirm current NIHSS/exam" in open_questions
    assert "Confirm ASPECTS 7" in open_questions
    assert any(term in open_questions for term in ("thrombolytic", "TNK", "tPA"))


def test_sparse_thrombectomy_rendering_uses_neutral_fact_headings():
    rendered = _render_sparse_thrombectomy_case()
    combined = "\n".join(
        rendered[name]
        for name in (
            "00-morning-of-case.md",
            "02-imaging-review.md",
            "04-operative-plan.md",
            "09-open-questions.md",
        )
    )

    assert "## Patient-Specific Known Facts" not in combined
    assert "### Supplied Imaging Facts" not in combined
    assert "## Patient-Specific Fact Status" in combined
    assert "### Imaging Fact Status" in combined
    assert "Last known well: missing/needs input" in combined
    assert "ASPECTS numeric score and involved regions: incomplete/needs input" in combined
