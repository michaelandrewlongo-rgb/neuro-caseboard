"""Pipeline orchestration: Explorer -> (Enricher -> Auditor) -> compile -> render.

Exercises the offline path (no retriever), which is deterministic and corpus-free, so it
runs anywhere. Live corpus enrichment is covered by manual end-to-end runs.
"""

import pytest

from neuro_caseboard.pipeline import classify_profile, build_dossier
from neuro_caseboard.render_md import render_markdown


@pytest.mark.parametrize("topic,prof", [
    ("C5-6 corpectomy", "spine"),
    ("left vestibular schwannoma, retrosigmoid", "skull_base"),
    ("right carotid endarterectomy", "vascular"),
])
def test_classify_profile(topic, prof):
    assert classify_profile(topic) == prof


def test_build_manifest_prunes_offtarget_bleed_offline():
    from neuro_caseboard.pipeline import build_manifest
    m, _ = build_manifest("right frontal non-eloquent convexity meningioma resection",
                          use_llm=False)
    text = " ".join(f"{c.question} {c.why_it_matters}" for c in m.cards).lower()
    assert "cerebellopontine" not in text
    assert "ix-xi" not in text  # the posterior/CPA lower-cranial-nerve litany is stripped


def test_build_manifest_uses_llm_when_enabled(monkeypatch):
    """When use_llm=True, the LLM Explorer's case-specific cards are used (mocked here)."""
    from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest
    from neuro_caseboard import pipeline

    fake = QuestionManifest(procedure_family="llm_generated", cards=[
        QuestionCard(target_file="04-operative-plan.md", section_key="critical_steps",
                     question=f"LLM-specific operative step {i}", why_it_matters="w",
                     compiler_slot="Critical Steps")
        for i in range(8)])
    monkeypatch.setattr("neuro_caseboard.explore_llm.build_llm_manifest", lambda topic: fake)

    m, _ = pipeline.build_manifest("some procedure with no template", use_llm=True)
    assert any("LLM-specific" in c.question for c in m.cards)


@pytest.mark.parametrize("topic", [
    "C5-6 corpectomy",
    "left vestibular schwannoma retrosigmoid",
    "awake left temporal glioma resection",
    "right carotid endarterectomy",
])
def test_build_dossier_offline_produces_clean_board(topic):
    d = build_dossier(topic, enrich=False)
    headings = [s.heading for s in d.sections]
    assert "Anatomy at Risk" in headings
    assert "Operative Plan" in headings
    assert "Risk and Rescue" in headings
    # offline: nothing corpus-supported, everything to verify, nothing quarantined
    assert d.summary.supported == 0 and d.summary.quarantined == 0
    assert d.summary.to_verify > 0
    claims = [c for s in d.sections for c in s.claims]
    assert claims and all(c.status == "verify" and c.why for c in claims)
    md = render_markdown(d)
    assert "[low]" not in md and "🟢" not in md
    assert "✓" in md and "⚠" in md
