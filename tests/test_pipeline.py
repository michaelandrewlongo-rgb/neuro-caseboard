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


@pytest.mark.parametrize("case_kwargs", [
    dict(laterality="right", level="C5-6", pathology="cervical spondylotic myelopathy",
         procedure="ACDF", surgical_goal="decompression"),
    dict(laterality="left", location="left frontal", pathology="diffuse glioma",
         procedure="awake craniotomy", surgical_goal="maximal safe resection"),
    dict(laterality="left", location="MCA bifurcation", pathology="ruptured MCA aneurysm",
         procedure="pterional clipping", surgical_goal="clip ligation"),
])
def test_build_case_dossier_offline_renders_eight_sections(case_kwargs):
    # Explicitly offline + deterministic (no provider, no retriever) across the three subspecialties.
    from neuro_caseboard.case_context import CaseContext
    from neuro_caseboard.pipeline import build_case_dossier
    d = build_case_dossier(CaseContext(**case_kwargs), enrich=False, use_llm=False,
                           literature=False)   # offline: no PubMed network
    headings = [s.heading for s in d.sections]
    for h in ["Clinical Summary", "Clinical Reasoning", "Operative Plan", "Alternatives",
              "Risks", "Pre-op Optimization", "Surgical Technique", "Case Figures"]:
        assert h in headings, f"missing section: {h}"
    assert "Case Dossier" in d.title
    # offline: single evidence axis, nothing corpus-supported / quarantined, everything to verify
    assert d.summary.supported == 0 and d.summary.quarantined == 0 and d.summary.to_verify > 0
    claims = [c for s in d.sections for c in s.claims]
    assert claims and all(c.status == "verify" and c.why for c in claims)


def test_build_case_dossier_attaches_literature_offline(monkeypatch):
    # WS-3: with literature on + an injected canned cache/synth (no network), the three
    # reasoning-bearing sections gain a [L#] block; literature=False attaches none.
    from neuro_caseboard.case_context import CaseContext
    from neuro_caseboard.pipeline import build_case_dossier
    from neuro_caseboard.literature.retriever import LiteratureRecord

    recs = [LiteratureRecord(pmid="111", title="ACDF RCT", journal="Spine", year=2024,
                             doi="10.1/x", url="", abstract="data")]

    class _Cache:
        def get(self, key):
            return recs
        def set(self, key, r):
            pass

    class _Synth:
        def generate(self, system, user, images):
            return "Recent evidence [L1]."

    # force the config flag on regardless of ambient env
    monkeypatch.setenv("LITERATURE_RETRIEVAL", "true")
    case = CaseContext(level="C5-6", pathology="cervical spondylotic myelopathy",
                       procedure="ACDF", surgical_goal="decompression")
    d = build_case_dossier(case, enrich=False, use_llm=False, literature=True,
                           lit_cache=_Cache(), lit_synth_client=_Synth())
    by = {s.heading: s for s in d.sections}
    for h in ("Clinical Reasoning", "Alternatives", "Risks"):
        assert by[h].literature is not None and by[h].literature.citations
        assert {c.pmid for c in by[h].literature.citations} <= {"111"}   # no fabrication
    assert by["Operative Plan"].literature is None

    d2 = build_case_dossier(case, enrich=False, use_llm=False, literature=False)
    assert all(s.literature is None for s in d2.sections)


def test_build_case_dossier_attaches_generated_schematics(tmp_path, monkeypatch):
    # WS-4: with figures_dir set, generated schematics attach to the Case Figures section
    # (deterministic, offline). Without it, no figures are generated.
    monkeypatch.setenv("CASEBOARD_LLM", "0")     # hermetic: deterministic figure author
    from neuro_caseboard.case_context import CaseContext
    from neuro_caseboard.pipeline import build_case_dossier
    case = CaseContext(laterality="left", level="C5-6",
                       pathology="cervical spondylotic myelopathy", procedure="ACDF",
                       surgical_goal="decompression")
    d = build_case_dossier(case, enrich=False, use_llm=False, literature=False,
                           figures_dir=tmp_path)
    fig_sec = next(s for s in d.sections if s.heading == "Case Figures")
    assert fig_sec.figures, "expected generated schematics in the Case Figures section"
    assert all(f.caption.startswith("Schematic (not a radiograph)") for f in fig_sec.figures)

    d2 = build_case_dossier(case, enrich=False, use_llm=False, literature=False)
    fig_sec2 = next(s for s in d2.sections if s.heading == "Case Figures")
    assert fig_sec2.figures == []        # no figures_dir -> none generated


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


@pytest.fixture
def _min_dossier():
    from neuro_caseboard.model import Dossier, EvidenceSummary, Section, Claim
    return Dossier(
        title="C5–6 ACDF",
        summary=EvidenceSummary(supported=1, to_verify=0, quarantined=0),
        sections=[Section(
            heading="Anatomy at risk", intro="Structures near the approach.",
            claims=[Claim(text="The vertebral artery runs in the foramen transversarium.",
                          why="Avoid far-lateral dissection.", status="supported")])])


def test_render_case_pdf_routes_style_to_theme(monkeypatch, tmp_path, _min_dossier):
    # CASEBOARD_PDF_STYLE maps to the HTML theme threaded into render_caseboard_pdf:
    # unset/exec (legacy) -> signal, print -> print. render_case_pdf imports the renderer
    # at call time, so patching the source attribute captures the theme kwarg.
    calls = {}

    def fake_render(dossier, path, *, subtitle="", theme="signal"):
        calls["theme"] = theme
        open(path, "wb").write(b"%PDF-1.4")
        return str(path)

    monkeypatch.setattr("neuro_caseboard.caseboard_pdf.render_caseboard_pdf", fake_render)
    from neuro_caseboard.pipeline import render_case_pdf

    monkeypatch.delenv("CASEBOARD_PDF_STYLE", raising=False)           # default -> signal
    render_case_pdf(_min_dossier, "topic", tmp_path / "a.pdf")
    assert calls["theme"] == "signal"
    monkeypatch.setenv("CASEBOARD_PDF_STYLE", "print")
    render_case_pdf(_min_dossier, "topic", tmp_path / "b.pdf")
    assert calls["theme"] == "print"
    monkeypatch.setenv("CASEBOARD_PDF_STYLE", "exec")                  # legacy -> signal
    render_case_pdf(_min_dossier, "topic", tmp_path / "c.pdf")
    assert calls["theme"] == "signal"
