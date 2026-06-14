# PubMed Contemporary-Literature Lane — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an always-on second retrieval lane that, for every Q&A question, produces a separate "Contemporary Literature" section — a synthesized narrative of recent PubMed studies with per-study `[L#]` citations — without touching the textbook answer's grounding.

**Architecture:** Two independent grounded mini-RAGs with disjoint citation namespaces. Lane A is the unchanged `neuro_core.query.query()` (textbook `[n]`/book-page). Lane B is a new `neuro_caseboard/literature/` package (ported caseprep httpx E-utilities client → ranked `LiteratureRecord`s → its own `synthesize_literature()` → `[L#]`/PMID-DOI). A thin `neuro_caseboard/qa.py` orchestrator runs both concurrently and is the new entry point for the CLI, Streamlit app, and PDF export. Lane B is strictly additive: any failure drops the section and never alters Lane A.

**Tech Stack:** Python, `httpx` (async E-utilities), stdlib `xml.etree`/`asyncio`/`concurrent.futures`, existing `neuro_core` synth clients (Vertex/OpenRouter/local), pytest. Spec: `docs/superpowers/specs/2026-06-14-pubmed-literature-lane-design.md`.

---

## File Structure

**Create:**
- `neuro_caseboard/literature/__init__.py` — package exports
- `neuro_caseboard/literature/config.py` — env-driven `LiteratureConfig`
- `neuro_caseboard/literature/pubmed_client.py` — async E-utilities client (ported)
- `neuro_caseboard/literature/retriever.py` — `LiteratureRecord`, query build, ranking, `LiteratureRetriever`
- `neuro_caseboard/literature/cache.py` — `LiteratureCache` (on-disk TTL)
- `neuro_caseboard/literature/synth.py` — `synthesize_literature`, literature refusal
- `neuro_caseboard/qa.py` — `QAResult`/`LiteratureSection`/`LiteratureCitation`, `answer_question`, `build_literature_section`
- Tests: `tests/test_literature_pubmed_client.py`, `tests/test_literature_retriever.py`, `tests/test_literature_cache.py`, `tests/test_literature_synth.py`, `tests/test_qa.py`, `tests/test_briefing_literature.py`

**Modify:**
- `pyproject.toml` — add `httpx` dependency
- `neuro_caseboard/briefing_pdf.py` — render the literature section (duck-typed via `_g`)
- `neuro_caseboard/cli.py` — `_run_ask` uses `answer_question`, prints literature
- `app/streamlit_app.py` — Ask mode uses `answer_question`, renders literature

---

## Task 1: Add httpx dependency

**Files:**
- Modify: `pyproject.toml:13-17` (the `dependencies` array)

- [ ] **Step 1: Add httpx to dependencies**

Change the `dependencies` array to:

```toml
dependencies = [
    "fpdf2>=2.8",
    "pillow>=10.0",
    "pymupdf>=1.23",
    "httpx>=0.27",
]
```

- [ ] **Step 2: Install it**

Run: `pip install -e .`
Expected: completes; `python3 -c "import httpx; print(httpx.__version__)"` prints a version.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add httpx for PubMed E-utilities client"
```

---

## Task 2: Literature config (env reader)

**Files:**
- Create: `neuro_caseboard/literature/__init__.py`
- Create: `neuro_caseboard/literature/config.py`
- Test: `tests/test_literature_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_config.py
import importlib
from neuro_caseboard.literature.config import load_literature_config


def test_defaults_when_env_empty(monkeypatch):
    for k in ("LITERATURE_RETRIEVAL", "LITERATURE_RECENCY_YEARS", "LITERATURE_K",
              "LITERATURE_CACHE_TTL_DAYS", "NCBI_API_KEY", "NCBI_API_KEY_2"):
        monkeypatch.delenv(k, raising=False)
    cfg = load_literature_config()
    assert cfg.enabled is True
    assert cfg.recency_years == 7
    assert cfg.k == 8
    assert cfg.cache_ttl_days == 14
    assert cfg.ncbi_api_key == ""


def test_reads_env_and_key_fallback(monkeypatch):
    monkeypatch.setenv("LITERATURE_RETRIEVAL", "false")
    monkeypatch.setenv("LITERATURE_K", "5")
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    monkeypatch.setenv("NCBI_API_KEY_2", "fallback-key")
    cfg = load_literature_config()
    assert cfg.enabled is False
    assert cfg.k == 5
    assert cfg.ncbi_api_key == "fallback-key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_literature_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'neuro_caseboard.literature'`

- [ ] **Step 3: Create the package and config**

```python
# neuro_caseboard/literature/__init__.py
"""Contemporary-literature (PubMed) lane for caseboard Q&A."""
```

