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

# Papers within the same relevance bucket are reordered by quality/recency; papers in
# a more-relevant bucket always outrank a less-relevant one (relevance gates selection).
_RELEVANCE_BUCKET = 5


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


PUBMED_QUERY_SYSTEM = (
    "Convert the clinician's question into a concise PubMed search query. Output ONLY "
    "the query string on a single line, with no preamble, label, or explanation.\n"
    "- Use the core clinical entities: disease/condition, anatomy, and intervention.\n"
    "- Prefer 2-4 concepts joined with AND; use quoted phrases for multi-word terms and "
    "OR for synonyms/abbreviations, e.g. (\"middle meningeal artery\" OR MMA).\n"
    "- DROP narrative/process words that over-constrain recall (e.g. 'resolution', "
    "'time course', 'rate', 'outcome', 'best', 'management') unless that word IS the "
    "core concept of the question.\n"
    "- Do NOT add PubMed field tags ([tiab], [pt]), date filters, or publication-type "
    "filters; the pipeline adds those separately."
)


def rewrite_pubmed_query(question: str, synth_client) -> str | None:
    """Use the LLM to turn a natural-language question into a focused PubMed query.

    Returns a cleaned single-line query, or None on any failure/empty output so the
    caller can fall back to ``build_query_terms`` (keeping already-correct behavior).
    """
    try:
        out = synth_client.generate(PUBMED_QUERY_SYSTEM, f"Question: {question}", [])
    except Exception:
        return None
    if not out:
        return None
    # Take the first non-empty line, strip surrounding quotes/whitespace.
    for line in out.splitlines():
        cleaned = line.strip().strip("`").strip()
        if cleaned.lower().startswith("query:"):
            cleaned = cleaned[6:].strip()
        if cleaned:
            return cleaned
    return None


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

    async def retrieve(self, question: str, *, candidates: int = 40,
                       current_year: int | None = None,
                       query: str | None = None) -> list[LiteratureRecord]:
        current_year = current_year or _dt.date.today().year
        # A focused PubMed query (e.g. from rewrite_pubmed_query) wins; otherwise fall
        # back to the token-dump of the whole question. The latter AND-conjuncts every
        # word at PubMed, which tanks recall on natural-language questions.
        term = query or build_query_terms(question)
        # Fan out across clinical question types (plan B.1) so the pool covers therapy,
        # evidence syntheses, etiology/risk, diagnosis and prognosis — not just the plain
        # query + systematic reviews. Filters refine by pub-type/MeSH WITHIN the same topic
        # query (CLINICAL_FILTERS), so this broadens recall without drifting off topic;
        # pmids are deduped and relevance still gates final selection below.
        axes = [
            (term, None),
            (term, "systematic_review"),
            (term, "etiology"),
            (term, "diagnosis"),
            (term, "prognosis"),
        ]
        pmids: list[str] = []
        seen: set[str] = set()
        for q, ft in axes:
            ids, _ = await self._client.search(q, max_results=candidates, filter_type=ft)
            for pid in ids:
                if pid and pid not in seen:
                    seen.add(pid)
                    pmids.append(pid)
        pmids = pmids[:candidates]
        # PubMed already returned these sorted by relevance (esearch sort=relevance);
        # keep that as the primary signal so the metadata sort below can't bury the
        # most on-topic paper under an older systematic review.
        rank_of = {pid: i for i, pid in enumerate(pmids)}
        summaries = await self._client.summaries(pmids)
        sections = await self._client.structured_abstracts(pmids)
        plains = await self._client.abstracts(pmids)
        records = [_to_record(s, sections, plains) for s in summaries]
        records = [r for r in records if r.abstract or r.sections]

        def rank_key(r: LiteratureRecord):
            # Bucket by relevance, then prefer evidence quality + recency WITHIN a bucket:
            # relevance gates selection; tier/recency only reorder similarly-relevant papers.
            bucket = rank_of.get(r.pmid, len(pmids)) // _RELEVANCE_BUCKET
            recent = 0 if (r.year and current_year - r.year <= self._recency_years) else 1
            return (bucket, pub_tier(r.pub_types), recent, -(r.year or 0))

        records.sort(key=rank_key)
        return records[:self._k]
