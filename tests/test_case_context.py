"""CaseContext: the structured intake object + its bridge helpers.

Pure dataclass logic — no network, no LLM. Proves to_topic() keeps the existing pipeline
runnable off a case, that field coercion tolerates messy LLM JSON, and that missing_critical()
stays conservative (<=3 fields, never interrogates for everything).
"""

from neuro_caseboard.case_context import CaseContext


def test_to_topic_composes_geometry_pathology_procedure():
    cc = CaseContext(level="C5-6", pathology="cervical spondylotic myelopathy",
                     procedure="ACDF", surgical_goal="decompression")
    topic = cc.to_topic()
    assert "C5-6" in topic and "ACDF" in topic
    # classify_profile must still recognise the case from the synthesized topic
    from neuro_caseboard.pipeline import classify_profile
    assert classify_profile(topic) == "spine"


def test_to_topic_omits_absent_laterality_for_midline_case():
    cc = CaseContext(location="fourth ventricle", pathology="medulloblastoma",
                     procedure="suboccipital craniotomy")
    topic = cc.to_topic().lower()
    assert "left" not in topic and "right" not in topic
    assert "fourth ventricle" in topic and "suboccipital" in topic


def test_to_topic_falls_back_to_presentation_then_case():
    assert CaseContext(presentation="A 54 year old with a lesion").to_topic()
    assert CaseContext().to_topic() == "case"


def test_target_prefers_level_then_location():
    assert CaseContext(level="L4-5", location="lumbar").target() == "L4-5"
    assert CaseContext(location="left frontal").target() == "left frontal"
    assert CaseContext().target() == ""


def test_from_dict_coerces_messy_llm_json():
    cc = CaseContext.from_dict({
        "age": "62", "sex": "female", "laterality": "Left",
        "comorbidities": "hypertension",          # string -> list
        "medications": ["aspirin", "apixaban"],
        "level": "c5-6", "surgical_goal": "gross total resection",
        "bogus_key": "ignored",
    })
    assert cc.age == 62 and cc.sex == "F" and cc.laterality == "left"
    assert cc.comorbidities == ["hypertension"]
    assert cc.medications == ["aspirin", "apixaban"]


def test_missing_critical_is_conservative_and_capped():
    empty = CaseContext()
    miss = empty.missing_critical()
    assert len(miss) <= 3
    # a midline lesion has no laterality -> laterality must NOT be demanded
    assert not any("lateral" in m.lower() for m in miss)
    complete = CaseContext(procedure="ACDF", level="C5-6", surgical_goal="decompression")
    assert complete.missing_critical() == []
    # pathology alone (no procedure) satisfies the "what operation" axis enough to not block
    partial = CaseContext(pathology="meningioma", location="convexity",
                          surgical_goal="resection")
    assert partial.missing_critical() == []