```python
# neuro_caseboard/literature/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _flag(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class LiteratureConfig:
    enabled: bool
    recency_years: int
    k: int
    cache_ttl_days: int
    ncbi_api_key: str
    cache_dir: str


def load_literature_config() -> LiteratureConfig:
    default_cache = str(Path.home() / ".cache" / "neuro_caseboard" / "pubmed")
    return LiteratureConfig(
        enabled=_flag(os.environ.get("LITERATURE_RETRIEVAL", "true")),
        recency_years=int(os.environ.get("LITERATURE_RECENCY_YEARS", "7")),
        k=int(os.environ.get("LITERATURE_K", "8")),
        cache_ttl_days=int(os.environ.get("LITERATURE_CACHE_TTL_DAYS", "14")),
        ncbi_api_key=(os.environ.get("NCBI_API_KEY")
                      or os.environ.get("NCBI_API_KEY_2") or "").strip(),
        cache_dir=os.environ.get("LITERATURE_CACHE_DIR", default_cache),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_literature_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/literature/__init__.py neuro_caseboard/literature/config.py tests/test_literature_config.py
git commit -m "feat(literature): env-driven LiteratureConfig"
```

---

## Task 3: PubMed E-utilities client

Ported from caseprep `mcp_server.py`, refactored into a class with an **injectable async transport** so tests never hit the network.

**Files:**
- Create: `neuro_caseboard/literature/pubmed_client.py`
- Test: `tests/test_literature_pubmed_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_pubmed_client.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_literature_pubmed_client.py -v`
Expected: FAIL with `ModuleNotFoundError: ... pubmed_client`

- [ ] **Step 3: Write the client**

```python
# neuro_caseboard/literature/pubmed_client.py
"""Async PubMed E-utilities client (ported from caseprep mcp_server).

Refactored so the async transport is injectable (constructor `http=`), keeping the
network out of unit tests. Public methods mirror caseprep's `_pubmed_*` helpers.
"""
from __future__ import annotations

import asyncio
import time
import xml.etree.ElementTree as ET

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# PubMed publication-type / clinical-query filters (verbatim from caseprep).
CLINICAL_FILTERS: dict[str, str] = {
    "therapy": (
        " AND (clinical trial[pt] OR randomized controlled trial[pt] "
        "OR comparative study[pt] OR multicenter study[pt])"
    ),
    "prognosis": (
        " AND (prognosis[MeSH] OR survival analysis[MeSH] "
        "OR mortality[MeSH] OR follow-up studies[MeSH] OR outcome*[tiab])"
    ),
    "etiology": (
        " AND (risk[MeSH] OR cohort studies[MeSH] OR case-control studies[MeSH] "
        "OR retrospective studies[MeSH] OR complications[sh])"
    ),
    "diagnosis": (
        " AND (sensitivity and specificity[MeSH] OR diagnosis[sh] "
        "OR diagnostic imaging[MeSH] OR diagnostic use[sh])"
    ),
    "systematic_review": (
        " AND (systematic review[pt] OR meta-analysis[pt] "
        "OR systematic review[tiab] OR meta-analysis[tiab])"
    ),
}


def apply_filter(query: str, filter_type: str | None) -> str:
    ft = (filter_type or "").strip().lower()
    return query + CLINICAL_FILTERS[ft] if ft in CLINICAL_FILTERS else query


def _fmt_authors(authors) -> str:
    names = [a.get("name", "") for a in (authors or [])
             if isinstance(a, dict) and a.get("name")]
    if not names:
        return ""
    return ", ".join(names) if len(names) <= 3 else f"{names[0]} et al."


class PubMedClient:
    def __init__(self, *, api_key: str = "", http=None, delay: float | None = None):
        self._api_key = api_key
        self._http = http
        self._delay = delay if delay is not None else (0.15 if api_key else 0.6)
        self._last = 0.0

    def _transport(self):
        if self._http is None:
            import httpx
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(45.0),
                headers={"User-Agent": "neuro-caseboard/0.1"},
            )
        return self._http

    async def _rate_limit(self):
        if self._delay <= 0:
            return
        wait = self._last + self._delay - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = time.monotonic()

    async def _get(self, url: str, params: dict):
        if self._api_key:
            params["api_key"] = self._api_key
        for attempt in range(3):
            await self._rate_limit()
            resp = await self._transport().get(url, params=params)
            if resp.status_code == 429 and attempt < 2:
                await asyncio.sleep(2.0 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError("NCBI rate limit exceeded after retries")

    async def search(self, query: str, *, max_results: int = 20,
                     filter_type: str | None = None) -> tuple[list[str], int]:
        params = {
            "db": "pubmed", "term": apply_filter(query, filter_type),
            "retmax": str(max_results), "retmode": "xml", "sort": "relevance",
        }
        resp = await self._get(f"{EUTILS}/esearch.fcgi", params)
        root = ET.fromstring(resp.text)
        total = int(root.findtext(".//Count") or "0")
        pmids = [e.text or "" for e in root.findall(".//Id") if e.text]
        return pmids, total

    async def summaries(self, pmids: list[str]) -> list[dict]:
        if not pmids:
            return []
        params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
        resp = await self._get(f"{EUTILS}/esummary.fcgi", params)
        data = resp.json()
        out = []
        for pmid in pmids:
            a = data.get("result", {}).get(pmid, {})
            if not a or "uid" not in a:
                continue
            pub_types = a.get("pubtype", [])
            if isinstance(pub_types, str):
                pub_types = [pub_types]
            eloc = a.get("elocationid", "") or ""
            out.append({
                "pmid": a.get("uid", ""),
                "title": a.get("title", ""),
                "authors": _fmt_authors(a.get("authors", [])),
                "source": a.get("source", ""),
                "pubdate": a.get("pubdate", ""),
                "pub_types": pub_types,
                "doi": eloc.replace("doi: ", "") if eloc else "",
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{a.get('uid', '')}/",
            })
        return out

    async def structured_abstracts(self, pmids: list[str]) -> dict[str, dict[str, str]]:
        if not pmids:
            return {}
        params = {"db": "pubmed", "id": ",".join(pmids),
                  "retmode": "xml", "rettype": "abstract"}
        resp = await self._get(f"{EUTILS}/efetch.fcgi", params)
        root = ET.fromstring(resp.text)
        results: dict[str, dict[str, str]] = {}
        for article in root.findall(".//PubmedArticle"):
            pmid_el = article.find(".//PMID")
            pmid = pmid_el.text if pmid_el is not None else ""
            if not pmid:
                continue
            sections: dict[str, str] = {}
            for at in article.findall(".//Abstract/AbstractText"):
                label = (at.get("Label") or "").upper().rstrip(":")
                text = at.text or ""
                for child in at:
                    if child.text:
                        text += child.text
                    if child.tail:
                        text += child.tail
                if text.strip():
                    key = label if label else "TEXT"
                    sections[key] = sections.get(key, "") + text.strip() + " "
            if sections:
                results[pmid] = {k: v.strip() for k, v in sections.items()}
        return results

    async def abstracts(self, pmids: list[str]) -> dict[str, str]:
        if not pmids:
            return {}
        params = {"db": "pubmed", "id": ",".join(pmids),
                  "retmode": "xml", "rettype": "abstract"}
        resp = await self._get(f"{EUTILS}/efetch.fcgi", params)
        root = ET.fromstring(resp.text)
        out: dict[str, str] = {}
        for article in root.findall(".//PubmedArticle"):
            pmid_el = article.find(".//PMID")
            ab_el = article.find(".//Abstract/AbstractText")
            pmid = pmid_el.text if pmid_el is not None else ""
            text = ab_el.text if ab_el is not None else ""
            if pmid and text:
                out[pmid] = text
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_literature_pubmed_client.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/literature/pubmed_client.py tests/test_literature_pubmed_client.py
git commit -m "feat(literature): async PubMed E-utilities client (ported, injectable transport)"
```

