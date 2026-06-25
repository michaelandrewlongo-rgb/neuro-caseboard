from neuro_caseboard.pipeline import build_briefing_bundle
from neuro_caseboard.briefing_model import OperativeBriefingBundle


class FakeSynth:
    def __init__(self, fail=()):
        self.fail = set(fail)
    def generate(self, system, user, images):
        from neuro_caseboard import briefing_synth as bs
        key = next(k for k in bs.SECTION_KEYS if f"SECTION={k}" in user)
        if key in self.fail:
            raise RuntimeError("down")
        if key == "equipment":
            return "positioning_monitoring: prone; SSEP\nrefs: T1\n"
        if key == "modalities":
            return "### ACDF\nrole: decompress\npreferred: yes\nrefs: T1\n"
        return f"[critical] {key} claim {{T1}}\n"


class TRec:
    """Minimal fake that satisfies both gather_briefing_evidence (text+metadata)
    AND the caseprep corpus_enricher._paper_summary (id+title+source+text+metadata)."""
    def __init__(self, n):
        self.id = f"rec-{n}"
        self.title = f"Youmans chapter {n}"
        self.source = "corpus"
        self.text = f"passage {n}"
        self.metadata = {"citation": f"Youmans p.{n}", "book": "Youmans", "page": n}


class TextRetriever:
    def retrieve(self, query, top_n=6, **kwargs):
        return [TRec(1)]


def test_sparse_query_builds_valid_bundle_offline():
    b = build_briefing_bundle(
        "C5-6 ACDF", use_llm=False, retriever=TextRetriever(),
        fig_retriever=None, synth_client=FakeSynth(), literature=False)
    assert isinstance(b, OperativeBriefingBundle)
    assert b.briefing.sections and b.references               # sections + resolved refs
    assert b.briefing.equipment.kind == "spine"               # subspecialty routed
    assert b.provenance.degraded is False
    # dossier (full audit) preserved alongside the briefing
    assert b.dossier is not None
    # serializes for the API
    assert b.model_dump(mode="json")["kind"] == "briefing"


def test_pubmed_failure_is_honest_not_fabricated():
    # literature=False simulates the lane being off; provenance must say so, briefing still builds.
    b = build_briefing_bundle("C5-6 ACDF", use_llm=False, retriever=TextRetriever(),
                              synth_client=FakeSynth(), literature=False)
    assert b.provenance.literature_ok is False
    assert all(r.kind == "textbook" for r in b.references)     # no L# fabricated


def test_failed_section_recorded_in_provenance():
    b = build_briefing_bundle("C5-6 ACDF", use_llm=False, retriever=TextRetriever(),
                              synth_client=FakeSynth(fail=["risks"]), literature=False)
    assert "risks" in b.provenance.failed_sections
    assert b.provenance.degraded is True
