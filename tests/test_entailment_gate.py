from neuro_caseboard.entailment import LexicalVerifier, should_cite
from neuro_caseboard.entailment import get_default_verifier


def test_lexical_entails_when_overlap_high():
    v = LexicalVerifier()
    premise = "The recurrent artery of Heubner supplies the caudate head and must be preserved."
    assert v.entails(premise, "Preserve the recurrent artery of Heubner.") is True


def test_lexical_rejects_when_disjoint():
    v = LexicalVerifier()
    premise = "Lumbar pedicle screw trajectories follow the convergent sagittal angle."
    assert v.entails(premise, "Preserve the recurrent artery of Heubner.") is False


def test_should_cite_abstains_keep_on_thin_premise():
    assert should_cite("Reference corpus record 1",
                       "Preserve the recurrent artery of Heubner.", LexicalVerifier()) is True


def test_should_cite_withholds_on_substantial_disjoint_premise():
    premise = "Lumbar pedicle screw trajectories follow the convergent sagittal angle through the pars."
    assert should_cite(premise, "Preserve the recurrent artery of Heubner.", LexicalVerifier()) is False


def test_default_verifier_is_lexical_without_model_env(monkeypatch):
    monkeypatch.delenv("CASEBOARD_NLI_MODEL", raising=False)
    assert isinstance(get_default_verifier(), LexicalVerifier)


from types import SimpleNamespace
from neuro_caseboard.compile import compile_case_dossier
from neuro_caseboard.case_sections import CORPUS_ELIGIBLE_FILES
from neuro_caseboard.case_context import CaseContext


def _card(tf, q, papers, status="supported"):
    return SimpleNamespace(target_file=tf, question=q, why_it_matters="", compiler_slot="",
                           section_key="op", audit_status=status, audit_reason="", papers=papers)


def _case():
    return CaseContext(laterality="left", location="MCA bifurcation", pathology="aneurysm",
                       procedure="pterional clipping", surgical_goal="clip ligation")


def _claims(d):
    return [c for s in d.sections for c in s.claims]


def test_disjoint_span_withholds_citation_and_downgrades():
    tf = sorted(CORPUS_ELIGIBLE_FILES)[0]
    paper = {"title": "Off-topic spine paper",
             "text_snippet": "Lumbar pedicle screw trajectories follow the convergent sagittal "
                             "angle through the pars interarticularis."}
    d = compile_case_dossier(SimpleNamespace(cards=[_card(tf,
            "Preserve the recurrent artery of Heubner during dissection.", [paper])]),
            case=_case(), verifier=LexicalVerifier())
    c = _claims(d)[0]
    assert "[1]" not in c.text and c.status == "verify"


def test_entailing_span_keeps_citation():
    tf = sorted(CORPUS_ELIGIBLE_FILES)[0]
    paper = {"title": "Heubner anatomy",
             "text_snippet": "The recurrent artery of Heubner arises near the anterior communicating "
                             "artery and must be preserved during dissection of the region."}
    d = compile_case_dossier(SimpleNamespace(cards=[_card(tf,
            "Preserve the recurrent artery of Heubner during dissection.", [paper])]),
            case=_case(), verifier=LexicalVerifier())
    c = _claims(d)[0]
    assert "[1]" in c.text and c.status == "supported"


def test_pipeline_passes_verifier_through(monkeypatch):
    import neuro_caseboard.pipeline as pipe
    from neuro_caseboard.entailment import ClaimVerifier
    captured = {}
    real = pipe.compile_case_dossier
    def spy(*a, **k):
        captured["verifier"] = k.get("verifier")
        return real(*a, **k)
    monkeypatch.setattr(pipe, "compile_case_dossier", spy)
    pipe.build_case_dossier(_case(), enrich=False, use_llm=False, literature=False)
    assert isinstance(captured["verifier"], ClaimVerifier)