---

## Task 4: LiteratureRecord, query build, ranking, retriever

**Files:**
- Create: `neuro_caseboard/literature/retriever.py`
- Test: `tests/test_literature_retriever.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_retriever.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_literature_retriever.py -v`
Expected: FAIL with `ModuleNotFoundError: ... retriever`

- [ ] **Step 3: Write the retriever**

```python
# neuro_caseboard/literature/retriever.py
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field

_STOP = {
    "the", "and", "for", "with", "this", "that", "from", "are", "any", "its",
    "what", "which", "when", "best", "first", "line", "is", "of", "to", "in",
    "on", "at", "be", "a", "an", "or", "vs", "how", "do", "does", "can",
}

# Lower tier = higher evidence quality (sorted ascending).
_TIER = [
    (0, ("systematic review", "meta-analysis", "meta analysis", "practice guideline", "guideline")),
    (1, ("randomized controlled trial", "clinical trial", "multicenter study")),
    (2, ("comparative study", "observational study", "cohort", "review")),
    (4, ("case reports", "case report", "editorial", "comment", "letter")),
]


@dataclass
class LiteratureRecord:
    pmid: str
    title: str
    journal: str
    year: int | None
    doi: str
    url: str
    abstract: str
    sections: dict = field(default_factory=dict)
    pub_types: list = field(default_factory=list)


def build_query_terms(question: str, *, max_terms: int = 10) -> str:
    terms: list[str] = []
    for tok in re.findall(r"[A-Za-z0-9]+", (question or "").lower()):
        if len(tok) < 3 or tok in _STOP or tok in terms:
            continue
        terms.append(tok)
        if len(terms) >= max_terms:
            break
    return " ".join(terms)


def parse_year(pubdate: str) -> int | None:
    m = re.search(r"(19|20)\d\d", pubdate or "")
    return int(m.group(0)) if m else None


def pub_tier(pub_types) -> int:
    joined = " ".join(pub_types or []).lower()
    for tier, needles in _TIER:
        if any(n in joined for n in needles):
            return tier
    return 3


def _to_record(summary: dict, sections: dict, plains: dict) -> LiteratureRecord:
    pmid = str(summary.get("pmid") or "")
    return LiteratureRecord(
        pmid=pmid,
        title=summary.get("title", "") or "",
        journal=summary.get("source", "") or "",
        year=parse_year(summary.get("pubdate", "")),
        doi=summary.get("doi", "") or "",
        url=summary.get("url", "") or "",
        abstract=plains.get(pmid, "") or "",
        sections=sections.get(pmid, {}) or {},
        pub_types=summary.get("pub_types", []) or [],
    )


class LiteratureRetriever:
    """question -> ranked LiteratureRecords. `client` is any object exposing the
    PubMedClient async methods (search/summaries/structured_abstracts/abstracts)."""

    def __init__(self, client, *, k: int = 8, recency_years: int = 7):
        self._client = client
        self._k = k
        self._recency_years = recency_years

    async def retrieve(self, question: str, *, candidates: int = 20,
                       current_year: int | None = None) -> list[LiteratureRecord]:
        current_year = current_year or _dt.date.today().year
        term = build_query_terms(question)
        axes = [(term, None), (term, "systematic_review")]
        pmids: list[str] = []
        seen: set[str] = set()
        for q, ft in axes:
            ids, _ = await self._client.search(q, max_results=candidates, filter_type=ft)
            for pid in ids:
                if pid and pid not in seen:
                    seen.add(pid)
                    pmids.append(pid)
        pmids = pmids[:candidates]
        summaries = await self._client.summaries(pmids)
        sections = await self._client.structured_abstracts(pmids)
        plains = await self._client.abstracts(pmids)
        records = [_to_record(s, sections, plains) for s in summaries]
        records = [r for r in records if r.abstract or r.sections]

        def rank_key(r: LiteratureRecord):
            recent = 0 if (r.year and current_year - r.year <= self._recency_years) else 1
            return (pub_tier(r.pub_types), recent, -(r.year or 0))

        records.sort(key=rank_key)
        return records[:self._k]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_literature_retriever.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/literature/retriever.py tests/test_literature_retriever.py
git commit -m "feat(literature): LiteratureRecord + quality/recency-ranked retriever"
```

