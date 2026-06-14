import asyncio

from neuro_caseboard.literature.retriever import (
    LiteratureRecord, LiteratureRetriever, build_query_terms, parse_year, pub_tier,
)


def test_build_query_terms_drops_stopwords_and_punct():
    q = build_query_terms("What is the best first-line for distal MCA occlusion?")
    assert "mca" in q and "occlusion" in q
    assert "the" not in q.split() and "is" not in q.split()


def test_parse_year_and_tier():
    assert parse_year("2024 Mar") == 2024
    assert parse_year("") is None
    assert pub_tier(["Systematic Review"]) < pub_tier(["Randomized Controlled Trial"])
    assert pub_tier(["Randomized Controlled Trial"]) < pub_tier(["Case Reports"])


class _FakeClient:
    async def search(self, query, *, max_results=20, filter_type=None):
        # reviews axis returns 333; primary returns 111,222
        return (["333"], 1) if filter_type == "systematic_review" else (["111", "222"], 2)

    async def summaries(self, pmids):
        rows = {
            "111": {"pmid": "111", "title": "RCT EVT", "source": "Stroke",
                     "pubdate": "2020 Jan", "pub_types": ["Randomized Controlled Trial"],
                     "doi": "10/a", "url": "u111", "authors": "X"},
            "222": {"pmid": "222", "title": "Case report", "source": "Cureus",
                     "pubdate": "2023 Jan", "pub_types": ["Case Reports"],
                     "doi": "", "url": "u222", "authors": "Y"},
            "333": {"pmid": "333", "title": "Meta-analysis EVT", "source": "Lancet",
                     "pubdate": "2022 Jan", "pub_types": ["Meta-Analysis"],
                     "doi": "10/c", "url": "u333", "authors": "Z"},
        }
        return [rows[p] for p in pmids if p in rows]

    async def structured_abstracts(self, pmids):
        return {p: {"RESULTS": f"results {p}"} for p in pmids}

    async def abstracts(self, pmids):
        return {p: f"abstract {p}" for p in pmids}


def test_retrieve_merges_axes_ranks_and_caps():
    r = LiteratureRetriever(_FakeClient(), k=2, recency_years=7)
    recs = asyncio.run(r.retrieve("distal MCA occlusion", current_year=2024))
    assert all(isinstance(x, LiteratureRecord) for x in recs)
    assert len(recs) == 2
    # tier 0 (meta-analysis 333) ranks ahead of RCT (111); case report (222) last/dropped
    assert recs[0].pmid == "333"
    assert "222" not in [x.pmid for x in recs]


def test_records_without_text_are_dropped():
    class NoText(_FakeClient):
        async def structured_abstracts(self, pmids):
            return {}
        async def abstracts(self, pmids):
            return {}
    r = LiteratureRetriever(NoText(), k=5, recency_years=7)
    recs = asyncio.run(r.retrieve("x", current_year=2024))
    assert recs == []
