from types import SimpleNamespace

from neuro_caseboard.qa import (
    answer_question, build_literature_section, QAResult, LiteratureSection,
)
from neuro_caseboard.literature.config import LiteratureConfig
from neuro_caseboard.literature.retriever import LiteratureRecord
from neuro_caseboard.literature.synth import LiteratureSynthesis


def _query_result():
    return SimpleNamespace(answer="Textbook answer [1].",
                           citations=[SimpleNamespace(n=1, book="Bk", chapter="", page=5)],
                           figures=[])


def test_lane_b_failure_is_additive():
    def lane_a():
        return _query_result()

    def lane_b():
        raise RuntimeError("pubmed down")

    out = answer_question("q", lane_a=lane_a, lane_b=lane_b)
    assert isinstance(out, QAResult)
    assert out.answer == "Textbook answer [1]."
    assert out.literature is None  # never blocks the textbook answer


def test_lane_a_error_propagates():
    def lane_a():
        raise RuntimeError("GPU not ready")

    import pytest
    with pytest.raises(RuntimeError, match="GPU not ready"):
        answer_question("q", lane_a=lane_a, lane_b=lambda: None)


def test_literature_section_is_carried():
    section = LiteratureSection(narrative="Recent RCTs [L1].", citations=[])
    out = answer_question("q", lane_a=_query_result, lane_b=lambda: section)
    assert out.literature is section


def test_build_literature_section_uses_cache_and_synth(tmp_path):
    cfg = LiteratureConfig(enabled=True, recency_years=7, k=5, cache_ttl_days=14,
                           ncbi_api_key="", cache_dir=str(tmp_path))

    class _Cache:
        def __init__(self):
            self.records = [LiteratureRecord(pmid="111", title="T", journal="J",
                            year=2024, doi="d", url="u", abstract="a",
                            sections={}, pub_types=["Review"])]
        def get(self, key):
            return self.records
        def set(self, key, records):
            pass

    class _Synth:
        def generate(self, system, user, images):
            return "Summary [L1]."

    section = build_literature_section("distal MCA occlusion", lit_config=cfg,
                                       cache=_Cache(), synth_client=_Synth())
    assert section is not None
    assert section.narrative == "Summary [L1]."
    assert section.citations[0].pmid == "111"
    assert section.citations[0].n == 1


def test_build_literature_section_disabled_returns_none():
    cfg = LiteratureConfig(enabled=False, recency_years=7, k=5, cache_ttl_days=14,
                           ncbi_api_key="", cache_dir="/tmp/x")
    assert build_literature_section("q", lit_config=cfg) is None


def test_answer_question_routes_to_woven_when_flag_on(monkeypatch):
    monkeypatch.setenv("NEURO_CASEBOARD_SKIP_DOTENV", "1")
    monkeypatch.setenv("LITERATURE_WEAVE", "1")
    import neuro_caseboard.qa as qa
    monkeypatch.setattr(qa, "_answer_question_woven", lambda *a, **k: "WOVEN")
    assert qa.answer_question("q") == "WOVEN"


def test_answer_question_forwards_skip_disambiguation(monkeypatch):
    monkeypatch.setenv("NEURO_CASEBOARD_SKIP_DOTENV", "1")
    monkeypatch.setenv("LITERATURE_WEAVE", "1")
    import neuro_caseboard.qa as qa
    captured = {}

    def _spy(*a, **k):
        captured.update(k)
        return "WOVEN"

    monkeypatch.setattr(qa, "_answer_question_woven", _spy)
    assert qa.answer_question("unilateral FTP rewrite", skip_disambiguation=True) == "WOVEN"
    assert captured.get("skip_disambiguation") is True


def test_answer_question_separate_path_when_flag_off(monkeypatch):
    monkeypatch.setenv("NEURO_CASEBOARD_SKIP_DOTENV", "1")
    monkeypatch.delenv("LITERATURE_WEAVE", raising=False)
    out = answer_question("q", lane_a=_query_result, lane_b=lambda: None)
    assert isinstance(out, QAResult)
    assert out.answer == "Textbook answer [1]."


def test_answer_question_forwards_skip_disambiguation_on_nonwoven_path(monkeypatch):
    # Parity with the woven path: with the weave flag OFF and no lanes injected, the
    # non-woven branch must forward skip_disambiguation through neuro_core.query.query.
    monkeypatch.setenv("NEURO_CASEBOARD_SKIP_DOTENV", "1")
    monkeypatch.delenv("LITERATURE_WEAVE", raising=False)
    import neuro_core.query as ncq
    captured = {}

    def _spy_query(question, *, config=None, force=False, skip_disambiguation=False):
        captured["skip_disambiguation"] = skip_disambiguation
        return _query_result()

    monkeypatch.setattr(ncq, "query", _spy_query)
    out = answer_question("unilateral FTP rewrite", lane_b=lambda: None,
                          skip_disambiguation=True)
    assert isinstance(out, QAResult)
    assert captured.get("skip_disambiguation") is True