---

## Task 5: On-disk TTL cache

**Files:**
- Create: `neuro_caseboard/literature/cache.py`
- Test: `tests/test_literature_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_cache.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_literature_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: ... cache`

- [ ] **Step 3: Write the cache**

```python
# neuro_caseboard/literature/cache.py
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from .retriever import LiteratureRecord


class LiteratureCache:
    """On-disk TTL cache of retrieved records (the rate-limited network step)."""

    def __init__(self, cache_dir: str, *, ttl_days: int = 14, now=time.time):
        self._dir = Path(cache_dir)
        self._ttl = ttl_days * 86400
        self._now = now

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._dir / f"{digest}.json"

    def get(self, key: str) -> list[LiteratureRecord] | None:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            blob = json.loads(p.read_text())
        except Exception:
            return None
        if self._now() - blob.get("ts", 0) > self._ttl:
            return None
        try:
            return [LiteratureRecord(**r) for r in blob.get("records", [])]
        except Exception:
            return None

    def set(self, key: str, records: list[LiteratureRecord]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        payload = {"ts": self._now(), "records": [asdict(r) for r in records]}
        self._path(key).write_text(json.dumps(payload))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_literature_cache.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/literature/cache.py tests/test_literature_cache.py
git commit -m "feat(literature): on-disk TTL cache for retrieved records"
```

---

## Task 6: Literature synthesis (grounded narrative)

