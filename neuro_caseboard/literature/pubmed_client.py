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
