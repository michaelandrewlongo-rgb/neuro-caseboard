"""Tests for surgical usefulness scoring heuristics."""

from __future__ import annotations

from caseprep.case_parser import parse_case_input, select_procedure_family
from caseprep.core import EvidenceRecord
from caseprep.scoring import (
    classify_clinical_applicability,
    neurosurg_relevance_score,
    surgical_usefulness_score,
)


def _acdf_case():
    case = parse_case_input(
        "C5-6 anterior cervical discectomy and fusion for right C6 "
        "radiculopathy from foraminal disc osteophyte complex"
    )
    return case, select_procedure_family(case)


def test_exact_procedure_title_outranks_generic_disease_title():
    case, family = _acdf_case()
    exact = EvidenceRecord(
        id="exact",
        source="pubmed",
        title="Anterior cervical discectomy and fusion: operative technique and outcomes",
        text="Technical note describing decompression, cage placement, plate fixation, and fusion.",
    )
    generic = EvidenceRecord(
        id="generic",
        source="pubmed",
        title="Cervical radiculopathy outcomes: a review",
        text="Background and nonoperative management options for cervical radiculopathy.",
    )

    exact_score, exact_reasons = surgical_usefulness_score(
        exact,
        case,
        family,
        "Surgical Technique",
    )
    generic_score, generic_reasons = surgical_usefulness_score(
        generic,
        case,
        family,
        "Surgical Technique",
    )

    assert exact_score > generic_score
    assert any("exact procedure" in reason for reason in exact_reasons)
    assert any("pathology" in reason for reason in generic_reasons)


def test_off_domain_drug_basic_science_content_gets_penalty():
    case, family = _acdf_case()
    record = EvidenceRecord(
        id="drug",
        source="pubmed",
        title="Drug pharmacokinetic changes in breast cancer cell cultures",
        text="Basic-science assay of placebo-controlled medication exposure in vitro.",
    )

    score, reasons = surgical_usefulness_score(record, case, family, "Outcomes / Evidence")

    assert score < 0
    assert any("off-domain" in reason for reason in reasons)
    assert any("non-neurosurgical" in reason for reason in reasons)


def test_complications_axis_recognizes_complication_terms():
    case, family = _acdf_case()
    record = EvidenceRecord(
        id="complications",
        source="pubmed",
        title="ACDF complications: dysphagia and recurrent laryngeal nerve injury",
        text="Operative series reporting postoperative dysphagia, hoarseness, and pseudarthrosis rescue strategies.",
    )

    score, reasons = surgical_usefulness_score(record, case, family, "Complications")

    assert score >= 60
    assert any("complication/outcome" in reason for reason in reasons)
    assert any("exact procedure" in reason for reason in reasons)


def test_uterine_fibroid_embolization_is_penalized_for_thrombectomy_case():
    case = parse_case_input("mechanical thrombectomy for acute ischemic stroke M1 occlusion")
    family = select_procedure_family(case)
    off_domain = EvidenceRecord(
        id="fibroid",
        source="pubmed",
        title="Uterine fibroid embolization outcomes",
        text="A gynecologic cohort reporting safety and complications after embolization.",
    )
    on_domain = EvidenceRecord(
        id="thrombectomy",
        source="pubmed",
        title="Mechanical thrombectomy outcomes for acute ischemic stroke",
        text="Endovascular stroke thrombectomy series reporting reperfusion and complications.",
    )

    off_score, off_reasons = surgical_usefulness_score(
        off_domain,
        case,
        family,
        "Outcomes / Evidence",
    )
    on_score, _ = surgical_usefulness_score(on_domain, case, family, "Outcomes / Evidence")

    assert off_score < on_score
    assert off_score < 20
    assert any("non-neurosurgical" in reason for reason in off_reasons)
    assert any("off-domain" in reason for reason in off_reasons)