**Files:**
- Create: `neuro_caseboard/literature/synth.py`
- Test: `tests/test_literature_synth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_literature_synth.py
from neuro_caseboard.literature.synth import (
    synthesize_literature, is_lit_refusal, LIT_REFUSAL,
)
from neuro_caseboard.literature.retriever import LiteratureRecord


def _rec(pmid, title):
    return LiteratureRecord(pmid=pmid, title=title, journal="Stroke", year=2024,
                            doi="d", url="u", abstract=f"abstract {pmid}",
                            sections={}, pub_types=["Review"])


class _FakeSynth:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def generate(self, system, user, images):
        self.calls.append((system, user, images))
        return self.reply


def test_synthesizes_narrative_and_keeps_records():
    sc = _FakeSynth("EVT has expanded to distal vessels [L1]. Bridging shifts [L2].")
    out = synthesize_literature("distal MCA", [_rec("1", "A"), _rec("2", "B")], sc)
    assert out is not None
    assert "[L1]" in out.narrative
    assert [r.pmid for r in out.records] == ["1", "2"]
    # text-only: images must be empty, and each study appears in the prompt
    assert sc.calls[0][2] == []
    assert "[L1]" in sc.calls[0][1] and "abstract 1" in sc.calls[0][1]


def test_refusal_reply_yields_none():
    sc = _FakeSynth(LIT_REFUSAL)
    assert synthesize_literature("q", [_rec("1", "A")], sc) is None


def test_empty_records_yields_none():
    sc = _FakeSynth("anything")
    assert synthesize_literature("q", [], sc) is None
    assert sc.calls == []  # no model call when there is nothing to synthesize


def test_is_lit_refusal_normalizes():
    assert is_lit_refusal("  No relevant recent literature found.  ")
    assert not is_lit_refusal("Recent RCTs show...")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_literature_synth.py -v`
Expected: FAIL with `ModuleNotFoundError: ... synth`

- [ ] **Step 3: Write the synthesis module**

```python
# neuro_caseboard/literature/synth.py
from __future__ import annotations

from dataclasses import dataclass, field

LIT_REFUSAL = "No relevant recent literature found."

LIT_SYSTEM = (
    "You are a neurosurgical evidence summarizer. Using ONLY the numbered studies "
    "provided, write a compressed but readable narrative summary of the contemporary "
    "literature relevant to the question. Rules:\n"
    "- Cite the bracketed study number for every claim, e.g. [L2]. Never invent a "
    "citation number that is not in the list.\n"
    "- Synthesize across studies into flowing prose (a short paragraph or two), not a "
    "bullet list of isolated facts; note agreement, disagreement, and recency.\n"
    "- Do not use any knowledge beyond the provided studies. Do not restate the "
    "textbook answer.\n"
    f"- If none of the studies are relevant to the question, reply exactly "
    f"\"{LIT_REFUSAL}\"\n"
    "- Be clinically precise. This is decision-support, not clinical judgment."
)


def is_lit_refusal(text: str) -> bool:
    def norm(s: str) -> str:
        return (s or "").strip().rstrip(".").strip().casefold()
    return norm(text) == norm(LIT_REFUSAL)


@dataclass
class LiteratureSynthesis:
    narrative: str
    records: list = field(default_factory=list)


def _format_studies(records) -> str:
    blocks = []
    for i, r in enumerate(records, 1):
        body = r.abstract or " ".join(f"{k}: {v}" for k, v in (r.sections or {}).items())
        head = f"[L{i}] {r.title} — {r.journal} {r.year or ''} (PMID {r.pmid})"
        blocks.append(f"{head}\n{body}")
    return "\n\n".join(blocks)


def synthesize_literature(question, records, synth_client):
    """Grounded narrative over PubMed abstracts. Returns None on empty input or refusal."""
    if not records:
        return None
    user = f"Question: {question}\n\nStudies:\n{_format_studies(records)}"
    narrative = synth_client.generate(LIT_SYSTEM, user, [])
    if not narrative or is_lit_refusal(narrative):
        return None
    return LiteratureSynthesis(narrative=narrative, records=list(records))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_literature_synth.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/literature/synth.py tests/test_literature_synth.py
git commit -m "feat(literature): grounded narrative synthesis with refusal"
```

---

## Task 7: Orchestrator (`qa.py`)

**Files:**
- Create: `neuro_caseboard/qa.py`
- Test: `tests/test_qa.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_qa.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_qa.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'neuro_caseboard.qa'`

- [ ] **Step 3: Write the orchestrator**

