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