def test_classify_clinical_applicability_quarantines_known_low_applicability_sources():
    case = parse_case_input("mechanical thrombectomy for acute ischemic stroke due to right M1 MCA occlusion")
    family = select_procedure_family(case)

    examples = [
        (
            EvidenceRecord(
                id="m2",
                source="pubmed",
                title="M2-only thrombectomy outcomes after distal MCA occlusion",
                text="distal M2-only cohort",
            ),
            "M2-only",
        ),
        (
            EvidenceRecord(
                id="isolated-m2",
                source="pubmed",
                title="Endovascular thrombectomy for isolated M2 segment occlusion",
                text="isolated M2 occlusions treated with thrombectomy",
            ),
            "M2-only",
        ),
        (
            EvidenceRecord(
                id="m2-occlusions",
                source="pubmed",
                title="Thrombectomy for M2 occlusions: multicenter outcomes",
                text="distal MCA M2 segment cohort without M1 patients",
            ),
            "M2-only",
        ),
        (
            EvidenceRecord(
                id="ai",
                source="pubmed",
                title="Artificial intelligence workflow triage for thrombectomy",
                text="AI workflow and detection software only",
            ),
            "AI/workflow",
        ),
        (
            EvidenceRecord(
                id="basilar",
                source="pubmed",
                title="Basilar artery thrombectomy for posterior circulation stroke",
                text="vertebrobasilar posterior circulation occlusion",
            ),
            "posterior-circulation-only",
        ),
        (
            EvidenceRecord(
                id="case-report",
                source="pubmed",
                title="Rare aortic arch anomaly during thrombectomy: case report",
                text="single case report vignette",
            ),
            "case report",
        ),
        (
            EvidenceRecord(
                id="ufe",
                source="pubmed",
                title="Uterine fibroid embolization outcomes",
                text="gynecologic embolization for fibroids",
            ),
            "non-stroke/non-neuro",
        ),
    ]

    for record, expected_reason in examples:
        include, reason = classify_clinical_applicability(record, case, family)
        assert include is False
        assert expected_reason in reason

    include, reason = classify_clinical_applicability(
        EvidenceRecord(
            id="m1-rct",
            source="pubmed",
            title="Randomized trial of thrombectomy for anterior circulation large vessel occlusion",
            text="M1 MCA acute ischemic stroke thrombectomy outcomes",
        ),
        case,
        family,
    )
    assert include is True
    assert reason == "clinically applicable"

    include, reason = classify_clinical_applicability(
        EvidenceRecord(
            id="valid-history",
            source="pubmed",
            title="Thrombectomy outcomes in patients with a history of atrial fibrillation",
            text="Patients with a history of atrial fibrillation were included in this acute ischemic stroke thrombectomy cohort.",
        ),
        case,
        family,
    )
    assert include is True
    assert reason == "clinically applicable"


def test_classify_clinical_applicability_allows_m2_sources_for_m2_case():
    case = parse_case_input("mechanical thrombectomy for acute ischemic stroke due to left M2 MCA occlusion")
    family = select_procedure_family(case)
    record = EvidenceRecord(
        id="m2-valid",
        source="pubmed",
        title="Endovascular thrombectomy for isolated M2 segment occlusion",
        text="isolated M2 occlusions treated with thrombectomy",
    )

    include, reason = classify_clinical_applicability(record, case, family)

    assert include is True
    assert reason == "clinically applicable"


def test_classify_clinical_applicability_quarantines_anterior_m1_sources_for_basilar_case():
    case = parse_case_input("mechanical thrombectomy for basilar artery occlusion acute ischemic stroke")
    family = select_procedure_family(case)

    anterior_record = EvidenceRecord(
        id="anterior-m1-only",
        source="pubmed",
        title="Randomized trial of thrombectomy for anterior circulation M1 MCA occlusion",
        text="M1 middle cerebral artery acute ischemic stroke endovascular therapy evidence.",
    )
    posterior_record = EvidenceRecord(
        id="posterior-valid",
        source="pubmed",
        title="Endovascular thrombectomy for basilar artery occlusion",
        text="Posterior circulation stroke thrombectomy outcomes for vertebrobasilar occlusion.",
    )

    include, reason = classify_clinical_applicability(anterior_record, case, family)
    assert include is False
    assert "anterior-circulation-only" in reason

    include, reason = classify_clinical_applicability(posterior_record, case, family)
    assert include is True
    assert reason == "clinically applicable"


def test_classify_clinical_applicability_acdf_quarantines_off_target_evidence():
    """ACDF cases should quarantine rare-variant and off-target evidence."""
    case = parse_case_input("C6-7 ACDF surgical technique")
    family = select_procedure_family(case)

    off_target_examples = [
        (
            EvidenceRecord(
                id="va-loop",
                source="corpus",
                title="Vertebral artery loop causing cervical radiculopathy",
                text="Case report of a rare vertebral artery loop causing radiculopathy treated with microvascular decompression.",
            ),
            "vertebral artery loop",
        ),
        (
            EvidenceRecord(
                id="va-sling",
                source="corpus",
                title="A New Sling Technique in Cervical Radiculopathy Caused by Vertebral Artery Loop Compression",
                text="Case report: sling technique for vertebral artery loop compression at C6-7.",
            ),
            "vertebral artery loop",
        ),
        (
            EvidenceRecord(
                id="dsa-hemodialysis",
                source="corpus",
                title="Surgical treatment of cervical destructive spondyloarthropathy (DSA)",
                text="Sixteen patients with hemodialysis-associated cervical spine disorders underwent surgical treatment.",
            ),
            "hemodialysis-associated",
        ),
        (
            EvidenceRecord(
                id="bow-hunter",
                source="pubmed",
                title="Bow hunter syndrome case report: rotational vertebral artery occlusion after ACDF",
                text="Single case report of bow hunter syndrome after adjacent level ACDF.",
            ),
            "rotational",
        ),
        (
            EvidenceRecord(
                id="basic-science",
                source="pubmed",
                title="Molecular pathways in cervical disc degeneration",
                text="Cell culture study of protein expression in murine disc tissue.",
            ),
            "basic-science",
        ),
    ]

    for record, expected_reason in off_target_examples:
        include, reason = classify_clinical_applicability(record, case, family)
        assert include is False, (
            f"expected {record.id} to be quarantined, got include={include}, reason={reason}"
        )
        assert expected_reason in reason, (
            f"expected '{expected_reason}' in quarantine reason for {record.id}, got: {reason}"
        )


