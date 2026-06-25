"""Profile-specificity + cross-domain leakage controls.

We assert STRUCTURE and ABSENCE, never hardcoded clinical answer text.

NOTE ON FAKES: The brief's minimal TRec/TextRetriever stubs are INSUFFICIENT for
build_briefing_bundle, which calls build_case_dossier(enrich=True).  The caseprep
corpus_enricher._paper_summary reads .id, .title, .source off each record and the
enricher may call retriever.retrieve() with extra kwargs (e.g. subdomain=).  We reuse
the working fakes from tests/test_briefing_pipeline.py (Task 6) verbatim.
"""
from neuro_caseboard.pipeline import build_briefing_bundle


class TRec:
    """Satisfies gather_briefing_evidence (text+metadata) AND caseprep corpus_enricher
    (id+title+source+text+metadata)."""
    def __init__(self, n):
        self.id = f"rec-{n}"
        self.title = f"Youmans chapter {n}"
        self.source = "corpus"
        self.text = f"passage {n}"
        self.metadata = {"citation": f"Youmans p.{n}", "book": "Youmans", "page": n}


class TextRetriever:
    def retrieve(self, query, top_n=6, **kwargs):
        return [TRec(1)]


class ProfiledSynth:
    """Echoes the subspecialty into equipment so we can prove routing; emits a fixed schema."""
    def generate(self, system, user, images):
        from neuro_caseboard import briefing_synth as bs
        key = next(k for k in bs.SECTION_KEYS if f"SECTION={k}" in user)
        sub = "spine" if "Subspecialty: spine" in user else (
              "endovascular" if "Subspecialty: endovascular" in user else "cranial")
        if key == "equipment":
            if sub == "spine":
                return "cage_class_sizing: PEEK; instrumentation_system: pedicle screws\nrefs: T1\n"
            if sub == "endovascular":
                return "catheters_wires: 6F guide\ndevices: flow diverter\nrefs: T1\n"
            return "head_fixation: Mayfield\ninstruments_clips: aneurysm clips\nrefs: T1\n"
        if key == "modalities":
            return "### Option\nrole: x\npreferred: yes\nrefs: T1\n"
        return f"[high] {key} {{T1}}\n"


def _bundle(query):
    return build_briefing_bundle(query, use_llm=False, retriever=TextRetriever(),
                                 synth_client=ProfiledSynth(), literature=False)


def test_spine_case_uses_spine_equipment_schema():
    eq = _bundle("C5-6 ACDF").briefing.equipment
    assert eq.kind == "spine" and eq.cage_class_sizing
    # negative control: no endovascular catheter fields exist on the spine schema
    assert not hasattr(eq, "catheters_wires")


def test_endovascular_case_uses_endo_schema_no_spine_cage():
    eq = _bundle("ruptured ACoA aneurysm coiling").briefing.equipment
    assert eq.kind == "endovascular" and eq.devices
    assert not hasattr(eq, "cage_class_sizing")        # no TLIF cage in an endovascular case


def test_cranial_case_uses_cranial_schema_no_endo_catheters():
    eq = _bundle("left retrosigmoid vestibular schwannoma").briefing.equipment
    assert eq.kind == "cranial" and eq.instruments_clips
    assert not hasattr(eq, "catheters_wires")          # no endovascular catheters in open cranial