```python
# neuro_caseboard/qa.py
"""Q&A orchestrator: textbook lane (A) + contemporary-literature lane (B), concurrent.

Lane B is strictly additive — any failure yields literature=None and never blocks or
alters Lane A's grounded answer.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field


@dataclass
class LiteratureCitation:
    n: int
    pmid: str
    title: str
    journal: str
    year: int | None
    doi: str
    url: str


@dataclass
class LiteratureSection:
    narrative: str
    citations: list = field(default_factory=list)


@dataclass
class QAResult:
    answer: str
    citations: list = field(default_factory=list)
    figures: list = field(default_factory=list)
    literature: "LiteratureSection | None" = None


def build_literature_section(question, *, config=None, lit_config=None,
                             client=None, synth_client=None, cache=None):
    """Run Lane B end to end. Returns a LiteratureSection or None (disabled/empty/error)."""
    from neuro_caseboard.literature.config import load_literature_config
    from neuro_caseboard.literature.retriever import LiteratureRetriever, build_query_terms
    from neuro_caseboard.literature.synth import synthesize_literature

    lit_config = lit_config or load_literature_config()
    if not lit_config.enabled:
        return None
    try:
        if cache is None:
            from neuro_caseboard.literature.cache import LiteratureCache
            cache = LiteratureCache(lit_config.cache_dir, ttl_days=lit_config.cache_ttl_days)
        term = build_query_terms(question)
        key = f"{term}|{lit_config.k}|{lit_config.recency_years}"
        records = cache.get(key)
        if records is None:
            if client is None:
                from neuro_caseboard.literature.pubmed_client import PubMedClient
                client = PubMedClient(api_key=lit_config.ncbi_api_key)
            retriever = LiteratureRetriever(client, k=lit_config.k,
                                            recency_years=lit_config.recency_years)
            records = asyncio.run(retriever.retrieve(question))
            cache.set(key, records)
        if not records:
            return None
        if synth_client is None:
            from neuro_core.config import load_config
            from neuro_core.synth_clients import make_synth_client
            synth_client = make_synth_client(config or load_config())
        syn = synthesize_literature(question, records, synth_client)
        if syn is None:
            return None
        cites = [LiteratureCitation(n=i, pmid=r.pmid, title=r.title, journal=r.journal,
                                    year=r.year, doi=r.doi, url=r.url)
                 for i, r in enumerate(syn.records, 1)]
        return LiteratureSection(narrative=syn.narrative, citations=cites)
    except Exception:
        return None


def answer_question(question, *, config=None, force=False, lane_a=None, lane_b=None) -> QAResult:
    """Run Lane A and Lane B concurrently. Lane A errors propagate; Lane B failures drop
    the section. `lane_a`/`lane_b` are injectable no-arg callables (for tests)."""
    if lane_a is None:
        from neuro_core.query import query
        def lane_a():
            return query(question, config=config, force=force)
    if lane_b is None:
        def lane_b():
            return build_literature_section(question, config=config)

    with ThreadPoolExecutor(max_workers=2) as ex:
        fa = ex.submit(lane_a)
        fb = ex.submit(lane_b)
        qr = fa.result()  # propagate Lane A errors (e.g. GpuNotReadyError)
        try:
            lit = fb.result()
        except Exception:
            lit = None
    return QAResult(answer=qr.answer, citations=qr.citations,
                    figures=qr.figures, literature=lit)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_qa.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/qa.py tests/test_qa.py
git commit -m "feat(qa): concurrent textbook+literature orchestrator (additive Lane B)"
```

---

## Task 8: Render the literature section in the PDF

**Files:**
- Modify: `neuro_caseboard/briefing_pdf.py` (add `_literature_html`, extend `build_briefing_html`, add CSS)
- Test: `tests/test_briefing_literature.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_briefing_literature.py
from types import SimpleNamespace

from neuro_caseboard.briefing_pdf import build_briefing_html


def _lit():
    cite = SimpleNamespace(n=1, pmid="111", title="Tenecteplase before EVT",
                           journal="Stroke", year=2024, doi="10.1161/abc",
                           url="https://pubmed.ncbi.nlm.nih.gov/111/")
    return SimpleNamespace(narrative="Recent RCTs expand EVT to distal vessels [L1].",
                           citations=[cite])


def _result(literature=None):
    return SimpleNamespace(answer="Answer [1].",
                           citations=[SimpleNamespace(n=1, book="Bk", chapter="", page=3)],
                           figures=[], literature=literature)


def test_literature_section_rendered_when_present():
    html = build_briefing_html(_result(_lit()), title="Q")
    assert "Contemporary Literature" in html
    assert "[L1]" in html
    assert "Tenecteplase before EVT" in html
    assert "https://doi.org/10.1161/abc" in html  # DOI link preferred


def test_no_literature_section_when_absent():
    html = build_briefing_html(_result(None), title="Q")
    assert "Contemporary Literature" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_briefing_literature.py -v`
Expected: FAIL — `AssertionError: 'Contemporary Literature' not in html`

- [ ] **Step 3: Add CSS for literature links**

In `neuro_caseboard/briefing_pdf.py`, inside the `SIGNAL_CSS` string, append after the `.src .n` rule (around line 68):

```css
.src .ln{color:#67e8f9;font-weight:600;font-family:"JetBrains Mono",ui-monospace,monospace;}
.src a{color:#22d3ee;text-decoration:none;}
.litmeta{color:#cbd5e1;}
```

- [ ] **Step 4: Add the literature renderer**

In `neuro_caseboard/briefing_pdf.py`, add this function after `_md_to_html` (after line 110):