def test_classify_clinical_applicability_acdf_allows_on_target_evidence():
    """ACDF cases should allow technique/outcome/comparison evidence."""
    case = parse_case_input("C6-7 ACDF surgical technique")
    family = select_procedure_family(case)

    on_target_examples = [
        EvidenceRecord(
            id="acdf-technique",
            source="pubmed",
            title="Anterior cervical discectomy and fusion: surgical technique and outcomes",
            text="Operative technique for ACDF including exposure, decompression, graft placement, and plating.",
        ),
        EvidenceRecord(
            id="acdf-dysphagia",
            source="pubmed",
            title="Dysphagia after ACDF: incidence and risk factors",
            text="Retrospective cohort of 500 patients reporting postoperative dysphagia after anterior cervical fusion.",
        ),
        EvidenceRecord(
            id="acdf-vs-cda",
            source="pubmed",
            title="ACDF versus cervical disc arthroplasty for single-level radiculopathy: a randomized trial",
            text="Patients with cervical radiculopathy were randomized to ACDF or CDA and followed for 5 years.",
        ),
        EvidenceRecord(
            id="acdf-pseudarthrosis",
            source="pubmed",
            title="Pseudarthrosis after ACDF: risk factors and revision strategies",
            text="Multicenter study of pseudarthrosis rates after one- and two-level ACDF.",
        ),
        EvidenceRecord(
            id="acdf-systematic-review",
            source="pubmed",
            title="ACDF for cervical radiculopathy: a systematic review and meta-analysis",
            text="Systematic review of outcomes after anterior cervical discectomy and fusion for cervical radiculopathy.",
        ),
    ]

    for record in on_target_examples:
        include, reason = classify_clinical_applicability(record, case, family)
        assert include is True, (
            f"expected {record.id} to be clinically applicable, got include={include}, reason={reason}"
        )
        assert reason == "clinically applicable"


def test_classify_clinical_applicability_acdf_orthopedic_bypass():
    """ACDF papers mentioning 'orthopedic' should not be falsely quarantined."""
    case = parse_case_input("C5-6 anterior cervical discectomy and fusion for right C6 radiculopathy from foraminal disc osteophyte complex")
    family = select_procedure_family(case)

    record = EvidenceRecord(
        id="acdf-orthopedic",
        source="pubmed",
        title="Orthopedic outcomes after ACDF: a prospective study",
        text="Anterior cervical discectomy and fusion outcomes in a prospective orthopedic cohort.",
    )

    include, reason = classify_clinical_applicability(record, case, family)
    assert include is True, (
        f"ACDF paper with 'orthopedic' should not be quarantined, got include={include}, reason={reason}"
    )


def test_breast_tumor_resection_review_is_penalized_for_convexity_meningioma():
    case = parse_case_input(
        "right frontal convexity meningioma resection near the superior sagittal sinus"
    )
    family = select_procedure_family(case)
    record = EvidenceRecord(
        id="breast",
        source="pubmed",
        title="Breast tumor resection complications review",
        text="Review of non-neurosurgical breast oncology resection outcomes and morbidity.",
    )

    score, reasons = surgical_usefulness_score(record, case, family, "Complications")

    assert score <= 0
    assert any("non-neurosurgical" in reason for reason in reasons)
    assert any("off-domain" in reason for reason in reasons)


def test_neurosurg_relevance_penalizes_off_domain_procedural_papers():
    breast_score = neurosurg_relevance_score(
        "Breast tumor resection complications review",
        "Review of breast oncology resection outcomes and morbidity.",
    )
    fibroid_score = neurosurg_relevance_score(
        "Uterine fibroid embolization outcomes",
        "A gynecologic cohort reporting safety and complications after embolization.",
    )
    neuro_score = neurosurg_relevance_score(
        "Meningioma resection complications after frontal craniotomy",
        "Intracranial brain tumor operative outcomes and morbidity review.",
    )

    assert breast_score <= 0
    assert fibroid_score <= 0
    assert neuro_score > breast_score
    assert neuro_score > fibroid_score
