"""Tests for the CasePrep v0.2 case dossier schema and renderer."""

from __future__ import annotations

import json

from caseprep.schema import (
    CANONICAL_MARKDOWN_FILES,
    build_caseprep_schema,
    build_caseprep_schema_from_axis_data,
    render_caseprep_files,
)


def test_build_caseprep_schema_has_core_sections():
    schema = build_caseprep_schema(
        "retrosigmoid vestibular schwannoma",
        profile="skull_base",
    )

    assert schema["schema_version"] == "0.2"
    assert schema["topic"] == "retrosigmoid vestibular schwannoma"
    assert schema["case_profile"] == "skull_base"
    assert schema["status"] == "draft"

    case = schema["case"]
    for section in [
        "case_snapshot",
        "indication_and_decision",
        "patient_context",
        "imaging_review",
        "anatomy_at_risk",
        "operative_plan",
        "risk_and_rescue",
        "postop_plan",
        "evidence",
        "verification",
    ]:
        assert section in case

    skull_base = schema["profile_extensions"]["skull_base"]
    assert "cranial_nerves" in skull_base
    assert "facial_nerve_status" in skull_base["cranial_nerves"]
    assert schema["provenance"]
    assert schema["provenance"][0]["value_status"] == "generated"


def test_render_caseprep_files_contains_only_canonical_files():
    schema = build_caseprep_schema(
        "retrosigmoid vestibular schwannoma",
        profile="skull_base",
    )
    files = render_caseprep_files(schema)

    for filename in CANONICAL_MARKDOWN_FILES:
        assert filename in files, f"missing canonical file {filename}"

    retired_aliases = {"anatomy.md", "approach.md", "complications.md", "literature.md"}
    assert retired_aliases.isdisjoint(files)

    assert "caseprep.yaml" in files
    assert "provenance.json" in files
    assert "## Preparation Status" in files["README.md"]
    assert "## Imaging Review Checklist" in files["02-imaging-review.md"]
    assert "## Anatomy At Risk" in files["03-anatomy-at-risk.md"]
    assert "## Approach Selection Matrix" in files["04-operative-plan.md"]
    assert "## Rescue Triggers" in files["05-risk-and-rescue.md"]
    assert "## Immediate Postop Orders" in files["06-postop-plan.md"]
    assert "## Clinical Questions" in files["07-evidence.md"]
    assert "## Day-Of Safety Checklist" in files["08-checklists.md"]
    assert "## Attending / Team Questions" in files["09-open-questions.md"]

    provenance = json.loads(files["provenance.json"])
    assert provenance[0]["field_path"] == "case.case_snapshot"


def test_build_schema_from_axis_data_adds_evidence_sources():
    axis_data = {
        "Surgical Technique": [
            {
                "pmid": "12345",
                "title": "Retrosigmoid Approach Study",
                "authors": "Doe J et al.",
                "source": "J Neurosurg",
                "pubdate": "2024 Sep",
                "doi": "10.1000/test",
                "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
                "_abstract": "The retrosigmoid approach provides exposure of the cerebellopontine angle.",
                "_structured": {},
            }
        ],
        "Complications": [
            {
                "pmid": "67890",
                "title": "CSF Leak After Skull Base Surgery",
                "authors": "Roe A et al.",
                "source": "World Neurosurg",
                "pubdate": "2023",
                "doi": "",
                "url": "https://pubmed.ncbi.nlm.nih.gov/67890/",
                "_abstract": "CSF leak is a postoperative complication.",
                "_structured": {},
            }
        ],
    }

    schema = build_caseprep_schema_from_axis_data(
        "retrosigmoid vestibular schwannoma",
        axis_data,
        profile="skull_base",
    )

    evidence = schema["case"]["evidence"]
    assert evidence["clinical_questions"]
    assert evidence["key_sources"][0]["id"] == "pmid-12345"
    assert evidence["key_sources"][0]["relevance"] == "surgical technique"
    assert evidence["key_sources"][1]["id"] == "pmid-67890"
    assert evidence["key_sources"][1]["relevance"] == "complications"
    assert schema["citations"][0]["pmid"] == "12345"
    assert any(p["field_path"] == "case.evidence.key_sources" for p in schema["provenance"])


def test_build_schema_from_axis_data_deduplicates_pmids():
    paper = {
        "pmid": "12345",
        "title": "Retrosigmoid Approach Study",
        "authors": "Doe J et al.",
        "source": "J Neurosurg",
        "pubdate": "2024 Sep",
        "doi": "10.1000/test",
        "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
        "_abstract": "The retrosigmoid approach provides exposure.",
        "_structured": {},
    }
    schema = build_caseprep_schema_from_axis_data(
        "retrosigmoid vestibular schwannoma",
        {
            "Surgical Technique": [paper],
            "Reviews / Landmarks": [paper],
        },
        profile="skull_base",
    )

    assert len(schema["case"]["evidence"]["key_sources"]) == 1
    assert len(schema["citations"]) == 1
