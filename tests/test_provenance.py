"""Provenance: the LLM-vs-deterministic source flag carried on every Dossier."""

from neuro_caseboard.model import (
    Dossier, EvidenceSummary, Provenance, FALLBACK_BANNER, fallback_notice,
)


def test_provenance_defaults_are_benign():
    p = Provenance()
    assert p.degraded is False
    assert p.source_label  # non-empty human label
    assert fallback_notice(p) is None


def test_fallback_notice_only_when_degraded():
    assert fallback_notice(Provenance(source="deterministic", degraded=True)) == FALLBACK_BANNER
    assert fallback_notice(Provenance(source="llm_generated", degraded=False)) is None


def test_dossier_has_default_provenance():
    d = Dossier(title="t", summary=EvidenceSummary())
    assert isinstance(d.provenance, Provenance)
    assert d.provenance.degraded is False


def test_compile_dossier_threads_provenance():
    from neuro_caseboard.compile import compile_dossier
    from caseprep.audit.card_auditor import AuditedCard, AuditedManifest

    card = AuditedCard(question="A concrete operative step", why_it_matters="w",
                       target_file="04-operative-plan.md", section_key="critical_steps",
                       compiler_slot="Critical Steps", answerability="needs_patient_fact",
                       audit_status="no_evidence")
    audited = AuditedManifest(procedure_family="deterministic", cards=[card])
    prov = Provenance(source="deterministic", degraded=True, reason="llm_error", detail="RuntimeError")
    d = compile_dossier(audited, topic="acdf", provenance=prov)
    assert d.provenance is prov
    # default path still works (no provenance passed -> benign default)
    d2 = compile_dossier(audited, topic="acdf")
    assert d2.provenance.degraded is False


# ---------------------------------------------------------------------------
# Task 2: _resolve_manifest decision-point provenance + PHI-safe fallback log
# ---------------------------------------------------------------------------

def _fake_manifest(n=8):
    from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest
    return QuestionManifest(procedure_family="llm_generated", cards=[
        QuestionCard(target_file="04-operative-plan.md", section_key="critical_steps",
                     question=f"LLM step {i}", why_it_matters="w", compiler_slot="Critical Steps")
        for i in range(n)])


def test_resolve_disabled_is_not_degraded():
    from neuro_caseboard.pipeline import _resolve_manifest
    _m, _prof, prov = _resolve_manifest("acdf c5-6", use_llm=False)
    assert prov.source == "deterministic" and prov.degraded is False
    assert prov.reason == "llm_disabled"


def test_resolve_llm_success_is_not_degraded(monkeypatch):
    from neuro_caseboard import pipeline
    monkeypatch.setattr("neuro_caseboard.explore_llm.build_llm_manifest",
                        lambda topic: _fake_manifest())
    _m, _prof, prov = pipeline._resolve_manifest("some procedure no template", use_llm=True)
    assert prov.degraded is False
    assert prov.source in ("llm_generated", "llm+template")


def test_resolve_llm_error_is_degraded_and_logged_phi_safe(monkeypatch, caplog):
    from neuro_caseboard import pipeline

    def boom(topic):
        raise RuntimeError("api down")

    monkeypatch.setattr("neuro_caseboard.explore_llm.build_llm_manifest", boom)
    with caplog.at_level("WARNING", logger="neuro_caseboard.pipeline"):
        _m, _prof, prov = pipeline._resolve_manifest("SECRET_PATIENT craniotomy", use_llm=True)
    assert prov.degraded is True
    assert prov.reason == "llm_error" and prov.detail == "RuntimeError"
    assert "reason=llm_error" in caplog.text
    assert "SECRET_PATIENT" not in caplog.text          # PHI-safe: no topic in logs


def test_resolve_llm_underproduced_is_degraded_and_logged(monkeypatch, caplog):
    from neuro_caseboard import pipeline
    monkeypatch.setattr("neuro_caseboard.explore_llm.build_llm_manifest", lambda topic: None)
    with caplog.at_level("WARNING", logger="neuro_caseboard.pipeline"):
        _m, _prof, prov = pipeline._resolve_manifest("acdf", use_llm=True)
    assert prov.degraded is True and prov.reason == "llm_underproduced"
    assert "reason=llm_underproduced" in caplog.text


def test_build_manifest_wrapper_still_two_tuple(monkeypatch):
    from neuro_caseboard.pipeline import build_manifest
    m, prof = build_manifest("acdf c5-6", use_llm=False)   # must remain a 2-tuple
    assert m.cards and isinstance(prof, str)


def test_build_dossier_degraded_sets_provenance(monkeypatch):
    from neuro_caseboard.pipeline import build_dossier

    def boom(topic):
        raise RuntimeError("api down")

    monkeypatch.setattr("neuro_caseboard.explore_llm.build_llm_manifest", boom)
    d = build_dossier("awake left temporal glioma", enrich=False, use_llm=True)
    assert d.provenance.degraded is True

    d2 = build_dossier("awake left temporal glioma", enrich=False, use_llm=False)
    assert d2.provenance.degraded is False


# ---------------------------------------------------------------------------
# Task 4: Markdown fallback banner
# ---------------------------------------------------------------------------

def test_markdown_banner_present_only_when_degraded():
    from neuro_caseboard.render_md import render_markdown
    base = dict(title="Case Board — acdf", summary=EvidenceSummary(to_verify=1))
    degraded = Dossier(provenance=Provenance(source="deterministic", degraded=True), **base)
    ok = Dossier(provenance=Provenance(source="llm_generated", degraded=False), **base)
    assert FALLBACK_BANNER in render_markdown(degraded)
    assert FALLBACK_BANNER not in render_markdown(ok)


# ---------------------------------------------------------------------------
# Task 5: PDF fallback banners (exec-Navy HTML + fpdf2 clinical)
# ---------------------------------------------------------------------------

def test_exec_html_banner_present_only_when_degraded():
    from neuro_caseboard.caseboard_pdf import build_caseboard_html
    base = dict(title="Case Board — acdf", summary=EvidenceSummary(to_verify=1))
    degraded = Dossier(provenance=Provenance(source="deterministic", degraded=True), **base)
    ok = Dossier(provenance=Provenance(source="llm_generated", degraded=False), **base)
    assert "fallback-banner" in build_caseboard_html(degraded)
    assert "fallback-banner" not in build_caseboard_html(ok)


def test_fpdf_renderer_handles_degraded(tmp_path):
    # fpdf2 binary output is not text-greppable; assert it renders a valid PDF without crashing
    # when degraded (the banner code path is exercised).
    from neuro_caseboard.render_pdf import render_pdf
    d = Dossier(title="Case Board — acdf", summary=EvidenceSummary(to_verify=1),
                provenance=Provenance(source="deterministic", degraded=True))
    art = render_pdf(d, tmp_path / "x.pdf")
    assert art.path.read_bytes()[:5].startswith(b"%PDF")
