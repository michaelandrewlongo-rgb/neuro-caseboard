import asyncio

from neuro_caseboard.literature.pubmed_client import (
    PubMedClient, apply_filter, CLINICAL_FILTERS,
)

ESEARCH_XML = """<?xml version="1.0"?>
<eSearchResult><Count>42</Count><IdList>
<Id>111</Id><Id>222</Id></IdList></eSearchResult>"""

ESUMMARY_JSON = {
    "result": {
        "111": {"uid": "111", "title": "Tenecteplase before EVT",
                 "authors": [{"name": "Smith J"}, {"name": "Doe A"}],
                 "source": "Stroke", "pubdate": "2024 Mar",
                 "pubtype": ["Randomized Controlled Trial"],
                 "elocationid": "doi: 10.1161/abc"},
    }
}

EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet><PubmedArticle><MedlineCitation>
<PMID>111</PMID><Article><Abstract>
<AbstractText Label="BACKGROUND">BG text.</AbstractText>
<AbstractText Label="RESULTS">RS text.</AbstractText>
</Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""


class _FakeResp:
    def __init__(self, *, text="", json_data=None, status=200):
        self.text = text
        self._json = json_data
        self.status_code = status

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHttp:
    """Routes by URL substring; records calls."""
    def __init__(self):
        self.calls = []

    async def get(self, url, params=None):
        self.calls.append((url, params))
        if "esearch" in url:
            return _FakeResp(text=ESEARCH_XML)
        if "esummary" in url:
            return _FakeResp(json_data=ESUMMARY_JSON)
        if "efetch" in url:
            return _FakeResp(text=EFETCH_XML)
        raise AssertionError(url)


def test_apply_filter_appends_systematic_review():
    out = apply_filter("mca occlusion", "systematic_review")
    assert out.startswith("mca occlusion")
    assert "systematic review[pt]" in out
    assert apply_filter("x", None) == "x"
    assert apply_filter("x", "bogus") == "x"


def test_search_parses_pmids_and_total():
    c = PubMedClient(api_key="k", http=_FakeHttp(), delay=0)
    pmids, total = asyncio.run(c.search("mca", max_results=10))
    assert pmids == ["111", "222"]
    assert total == 42


def test_summaries_normalizes_fields():
    c = PubMedClient(api_key="", http=_FakeHttp(), delay=0)
    rows = asyncio.run(c.summaries(["111"]))
    assert rows[0]["pmid"] == "111"
    assert rows[0]["doi"] == "10.1161/abc"
    assert rows[0]["pub_types"] == ["Randomized Controlled Trial"]
    assert rows[0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/111/"


def test_structured_abstracts_sections():
    c = PubMedClient(api_key="", http=_FakeHttp(), delay=0)
    sections = asyncio.run(c.structured_abstracts(["111"]))
    assert sections["111"]["BACKGROUND"] == "BG text."
    assert sections["111"]["RESULTS"] == "RS text."


def test_api_key_injected_into_params():
    http = _FakeHttp()
    c = PubMedClient(api_key="secret", http=http, delay=0)
    asyncio.run(c.search("q"))
    assert http.calls[0][1]["api_key"] == "secret"


def test_summaries_rejects_non_doi_elocationid():
    import asyncio
    class _Http(_FakeHttp):
        async def get(self, url, params=None):
            self.calls.append((url, params))
            if "esummary" in url:
                return _FakeResp(json_data={"result": {"111": {
                    "uid": "111", "title": "T", "authors": [], "source": "J",
                    "pubdate": "2024", "pubtype": ["Review"],
                    "elocationid": "pii: S0140-6736(23)01234-5"}}})
            return await super().get(url, params)
    rows = asyncio.run(PubMedClient(http=_Http(), delay=0).summaries(["111"]))
    assert rows[0]["doi"] == ""   # non-DOI elocationid is not stored as a DOI


def test_aclose_closes_transport():
    import asyncio
    class _Closeable(_FakeHttp):
        closed = False
        async def aclose(self):
            self.closed = True
    h = _Closeable()
    c = PubMedClient(http=h, delay=0)
    asyncio.run(c.aclose())
    assert h.closed is True
