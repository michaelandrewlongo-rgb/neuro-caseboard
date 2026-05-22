from caseprep.case_parser import deterministic_parse_case
from caseprep.schema import _case_facts, build_caseprep_schema


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
