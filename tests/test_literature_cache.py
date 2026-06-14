from neuro_caseboard.literature.cache import LiteratureCache
from neuro_caseboard.literature.retriever import LiteratureRecord


def _rec(pmid):
    return LiteratureRecord(pmid=pmid, title="T", journal="J", year=2024,
                            doi="d", url="u", abstract="a", sections={"RESULTS": "r"},
                            pub_types=["Review"])


def test_set_then_get_roundtrip(tmp_path):
    c = LiteratureCache(str(tmp_path), ttl_days=14)
    c.set("key1", [_rec("111")])
    got = c.get("key1")
    assert got is not None and got[0].pmid == "111"
    assert got[0].sections == {"RESULTS": "r"}


def test_miss_returns_none(tmp_path):
    assert LiteratureCache(str(tmp_path)).get("absent") is None


def test_expired_entry_returns_none(tmp_path):
    clock = {"t": 1000.0}
    c = LiteratureCache(str(tmp_path), ttl_days=1, now=lambda: clock["t"])
    c.set("k", [_rec("1")])
    clock["t"] += 2 * 86400  # 2 days later, ttl is 1 day
    assert c.get("k") is None


def test_corrupt_file_returns_none(tmp_path):
    c = LiteratureCache(str(tmp_path))
    c.set("k", [_rec("1")])
    # Corrupt the stored file
    f = next(tmp_path.glob("*.json"))
    f.write_text("{not json")
    assert c.get("k") is None
