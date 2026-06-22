import pytest

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


def test_lexical_rejects_long_offtopic_premise_sharing_few_tokens():
    # A 60+ word off-topic (spine/orthopedic) premise that incidentally shares only ~2 generic
    # tokens ("artery", "preserve") with the neurovascular hypothesis must NOT count as entailment:
    # the shared tokens are too small a fraction of either side to support the claim.
    v = LexicalVerifier()
    premise = (
        "The orthopedic spine surgeon planned a multilevel lumbar pedicle screw construct and "
        "reviewed each vertebral level, noting the convergent sagittal trajectory through the pars "
        "interarticularis, the facet joints, the disc spaces, the ligamentum flavum, and the "
        "segmental musculature, electing to preserve the dorsal fascia while a small incidental "
        "epidural artery was cauterized within the routine posterior decompression and instrumented "
        "fusion."
    )
    hypothesis = "Preserve the recurrent artery of Heubner during careful microsurgical dissection."
    assert len(premise.split()) >= 60
    # Recall clears the bar (~0.25) but the shared tokens are a tiny fraction of the long premise
    # (precision ~0.04) -> not entailment.
    assert v.entails(premise, hypothesis) is False


def test_lexical_entails_long_ontopic_multisentence_premise():
    # The real-world failure (run pr50-groundedness): a long MULTI-sentence on-topic textbook chunk
    # that states the claim in ONE of its sentences. The shipped gate computed precision against the
    # WHOLE chunk, so a short well-supported claim scored precision ~0.14 (< 0.20) and was wrongly
    # flagged unsupported despite recall ~0.88. Precision must be judged against the best-matching
    # premise sentence (length-invariant), not the whole chunk.
    v = LexicalVerifier()
    premise = (
        "Aneurysms of the internal carotid artery represent a heterogeneous group of lesions with "
        "varied natural history depending on size, location, and morphology. Microsurgical clipping "
        "was historically the mainstay of treatment for these complex lesions. "
        "Flow diversion with the pipeline embolization device has become the preferred treatment for "
        "large and giant unruptured aneurysms of the internal carotid artery. "
        "Dual antiplatelet therapy with aspirin and clopidogrel is mandatory to mitigate "
        "thromboembolic complications during and after device deployment. "
        "Reported complete occlusion rates exceed eighty percent at one year of angiographic follow-up."
    )
    claim = "Flow diversion is the preferred treatment for large unruptured aneurysms of the internal carotid artery."
    assert len(premise.split()) >= 60          # genuinely long, multi-sentence
    assert v.entails(premise, claim) is True    # RED on shipped (whole-chunk precision) -> GREEN after fix


def test_lexical_rejects_long_multisentence_offtopic_premise():
    # Guard the fix does NOT over-pass: a long multi-sentence OFF-topic chunk (no single sentence
    # densely matches the claim) must stay rejected even with per-sentence precision.
    v = LexicalVerifier()
    premise = (
        "Photosynthesis converts sunlight, water, and carbon dioxide into glucose and oxygen. "
        "Chlorophyll within the thylakoid membranes of chloroplasts absorbs light energy. "
        "The light-dependent reactions generate adenosine triphosphate and reduced nicotinamide. "
        "The Calvin cycle then fixes inorganic carbon into three-carbon sugars. "
        "Stomata on the leaf surface regulate gas exchange and transpirational water loss."
    )
    claim = "Flow diversion is the preferred treatment for large unruptured aneurysms of the internal carotid artery."
    assert len(premise.split()) >= 40
    assert v.entails(premise, claim) is False


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
    monkeypatch.delenv("CASEBOARD_NLI_MODEL", raising=False)
    monkeypatch.setattr(pipe, "compile_case_dossier", spy)
    pipe.build_case_dossier(_case(), enrich=False, use_llm=False, literature=False)
    assert isinstance(captured["verifier"], ClaimVerifier)
    assert isinstance(captured["verifier"], LexicalVerifier)


# --------------------------------------------------------------------------- NLIVerifier (stubbed)
# These exercise NLIVerifier without importing sentence_transformers, by injecting a tiny stub model
# that exposes `.config.id2label` and `.predict` — the contract the lazy CrossEncoder satisfies.

from neuro_caseboard.entailment import NLIVerifier


class _StubModel:
    """Minimal CrossEncoder stand-in: fixed id2label + fixed per-pair raw scores (logits)."""

    def __init__(self, id2label, scores):
        self.config = SimpleNamespace(id2label=id2label)
        self._scores = scores

    def predict(self, pairs):
        return [self._scores for _ in pairs]


_MNLI = {0: "CONTRADICTION", 1: "NEUTRAL", 2: "ENTAILMENT"}


def test_nli_entail_index_read_from_id2label():
    # MNLI order is [contradiction, neutral, entailment]; entailment is index 2, NOT 1.
    model = _StubModel(_MNLI, scores=[0.1, 0.2, 5.0])  # logits peak at index 2
    v = NLIVerifier(model=model)
    assert v._entail_index == 2
    assert v.entails("some premise span", "some hypothesis claim") is True


def test_nli_does_not_treat_neutral_index_as_entailed():
    # A strong NEUTRAL (index 1) peak must read as NOT entailed (the bug the id2label fix closes).
    model = _StubModel(_MNLI, scores=[0.1, 5.0, 0.2])
    v = NLIVerifier(model=model)
    assert v.entails("p", "h") is False


def test_nli_confidence_threshold_rejects_below_threshold():
    # Entailment is the argmax but only ~0.35 of the mass: below the 0.5 gate -> not entailed.
    model = _StubModel(_MNLI, scores=[2.0, 1.9, 2.1])
    v = NLIVerifier(model=model, entail_threshold=0.5)
    assert v.entails("p", "h") is False
    # A lower threshold accepts the same split (argmax is still entailment).
    assert NLIVerifier(model=model, entail_threshold=0.3).entails("p", "h") is True


def test_nli_rejects_unusable_label_space():
    # A scalar/regression head (single label) is rejected so get_default_verifier() can fall back.
    with pytest.raises(ValueError):
        NLIVerifier(model=_StubModel({0: "LABEL_0"}, scores=[1.0]))