```python
def _literature_html(result) -> str:
    """Render the Contemporary Literature section, or '' when absent/empty."""
    lit = _g(result, "literature")
    if not lit:
        return ""
    narrative = _g(lit, "narrative") or ""
    cites = _g(lit, "citations") or []
    if not narrative or not cites:
        return ""
    rows = []
    for c in cites:
        doi = _g(c, "doi") or ""
        href = f"https://doi.org/{doi}" if doi else (_g(c, "url") or "")
        meta = ", ".join(p for p in (html.escape(_g(c, "journal") or ""),
                                     str(_g(c, "year") or "")) if p)
        link = f' · <a href="{html.escape(href)}">link</a>' if href else ""
        rows.append(
            f'<div class="src"><span class="ln">[L{_g(c, "n")}]</span> '
            f'{html.escape(_g(c, "title") or "")} '
            f'<span class="litmeta">— {meta}</span>{link}</div>')
    return ("<h2>Contemporary Literature</h2>"
            + _md_to_html(narrative)
            + f'<div class="sources">{"".join(rows)}</div>')
```

- [ ] **Step 5: Insert it into `build_briefing_html`**

In `build_briefing_html`, change the return concatenation (the `+ "\n".join(figs)` tail around line 150) to insert literature after the Sources block and before figures:

```python
        + answer
        + "<h2>Sources</h2>"
        + f'<div class="sources">{sources}</div>'
        + _literature_html(result)
        + "\n".join(figs)
        + "</body></html>")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_briefing_literature.py tests/test_briefing_pdf.py -v`
Expected: PASS (new tests pass; existing briefing tests still pass)

- [ ] **Step 7: Commit**

```bash
git add neuro_caseboard/briefing_pdf.py tests/test_briefing_literature.py
git commit -m "feat(briefing): render Contemporary Literature section ([L#] + DOI links)"
```

---

## Task 9: Wire the CLI

**Files:**
- Modify: `neuro_caseboard/cli.py:11-28` (`_run_ask`)
- Test: `tests/test_cli_literature.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_literature.py
from types import SimpleNamespace

import neuro_caseboard.cli as cli


def test_run_ask_prints_literature(monkeypatch, capsys):
    lit = SimpleNamespace(
        narrative="Recent RCTs expand EVT [L1].",
        citations=[SimpleNamespace(n=1, pmid="111", title="EVT RCT", journal="Stroke",
                                   year=2024, doi="10/x",
                                   url="https://pubmed.ncbi.nlm.nih.gov/111/")])
    result = SimpleNamespace(answer="Textbook answer [1].",
                             citations=[SimpleNamespace(n=1, book="Bk", chapter="", page=5)],
                             figures=[], literature=lit)
    monkeypatch.setattr(cli, "_answer_question", lambda q, force=False: result, raising=False)
    rc = cli._run_ask(SimpleNamespace(question="q", force=False))
    out = capsys.readouterr().out
    assert rc == 0
    assert "Textbook answer" in out
    assert "Contemporary Literature" in out
    assert "[L1]" in out and "EVT RCT" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_literature.py -v`
Expected: FAIL (AttributeError or missing literature output)

- [ ] **Step 3: Update `_run_ask`**

Replace `neuro_caseboard/cli.py` lines 11-28 (`_run_ask`) with:

```python
def _answer_question(question, force=False):
    from neuro_caseboard.qa import answer_question
    return answer_question(question, force=force)


def _run_ask(args) -> int:
    from neuro_core.gpu_guard import GpuNotReadyError
    try:
        result = _answer_question(args.question, force=args.force)
    except GpuNotReadyError as e:
        print(f"GPU not ready: {e}", file=sys.stderr)
        return 1
    print(result.answer)
    print("\nSources:")
    for c in result.citations:
        loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
        print(f"  [{c.n}] {loc}")
    lit = getattr(result, "literature", None)
    if lit and lit.narrative:
        print("\nContemporary Literature:")
        print(lit.narrative)
        for c in lit.citations:
            link = f"https://doi.org/{c.doi}" if c.doi else c.url
            print(f"  [L{c.n}] {c.title} — {c.journal} {c.year or ''} · {link}")
    if result.figures:
        print("\nFigures:")
        for f in result.figures:
            print(f"  [{f.source_n}] {f.book}, p.{f.page} -> {f.image_path}")
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli_literature.py tests/test_cli.py -v`
Expected: PASS (new test passes; existing CLI tests still pass)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/cli.py tests/test_cli_literature.py
git commit -m "feat(cli): ask command emits Contemporary Literature via answer_question"
```

---

## Task 10: Wire the Streamlit app

**Files:**
- Modify: `app/streamlit_app.py:16` (import) and `:57-75` (Ask branch render)

No unit test (Streamlit UI). Verify by import-compile + manual smoke.

- [ ] **Step 1: Swap the import**

In `app/streamlit_app.py`, change line 16:

```python
from neuro_core.query import query
```
to:
```python
from neuro_caseboard.qa import answer_question
```

- [ ] **Step 2: Use `answer_question` and render literature**

Replace the Ask-branch body (lines 57-75, from `if q:` through the Sources loop) with:

```python
    if q:
        with st.spinner("Searching textbooks + recent literature..."):
            result = answer_question(q)
        label = f'answer: "{q}"'
        record(_store, [from_figure(f) for f in result.figures], label)
        st.markdown(result.answer)
        if result.figures:
            st.subheader("Figures")
            cols = st.columns(min(3, len(result.figures)))
            for col, f in zip(cols, result.figures):
                with col:
                    st.image(f.image_path,
                             caption=f"[{f.source_n}] {f.book}, p.{f.page} — {f.caption}",
                             use_container_width=True)
                    _badge(from_figure(f).key, label)
        st.subheader("Sources")
        for c in result.citations:
            loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
            st.write(f"[{c.n}] {loc}")
        if result.literature and result.literature.narrative:
            st.subheader("Contemporary Literature")
            st.markdown(result.literature.narrative)
            for lc in result.literature.citations:
                link = f"https://doi.org/{lc.doi}" if lc.doi else lc.url
                st.markdown(f"[L{lc.n}] {lc.title} — *{lc.journal}* {lc.year or ''} · [{link}]({link})")
