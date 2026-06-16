"""Case-section author: CaseContext -> QuestionManifest across the 8 case surfaces.

Mirrors test_explore_llm.py — the model call is injected (complete_fn), so these tests are
deterministic and never touch the network. Also pins the topic-agnostic invariant: the
deterministic scaffold composes from the case's own fields + ontology dimension labels, never a
hardcoded clinical literal from another subspecialty.
"""

import json

import pytest

from neuro_caseboard.case_context import CaseContext
from neuro_caseboard.case_author import build_case_manifest, deterministic_case_manifest
from neuro_caseboard.case_sections import CASE_ORDER


def _fake(payload):
    return lambda system, user: payload


def _c(tf, key, q="a specific case statement", w="a specific consequence"):
    return {"target_file": tf, "section_key": key, "question": q, "why_it_matters": w}


SPINE = CaseContext(laterality="right", level="C5-6",
                    pathology="cervical spondylotic myelopathy",
                    procedure="ACDF", surgical_goal="decompression",
                    comorbidities=["hypertension", "type 2 diabetes"],
                    presentation="62F with progressive myelopathy and right C6 radiculopathy")
CRANIAL = CaseContext(laterality="left", location="left frontal",
                      pathology="diffuse glioma", procedure="awake craniotomy",
                      surgical_goal="maximal safe resection",
                      presentation="38F with word-finding difficulty and seizures")
VASCULAR = CaseContext(laterality="left", location="MCA bifurcation",
                       pathology="ruptured MCA aneurysm",
                       procedure="pterional clipping", surgical_goal="clip ligation",
                       presentation="65F with thunderclap headache and SAH")

VALID = {"cards": [
    _c("01-clinical-summary.md", "presentation"),
    _c("02-clinical-reasoning.md", "indication"),
    _c("04-operative-plan.md", "critical_steps"),
    _c("06-alternatives.md", "tradeoff"),
    _c("05-risk-and-rescue.md", "catastrophic_complications"),
    _c("07-preop-optimization.md", "medical_optimization"),
    _c("08-surgical-technique.md", "approach_corridor"),
    _c("09-case-figures.md", "schematic"),
    _c("01-clinical-summary.md", "made_up_key"),       # invalid section_key -> dropped
    _c("99-not-a-section.md", "presentation"),          # invalid file -> dropped
    _c("02-clinical-reasoning.md", "indication", q=" "),  # empty question -> dropped
]}


def test_llm_author_keeps_only_valid_cards_across_the_eight_files():
    m = build_case_manifest(SPINE, complete_fn=_fake(json.dumps(VALID)))
    files = {c.target_file for c in m.cards}
    assert files <= set(CASE_ORDER)
    assert len(m.cards) == 8                      # 8 valid, 3 invalid dropped
    keys = {c.section_key for c in m.cards}
    assert "made_up_key" not in keys


def test_llm_author_derives_compiler_slot_title_case():
    m = build_case_manifest(SPINE, complete_fn=_fake(json.dumps(VALID)))
    slots = {c.section_key: c.compiler_slot for c in m.cards}
    assert slots["catastrophic_complications"] == "Catastrophic Complications"
    assert slots["approach_corridor"] == "Approach Corridor"


def test_llm_author_falls_back_on_error_and_unparseable():
    def boom(s, u):
        raise RuntimeError("api down")
    m1 = build_case_manifest(SPINE, complete_fn=boom)
    m2 = build_case_manifest(SPINE, complete_fn=_fake("not json"))
    # both fall back to the deterministic scaffold (still covers all sections)
    for m in (m1, m2):
        assert {c.target_file for c in m.cards} >= set(CASE_ORDER)


def test_llm_author_backfills_missing_sections_when_cards_cluster():
    # Six valid cards, but clustered in only Operative Plan + Risks. The compiler drops empty
    # sections, so a count-only acceptance gate would ship a dossier missing Clinical Summary,
    # Reasoning, Alternatives, Pre-op, and Technique. The author must guarantee every author-owned
    # section is covered — backfilling the gaps from the deterministic scaffold, NOT discarding the
    # good LLM cards via a blunt full fallback.
    clustered = {"cards": [
        _c("04-operative-plan.md", "critical_steps"),
        _c("04-operative-plan.md", "decision_points"),
        _c("04-operative-plan.md", "stop_points"),
        _c("05-risk-and-rescue.md", "likely_complications"),
        _c("05-risk-and-rescue.md", "catastrophic_complications"),
        _c("05-risk-and-rescue.md", "mitigation"),
    ]}
    m = build_case_manifest(SPINE, complete_fn=_fake(json.dumps(clustered)))
    files = {c.target_file for c in m.cards}
    required = set(CASE_ORDER) - {"09-case-figures.md"}   # figures come from figures_gen, not here
    assert required <= files, f"missing: {required - files}"
    assert m.procedure_family == "case_llm"               # kept the LLM cards, did not fully fall back
    # the three authored Operative-Plan cards survive untouched
    assert sum(1 for c in m.cards if c.target_file == "04-operative-plan.md") >= 3


def test_llm_author_underproduction_falls_back():
    thin = {"cards": [_c("01-clinical-summary.md", "presentation")]}
    m = build_case_manifest(SPINE, complete_fn=_fake(json.dumps(thin)))
    assert {c.target_file for c in m.cards} >= set(CASE_ORDER)   # fell back


@pytest.mark.parametrize("case", [SPINE, CRANIAL, VASCULAR])
def test_deterministic_covers_every_section(case):
    m = deterministic_case_manifest(case)
    files = {c.target_file for c in m.cards}
    assert files >= set(CASE_ORDER), f"missing: {set(CASE_ORDER) - files}"
    assert all(c.compiler_slot and c.question for c in m.cards)


def test_deterministic_is_topic_agnostic_no_foreign_clinical_literal():
    # The purely-scaffolded sections (summary/reasoning/alternatives/figures) must not leak a
    # clinical term from another subspecialty — only the case's own words + process labels.
    m = deterministic_case_manifest(SPINE)
    scaffold = {"01-clinical-summary.md", "02-clinical-reasoning.md",
                "06-alternatives.md", "09-case-figures.md"}
    text = " ".join(c.question.lower() for c in m.cards if c.target_file in scaffold)
    for foreign in ("aneurysm", "vestibular", "glioma", "facial nerve"):
        assert foreign not in text