def test_answer_question_nonwoven_default_skip_disambiguation_off(monkeypatch):
    # DEFAULT-OFF parity: the flag stays False when not requested (byte-identical default).
    monkeypatch.setenv("NEURO_CASEBOARD_SKIP_DOTENV", "1")
    monkeypatch.delenv("LITERATURE_WEAVE", raising=False)
    import neuro_core.query as ncq
    captured = {}

    def _spy_query(question, *, config=None, force=False, skip_disambiguation=False):
        captured["skip_disambiguation"] = skip_disambiguation
        return _query_result()

    monkeypatch.setattr(ncq, "query", _spy_query)
    answer_question("q", lane_b=lambda: None)
    assert captured.get("skip_disambiguation") is False


def test_retrieve_records_cache_key_includes_recency_boost():
    from neuro_caseboard.qa import retrieve_records

    class _KeyCache:
        def __init__(self):
            self.asked = []
        def get(self, key):
            self.asked.append(key)
            return []  # cache "hit" with empty list -> no network, returns ([], term)
        def set(self, key, records):
            pass

    class _Synth:
        def generate(self, system, user, images):
            return "x"

    def _cfg(boost):
        return LiteratureConfig(enabled=True, recency_years=7, k=5, cache_ttl_days=14,
                                ncbi_api_key="", cache_dir="/tmp/x", weave=True,
                                recency_boost=boost, precision_gate=True, precision_min_overlap=1)

    c0, c1 = _KeyCache(), _KeyCache()
    retrieve_records("distal MCA occlusion", lit_config=_cfg(0), synth_client=_Synth(), cache=c0)
    retrieve_records("distal MCA occlusion", lit_config=_cfg(2), synth_client=_Synth(), cache=c1)
    assert c0.asked and c1.asked
    assert c0.asked[0] != c1.asked[0]  # boost must be part of the key


def test_answer_question_attaches_verification():
    from types import SimpleNamespace
    from neuro_caseboard.qa import answer_question
    qr = SimpleNamespace(answer="The MCA supplies the lateral cortex [1].",
        citations=[SimpleNamespace(n=1, book="Youmans", chapter="", page=5,
                                   text="The MCA supplies the lateral cerebral cortex.")], figures=[])
    out = answer_question("q", lane_a=lambda: qr, lane_b=lambda: None)
    assert out.verification is not None
    assert out.verification.n_cited_claims == 1 and out.verification.n_unsupported == 0


def test_answer_question_verifies_literature_narrative_in_default_path():
    """SHOULD-3: the default (separate) path must verify the literature [L#] narrative,
    not just the textbook [n] answer. A narrative whose [L1] claim is unsupported by the
    cited abstract must be flagged needs-verification and merged into QAResult.verification."""
    from types import SimpleNamespace
    from neuro_caseboard.qa import answer_question, LiteratureSection, LiteratureCitation
    qr = SimpleNamespace(answer="Textbook answer [1].",
                         citations=[SimpleNamespace(n=1, book="Bk", chapter="", page=5)],
                         figures=[])
    # Narrative claim is about thrombectomy; the cited abstract is about the corpus callosum
    # (≥5 content tokens, clearly off-topic) so the LexicalVerifier deterministically rejects.
    section = LiteratureSection(
        narrative="Endovascular thrombectomy improves distal-occlusion outcomes [L1].",
        citations=[LiteratureCitation(
            n=1, pmid="111", title="T", journal="J", year=2024, doi="d", url="u",
            abstract="The corpus callosum is a broad commissural white-matter tract "
                     "connecting the two cerebral hemispheres.")])
    out = answer_question("q", lane_a=lambda: qr, lane_b=lambda: section)
    assert out.verification is not None
    assert out.verification.n_unsupported >= 1
    assert "L1" in out.verification.unsupported_markers()


def test_answer_question_flags_unsupported_textbook_claim():
    """SHOULD-1/2 (separate path): alignment-sensitive — a [1] claim whose cited passage is
    clearly unrelated must be flagged unsupported with the right marker. Guards against a
    premise-map misalignment that the supported-only tests would silently pass."""
    from types import SimpleNamespace
    qr = SimpleNamespace(
        answer="Endovascular thrombectomy improves distal-occlusion outcomes [1].",
        citations=[SimpleNamespace(
            n=1, book="Bk", chapter="", page=5,
            text="The corpus callosum is a broad commissural white-matter tract "
                 "connecting the cerebral hemispheres.")],
        figures=[])
    out = answer_question("q", lane_a=lambda: qr, lane_b=lambda: None)
    assert out.verification.n_unsupported == 1
    assert "1" in out.verification.unsupported_markers()
