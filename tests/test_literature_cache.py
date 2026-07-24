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


def test_empty_result_expires_quickly(tmp_path):
    """An empty result must not persist for the full TTL.

    A transient upstream failure (LLM query-rewrite down, NCBI hiccup) yields [] and used to
    be cached for the whole 14 days, so the literature lane stayed silently empty long after
    the cause was fixed. Empty results get a short TTL instead.
    """
    clock = {"t": 1000.0}
    c = LiteratureCache(str(tmp_path), ttl_days=14, now=lambda: clock["t"])
    c.set("k", [])

    assert c.get("k") == []          # still shields NCBI from an immediate re-hit
    clock["t"] += 2 * 3600           # 2 hours later
    assert c.get("k") is None        # ...but re-queries rather than staying empty for weeks


def test_nonempty_result_keeps_the_full_ttl(tmp_path):
    """The short TTL must apply ONLY to empty results, not shorten real cached records."""
    clock = {"t": 1000.0}
    c = LiteratureCache(str(tmp_path), ttl_days=14, now=lambda: clock["t"])
    c.set("k", [_rec("1")])

    clock["t"] += 5 * 86400          # 5 days later, well past the empty-result TTL
    got = c.get("k")

    assert got is not None and got[0].pmid == "1"
