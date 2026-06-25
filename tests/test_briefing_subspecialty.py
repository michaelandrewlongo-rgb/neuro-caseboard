"""Routing-specificity: verify subspecialty cases route to the correct equipment schema.

Equipment is a discriminated union (kind="spine" | "endovascular" | "cranial"), so once
the routing signal eq.kind matches, the Pydantic type system structurally guarantees field
separation (e.g., SpineEquipment lacks catheters_wires by type definition, not by runtime
check). These tests verify:
1. The routing signal eq.kind is set correctly per subspecialty.
2. The expected content fields (eq.cage_class_sizing, eq.devices, eq.instruments_clips)
   are present in the routed schema, proving the bundle was enriched by synthesis.
3. A cross-profile assertion proves the three subspecialties route to DISTINCT kinds.

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
    # Routing: spine case routes to SpineEquipment (kind="spine").
    # Content: synthesizer populated cage_class_sizing field (present + non-empty).
    assert eq.kind == "spine" and eq.cage_class_sizing


def test_endovascular_case_uses_endo_schema():
    eq = _bundle("ruptured ACoA aneurysm coiling").briefing.equipment
    # Routing: endovascular case routes to EndovascularEquipment (kind="endovascular").
    # Content: synthesizer populated devices field (present + non-empty).
    assert eq.kind == "endovascular" and eq.devices


def test_cranial_case_uses_cranial_schema():
    eq = _bundle("left retrosigmoid vestibular schwannoma").briefing.equipment
    # Routing: cranial case routes to CranialEquipment (kind="cranial").
    # Content: synthesizer populated instruments_clips field (present + non-empty).
    assert eq.kind == "cranial" and eq.instruments_clips


def test_three_profiles_route_distinctly():
    """Prove the three subspecialties route to DISTINCT equipment kinds.

    This is the genuinely non-vacuous cross-case routing check: if subspecialty
    routing were broken and (e.g.) spine and cranial both routed to CranialEquipment,
    this test would catch it immediately.
    """
    cranial_bundle = _bundle("left retrosigmoid vestibular schwannoma")
    spine_bundle = _bundle("C5-6 ACDF")
    endo_bundle = _bundle("ruptured ACoA aneurysm coiling")

    kinds = {
        cranial_bundle.briefing.equipment.kind,
        spine_bundle.briefing.equipment.kind,
        endo_bundle.briefing.equipment.kind,
    }
    # All three subspecialties must route to distinct kinds.
    assert len(kinds) == 3, f"Expected 3 distinct kinds, got {kinds}"
