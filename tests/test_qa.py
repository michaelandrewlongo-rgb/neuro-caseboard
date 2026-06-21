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


def _two_record_cache(tmp_path):
    cfg = LiteratureConfig(enabled=True, recency_years=7, k=5, cache_ttl_days=14,
                           ncbi_api_key="", cache_dir=str(tmp_path))

    class _Cache:
        def __init__(self):
            self.records = [
                LiteratureRecord(pmid="111", title="T1", journal="J", year=2024, doi="d1",
                                 url="u1", abstract="a", sections={}, pub_types=["Review"]),
                LiteratureRecord(pmid="222", title="T2", journal="J", year=2024, doi="d2",
                                 url="u2", abstract="a", sections={}, pub_types=["Review"])]

        def get(self, key):
            return self.records

        def set(self, key, records):
            pass

    return cfg, _Cache()


def test_build_literature_section_cites_only_used_records(tmp_path):
    # Two studies fed to synthesis; narrative cites ONLY [L2]. The off-topic [L1] must NOT
    # appear as a citation, and the used study keeps its original marker number (2).
    cfg, cache = _two_record_cache(tmp_path)

    class _Synth:
        def generate(self, system, user, images):
            return "Only the second study is relevant here [L2]."

    section = build_literature_section("q", lit_config=cfg, cache=cache, synth_client=_Synth())
    assert section is not None
    assert [c.n for c in section.citations] == [2]
    assert [c.pmid for c in section.citations] == ["222"]


def test_build_literature_section_drops_lane_when_nothing_cited(tmp_path):
    # An ungrounded narrative (no [L#] markers) must not attach fabricated authority.
    cfg, cache = _two_record_cache(tmp_path)

    class _Synth:
        def generate(self, system, user, images):
            return "Contemporary practice has evolved considerably in recent years."

    assert build_literature_section("q", lit_config=cfg, cache=cache, synth_client=_Synth()) is None