```

- [ ] **Step 3: Verify it compiles**

Run: `python3 -m py_compile app/streamlit_app.py`
Expected: no output (exit 0)

- [ ] **Step 4: Commit**

```bash
git add app/streamlit_app.py
git commit -m "feat(app): Ask mode shows Contemporary Literature via answer_question"
```

---

## Task 11: Live smoke test (opt-in) + full suite + docs

**Files:**
- Create: `tests/test_literature_live.py`
- Modify: `README.md` (document the lane + env flags)

- [ ] **Step 1: Write the opt-in live smoke test**

```python
# tests/test_literature_live.py
import asyncio
import os

import pytest

from neuro_caseboard.literature.pubmed_client import PubMedClient

pytestmark = pytest.mark.skipif(
    not (os.environ.get("NCBI_API_KEY") or os.environ.get("NCBI_API_KEY_2")),
    reason="no NCBI key in env; live PubMed smoke test skipped",
)


def test_live_search_returns_pmids():
    key = os.environ.get("NCBI_API_KEY") or os.environ.get("NCBI_API_KEY_2")
    client = PubMedClient(api_key=key)
    pmids, total = asyncio.run(
        client.search("mechanical thrombectomy large vessel occlusion", max_results=5))
    assert pmids and total > 0
```

- [ ] **Step 2: Run it (skips without a key)**

Run: `pytest tests/test_literature_live.py -v`
Expected: SKIPPED (no key) or PASS (key present)

- [ ] **Step 3: Document in README**

Add a short subsection to `README.md` under the Q&A/ask docs:

```markdown
### Contemporary Literature (PubMed)

Every `ask` answer is augmented with a synthesized "Contemporary Literature"
section from PubMed (separate `[L#]` / PMID-DOI citations; the textbook answer is
unchanged). Set `NCBI_API_KEY` (or `NCBI_API_KEY_2`) for the higher rate limit.

Env flags: `LITERATURE_RETRIEVAL` (default on), `LITERATURE_RECENCY_YEARS` (7),
`LITERATURE_K` (8), `LITERATURE_CACHE_TTL_DAYS` (14), `LITERATURE_CACHE_DIR`.
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all pass (live test skipped without a key). Investigate any failure before committing.

- [ ] **Step 5: Commit**

```bash
git add tests/test_literature_live.py README.md
git commit -m "test(literature): opt-in live PubMed smoke test + docs"
```

---

## Self-Review (completed during planning)

- **Spec coverage:** §2 architecture → Tasks 7,9,10; §3 components → Tasks 2–7; §4 query/filters → Task 4 (`build_query_terms`, axes, `pub_tier`, recency in `rank_key`); §5 grounding/namespace → Tasks 6,8 (`[L#]`, DOI links); §6 error handling/cache/config → Tasks 2,5,7 (additive `try/except`, TTL cache); §7 surfaces → Tasks 8,9,10; §8 testing → every task + Task 11 live test.
- **Type consistency:** `PubMedClient.search/summaries/structured_abstracts/abstracts` signatures are identical in Tasks 3,4,7 and the fakes. `LiteratureRecord` fields match across retriever/cache/synth/qa. `LiteratureSection(narrative, citations)` and `LiteratureCitation(n,pmid,title,journal,year,doi,url)` are produced in Task 7 and consumed identically in Tasks 8,9,10. `build_literature_section`/`answer_question` keyword args match their tests.
- **Placeholder scan:** none — every code/test step contains complete code.

## Execution Handoff

(See options after the plan is reviewed.)
