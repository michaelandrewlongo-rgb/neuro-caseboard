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
    # Explicitly offline — must not depend on the ambient env lacking an LLM
    # provider (a dev shell that defaults to Vertex would otherwise make a real call).
    d = build_dossier(topic, enrich=False, use_llm=False)
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


def test_render_ask_pdf_clinical_style_uses_fpdf(monkeypatch, tmp_path):
    monkeypatch.setenv("CASEBOARD_PDF_STYLE", "clinical")
    from neuro_caseboard.pipeline import render_ask_pdf
    result = {"answer": "Answer [1].",
              "citations": [{"n": 1, "book": "Bk", "chapter": "", "page": 3}], "figures": []}
    out = render_ask_pdf(result, "Q?", tmp_path / "a.pdf")
    assert out.read_bytes()[:5].startswith(b"%PDF")


def test_render_ask_pdf_falls_back_when_chromium_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("CASEBOARD_PDF_STYLE", raising=False)
    import neuro_caseboard.briefing_pdf as bp

    def _boom(*a, **k):
        raise ImportError("no playwright")

    monkeypatch.setattr(bp, "render_briefing_pdf", _boom)
    from neuro_caseboard.pipeline import render_ask_pdf
    out = render_ask_pdf({"answer": "A.", "citations": [], "figures": []}, "Q?", tmp_path / "b.pdf")
    assert out.read_bytes()[:5].startswith(b"%PDF")  # fell back to fpdf2


def test_render_ask_pdf_reraises_real_bug(monkeypatch, tmp_path):
    import pytest
    monkeypatch.delenv("CASEBOARD_PDF_STYLE", raising=False)
    import neuro_caseboard.briefing_pdf as bp

    def _boom(*a, **k):
        raise AttributeError("genuine bug in the exec renderer")

    monkeypatch.setattr(bp, "render_briefing_pdf", _boom)
    from neuro_caseboard.pipeline import render_ask_pdf
    with pytest.raises(AttributeError):
        render_ask_pdf({"answer": "A.", "citations": [], "figures": []}, "Q?", tmp_path / "c.pdf")
