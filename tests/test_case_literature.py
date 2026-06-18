"""WS-3: contemporary literature attached to the case dossier's Reasoning / Alternatives / Risks
sections, on a separate [L#] axis. Offline — a canned cache + synth stub feed the real lane, so no
network. Pins the never-fabricate guarantee: every [L#] resolves to an injected record.
"""

from neuro_caseboard.case_context import CaseContext
from neuro_caseboard.case_literature import attach_case_literature, section_query, LIT_SECTIONS
from neuro_caseboard.literature.config import LiteratureConfig
from neuro_caseboard.literature.retriever import LiteratureRecord
from neuro_caseboard.model import Dossier, EvidenceSummary, Section, Claim


CASE = CaseContext(level="C5-6", pathology="cervical spondylotic myelopathy",
                   procedure="ACDF", surgical_goal="decompression")


def test_literature_falls_back_to_term_when_rewrite_returns_zero(monkeypatch):
    """qa.build_literature_section: a bad LLM query-rewrite (0 results) must retry once with the
    deterministic term, so a salvageable query is never silently lost (the case-2 root cause).
    Fully offline — the retriever/rewrite/synth seams are faked, no network."""
    import types
    import neuro_caseboard.qa as qa
    rec = LiteratureRecord(pmid="111", title="Adult spinal deformity outcomes",
                           journal="Spine", year=2024, doi="d", url="", abstract="")

    class _Cache:
        def get(self, k): return None
        def set(self, k, v): pass

    class _FakeRetriever:
        def __init__(self, *a, **k): pass
        async def retrieve(self, question, *, query):
            return [rec] if query == "TERM" else []      # the term works; the rewrite returns 0

    monkeypatch.setattr("neuro_caseboard.literature.retriever.build_query_terms", lambda q: "TERM")
    monkeypatch.setattr("neuro_caseboard.literature.retriever.rewrite_pubmed_query",
                        lambda q, s: "OVER-NARROWED REWRITE")
    monkeypatch.setattr("neuro_caseboard.literature.retriever.LiteratureRetriever", _FakeRetriever)
    monkeypatch.setattr("neuro_caseboard.literature.synth.synthesize_literature",
                        lambda q, recs, s: types.SimpleNamespace(narrative="Evidence [L1].", records=list(recs)))

    cfg = LiteratureConfig(enabled=True, recency_years=7, k=8, cache_ttl_days=14,
                           ncbi_api_key="", cache_dir="/tmp")
    out = qa.build_literature_section(
        "adult degenerative scoliosis coronal deformity correction outcomes",
        lit_config=cfg, client=object(), synth_client=object(), cache=_Cache())
    assert out is not None, "fallback to the deterministic term should have recovered records"
    assert len(out.citations) == 1 and out.citations[0].pmid == "111"


def _records():
    return [
        LiteratureRecord(pmid="111", title="ACDF outcomes RCT", journal="Spine", year=2024,
                         doi="10.1/abc", url="https://pubmed/111", abstract="Good outcomes."),
        LiteratureRecord(pmid="222", title="Cervical myelopathy review", journal="JNS", year=2023,
                         doi="", url="https://pubmed/222", abstract="Natural history data."),
    ]


class _Cache:
    def __init__(self, records):
        self._records = records

    def get(self, key):
        return self._records      # canned -> no PubMed client call

    def set(self, key, records):
        pass


class _Synth:
    def generate(self, system, user, images):
        return "Recent evidence supports decompression [L1]; review summarizes history [L2]."


def _cfg(enabled=True):
    return LiteratureConfig(enabled=enabled, recency_years=7, k=8, cache_ttl_days=14,
                            ncbi_api_key="", cache_dir="/tmp/x")


def _dossier():
    headings = ["Clinical Summary", "Clinical Reasoning", "Operative Plan",
                "Alternatives", "Risks", "Surgical Technique"]
    return Dossier(title="Case Dossier — C5-6 ACDF",
                   summary=EvidenceSummary(),
                   sections=[Section(heading=h, claims=[Claim(text=f"{h} claim", why="w")])
                             for h in headings])


def test_section_query_only_for_the_three_lit_sections():
    assert set(LIT_SECTIONS) == {"Clinical Reasoning", "Alternatives", "Risks"}
    for h in LIT_SECTIONS:
        q = section_query(h, CASE)
        assert q and "cervical spondylotic myelopathy" in q   # built from the case's pathology
    assert section_query("Operative Plan", CASE) is None
    assert section_query("Clinical Summary", CASE) is None


def test_section_query_is_case_specific_not_generic():
    """WS-3: the PubMed query must stay grounded in THIS case (its pathology/procedure), not a bare
    per-section focus token — relevance/recency quality starts with an on-topic query."""
    for h in LIT_SECTIONS:
        q = section_query(h, CASE)
        # the case's semantic anchors are embedded, plus a generic per-section focus
        assert "cervical spondylotic myelopathy" in q and "ACDF" in q
        assert len(q.split()) > 4


def test_section_query_omits_geometry_for_pubmed_recall():
    """Real-data regression: PubMed esearch ANDs every token, so prepending case GEOMETRY
    (laterality + level/location) collapses recall to zero — observed live: 'right thoracolumbar
    adult degenerative scoliosis coronal deformity correction indications outcomes' -> 0 records,
    while dropping the geometry -> 8 records. Build the query from the SEMANTIC fields
    (pathology + procedure) + the per-section focus, never the case geometry."""
    case = CaseContext(laterality="right", level="L1", location="thoracolumbar",
                       pathology="adult degenerative scoliosis",
                       procedure="coronal deformity correction", surgical_goal="coronal correction")
    q = section_query("Risks", case)
    assert q is not None
    toks = q.lower().split()
    assert "right" not in toks, f"laterality must not be in the literature query: {q!r}"
    assert "l1" not in toks and "thoracolumbar" not in toks, f"geometry must not be in the query: {q!r}"
    assert "adult degenerative scoliosis" in q and "coronal deformity correction" in q


def test_attach_literature_to_three_sections_no_fabrication():
    recs = _records()
    d = attach_case_literature(_dossier(), CASE, cache=_Cache(recs),
                               synth_client=_Synth(), lit_config=_cfg(True))
    by = {s.heading: s for s in d.sections}
    # the three target sections each carry a literature block with [L#] citations
    for h in ("Clinical Reasoning", "Alternatives", "Risks"):
        lit = by[h].literature
        assert lit is not None and lit.narrative and lit.citations
        # never fabricate: every cited PMID is one we actually returned
        assert {c.pmid for c in lit.citations} <= {"111", "222"}
        assert [c.n for c in lit.citations] == list(range(1, len(lit.citations) + 1))  # [L1..]
    # non-target sections are untouched (no literature axis)
    for h in ("Clinical Summary", "Operative Plan", "Surgical Technique"):
        assert by[h].literature is None


def test_disabled_config_attaches_nothing():
    d = attach_case_literature(_dossier(), CASE, cache=_Cache(_records()),
                               synth_client=_Synth(), lit_config=_cfg(False))
    assert all(s.literature is None for s in d.sections)
