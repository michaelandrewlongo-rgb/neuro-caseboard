"""MCP server for caseprep — PubMed-powered case preparation.

Tools:
  search_pubmed      — search with clinical query filters, optional abstracts
  build_caseplan     — run 4 targeted searches, pull abstracts, write filled-in templates
  generate_caseprep  — static template folder (quick scaffold)
  search_local_pdfs  — PyMuPDF local PDF search
  get_fulltext       — 3-tier best-available content for a PMID
  search_radiology   — search Open-i for radiology images (MRI, CT, X-ray)
  send_email         — send email via Resend REST API
"""

from __future__ import annotations

import asyncio
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from caseprep.generator import generate_caseprep as _generate_caseprep
from caseprep.links import build_search_links
from caseprep.pdfs import format_pdf_results, search_local_pdfs as _search_local_pdfs

# ── Load .env file ───────────────────────────────────────────────────────────

import os
from pathlib import Path as _Path

_ENV_FILE = _Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                os.environ.setdefault(_key.strip(), _val.strip())

# Also load Hermes .env as fallback (for OPENROUTER_API_KEY etc.)
_HERMES_ENV = _Path.home() / ".hermes" / ".env"
if _HERMES_ENV.exists():
    with open(_HERMES_ENV) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                os.environ.setdefault(_key.strip(), _val.strip())

# ── NCBI API key ────────────────────────────────────────────────────────────

_NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "").strip()
_DELAY = 0.15 if _NCBI_API_KEY else 0.6  # 10/sec with key, ~1.5/sec without

# ── Resend email API ─────────────────────────────────────────────────────────

_RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_API = "https://api.resend.com"
RESEND_DEFAULT_FROM = "CasePrep <onboarding@resend.dev>"

# ── HTTP client ─────────────────────────────────────────────────────────────

_http: httpx.AsyncClient | None = None

def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            timeout=httpx.Timeout(45.0),
            headers={"User-Agent": "caseprep-mcp/0.2 (hermes-agent)"},
        )
    return _http

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
OPENI = "https://openi.nlm.nih.gov/api"

# ── Open-i radiology image type codes ────────────────────────────────────────
# Codes are loosely tagged; prefer "x" (general radiology) as default.
OPENI_MODALITY: dict[str, str] = {
    "any": "x",         # all radiology (MRI/CT/X-ray/ultrasound)
    "mri": "m",         # MRI
    "ct": "c",          # CT
    "xray": "x",        # general x-ray / radiology
    "ultrasound": "u",  # ultrasound
    "graph": "g",       # charts / graphs (non-radiology fallback)
}

STOP_WORDS: set[str] = {
    "and", "or", "not", "the", "a", "an", "in", "of", "for",
    "with", "to", "from", "by", "on", "at", "is", "are",
    "was", "were", "be", "been", "being",
}


def _query_terms(query: str) -> list[str]:
    """Extract meaningful search terms from a query string.

    Splits on whitespace, punctuation, and hyphens; removes stop words
    and tokens shorter than 2 chars. Each term is lowercased and deduplicated.
    """
    tokens = re.split(r'[\s,"\':;()\[\]{}-]+', query.lower())
    seen: set[str] = set()
    terms: list[str] = []
    for t in tokens:
        t = t.strip(".")
        if len(t) >= 2 and t not in STOP_WORDS and t not in seen:
            seen.add(t)
            terms.append(t)
    return terms


# ── Clinical query filters (PubMed syntax) ──────────────────────────────────

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


def _apply_filter(query: str, filter_type: str | None) -> str:
    """Append a clinical query filter to the PubMed query string."""
    ft = (filter_type or "").strip().lower()
    if ft in CLINICAL_FILTERS:
        return query + CLINICAL_FILTERS[ft]
    return query


# ── Rate limiter (NCBI: 3 req/sec without API key) ───────────────────────────

_last_request: float = 0.0


async def _rate_limit():
    """Enforce delay between NCBI requests."""
    global _last_request
    now = time.monotonic()
    wait = _last_request + _DELAY - now
    if wait > 0:
        await asyncio.sleep(wait)
    _last_request = time.monotonic()


async def _ncbi_get(url: str, params: dict) -> httpx.Response:
    """GET with API key injection, rate limiting, and retry on 429."""
    if _NCBI_API_KEY:
        params["api_key"] = _NCBI_API_KEY
    for attempt in range(3):
        await _rate_limit()
        resp = await _client().get(url, params=params)
        if resp.status_code == 429 and attempt < 2:
            await asyncio.sleep(2.0 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError("NCBI rate limit exceeded after retries")


# ── PubMed API helpers ──────────────────────────────────────────────────────

async def _pubmed_search(
    query: str,
    max_results: int = 10,
    filter_type: str | None = None,
) -> list[str]:
    """Return PMIDs matching *query*, optionally filtered by clinical type."""
    term = _apply_filter(query, filter_type)
    params = {
        "db": "pubmed",
        "term": term,
        "retmax": str(max_results),
        "retmode": "xml",
        "sort": "relevance",
    }
    resp = await _ncbi_get(f"{EUTILS}/esearch.fcgi", params)
    root = ET.fromstring(resp.text)
    total = root.findtext(".//Count") or "0"
    pmids = [e.text or "" for e in root.findall(".//Id") if e.text]
    # Attach total count as a pseudo-attribute on first element
    return pmids, int(total)


async def _pubmed_summaries(pmids: list[str]) -> list[dict]:
    """Fetch structured summaries (title, authors, journal, etc.) for PMIDs."""
    if not pmids:
        return []
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
    resp = await _ncbi_get(f"{EUTILS}/esummary.fcgi", params)
    data = resp.json()
    results = []
    for pmid in pmids:
        a = data.get("result", {}).get(pmid, {})
        if not a or "uid" not in a:
            continue
        results.append({
            "pmid": a.get("uid", ""),
            "title": a.get("title", ""),
            "authors": _fmt_authors(a.get("authors", [])),
            "source": a.get("source", ""),
            "pubdate": a.get("pubdate", ""),
            "doi": a.get("elocationid", "").replace("doi: ", "")
                   if a.get("elocationid", "") else "",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{a.get('uid', '')}/",
        })
    return results


async def _pubmed_abstracts(pmids: list[str]) -> dict[str, str]:
    """Fetch plain-text abstracts for PMIDs. Returns dict[pmid → abstract_text]."""
    if not pmids:
        return {}
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "rettype": "abstract",
    }
    resp = await _ncbi_get(f"{EUTILS}/efetch.fcgi", params)
    root = ET.fromstring(resp.text)
    abstracts = {}
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        abstract_el = article.find(".//Abstract/AbstractText")
        pmid = pmid_el.text if pmid_el is not None else ""
        text = abstract_el.text if abstract_el is not None else ""
        if pmid and text:
            abstracts[pmid] = text
    return abstracts


async def _pubmed_structured_abstracts(pmids: list[str]) -> dict[str, dict[str, str]]:
    """Fetch structured abstracts with labeled sections for PMIDs.

    Returns dict[pmid → {label: text}] where labels are BACKGROUND, METHODS,
    RESULTS, CONCLUSIONS, or empty string for unlabeled paragraphs.
    Works for JAMA, NEJM, Lancet, Neurology — even without PMC access.
    """
    if not pmids:
        return {}
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "rettype": "abstract",
    }
    resp = await _ncbi_get(f"{EUTILS}/efetch.fcgi", params)
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
            # Also collect text from child elements (some abstracts have inline markup)
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


async def _pubmed_fulltext(pmids: list[str]) -> dict[str, str]:
    """Fetch PMC full text via curl subprocess with retry.

    Three attempts per article, exponential backoff, ."""
    if not pmids:
        return {}
    # Step 1: get PMCIDs via elink
    params = {
        "dbfrom": "pubmed", "db": "pmc", "id": ",".join(pmids),
        "retmode": "xml", "linkname": "pubmed_pmc",
    }
    try:
        resp = await _ncbi_get(f"{EUTILS}/elink.fcgi", params)
        root = ET.fromstring(resp.text)
    except Exception:
        return {}
    pmid_to_pmcid: dict[str, str] = {}
    for link_set in root.findall(".//LinkSet"):
        pmid_el = link_set.find(".//Id")
        if pmid_el is None or not pmid_el.text:
            continue
        for link in link_set.findall(".//Link/Id"):
            if link.text:
                link_id = link.text
                if not link_id.startswith("PMC"):
                    link_id = "PMC" + link_id
                pmid_to_pmcid[pmid_el.text] = link_id
                break
    if not pmid_to_pmcid:
        return {}
    # Step 2: fetch via curl with retry
    fulltexts: dict[str, str] = {}
    api_key_param = f"&api_key={_NCBI_API_KEY}" if _NCBI_API_KEY else ""
    for pmid, pmcid in pmid_to_pmcid.items():
        url = f"{EUTILS}/efetch.fcgi?db=pmc&id={pmcid}&retmode=xml{api_key_param}"
        for attempt in range(3):
            proc = await asyncio.create_subprocess_exec(
                "curl", "-sS", "--max-time", "45", "--retry", "2", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0 or not stdout:
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
                continue
            try:
                root = ET.fromstring(stdout.decode("utf-8", errors="replace"))
                for article in root.findall(".//article"):
                    body = article.find(".//body")
                    if body is not None:
                        text = ET.tostring(body, encoding="unicode", method="text")
                        # Clean excessive whitespace
                        text = " ".join(text.split())
                        fulltexts[pmid] = text[:5000]
                        break
                break  # success, stop retrying
            except ET.ParseError:
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
                continue
    return fulltexts


# ── Open-i radiology image search ────────────────────────────────────────────

async def _openi_search(
    query: str,
    max_results: int = 5,
    modality: str | None = None,
    query_terms: list[str] | None = None,
) -> tuple[list[dict], int]:
    """Search Open-i for radiology images. Returns (results, total_count).

    Each result: uid, pmid, pmcid, title, journal, authors, pubdate,
    caption (cleaned), img_thumb, img_large, img_grid, pmc_url, pubmed_url,
    article_type.

    If *query_terms* is provided, results are post-filtered — only images
    whose title or caption contains at least one query term are returned.
    Fetches more results from Open-i (up to 20) to compensate for filtering.
    """
    it_code = OPENI_MODALITY.get((modality or "").strip().lower(), "x")
    # Fetch more from Open-i to compensate for post-filtering
    fetch_n = min(max(max_results * 4, 10), 20)
    params = {
        "query": query,
        "it": it_code,
        "m": 1,
        "n": str(fetch_n),
    }
    try:
        resp = await _client().get(f"{OPENI}/search", params=params)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        msg = str(exc)[:200]
        print(f"  [Open-i API error: {msg}]", file=__import__("sys").stderr)
        return [], 0

    total = int(data.get("total", 0))
    results: list[dict] = []
    for item in data.get("list", []):
        img = item.get("image", {})
        caption_raw = img.get("caption", "")
        # Strip HTML bold tags from captions
        caption_clean = caption_raw.replace("<b>", "").replace("</b>", "").replace("\\/", "/")
        title = item.get("title", "")

        # Post-filter by relevance: require title or caption to contain a query term
        if query_terms:
            title_lower = title.lower()
            caption_lower = caption_clean.lower()
            if not any(
                term in title_lower or term in caption_lower
                for term in query_terms
            ):
                continue

        journal_date = item.get("journal_date", {})
        pubdate = f"{journal_date.get('year','')}-{journal_date.get('month','')}-{journal_date.get('day','')}"
        pubdate = pubdate.strip("-")
        # Image URLs are top-level fields on the item (not inside 'image' dict)
        thumb = item.get("imgThumb", "") or ""
        large = item.get("imgLarge", "") or ""
        grid = item.get("imgGrid150", "") or ""
        results.append({
            "uid": item.get("uid", ""),
            "pmid": item.get("pmid", ""),
            "pmcid": item.get("pmcid", ""),
            "title": title,
            "journal": item.get("journal_title", "") or item.get("journal_abbr", ""),
            "authors": item.get("authors", ""),
            "pubdate": pubdate,
            "caption": caption_clean,
            "img_thumb": f"https://openi.nlm.nih.gov{thumb}" if thumb else "",
            "img_large": f"https://openi.nlm.nih.gov{large}" if large else "",
            "img_grid": f"https://openi.nlm.nih.gov{grid}" if grid else "",
            "pmc_url": item.get("pmc_url", ""),
            "pubmed_url": item.get("pubMed_url", ""),
            "article_type": item.get("articleType", ""),
        })
        if len(results) >= max_results:
            break
    return results, total


async def _download_images(
    results: list[dict],
    output_dir: Path,
    max_images: int = 5,
) -> list[dict]:
    """Download radiology images from Open-i and add local_path to each result.

    Tries img_large first, falls back to img_grid, then img_thumb.
    Saves files as <nn>_<uid>.<ext> in *output_dir*.
    Errors are captured in local_path as "Error: …" strings.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(results[:max_images]):
        img_url = r["img_large"] or r["img_grid"] or r["img_thumb"]
        if not img_url:
            r["local_path"] = "Error: no image URL"
            continue
        try:
            resp = await _client().get(img_url)
            resp.raise_for_status()
            # Determine extension from content-type header
            ct = resp.headers.get("content-type", "")
            if "jpeg" in ct or "jpg" in ct:
                ext = ".jpg"
            elif "png" in ct:
                ext = ".png"
            elif img_url.lower().endswith(".png"):
                ext = ".png"
            else:
                ext = ".jpg"
            filename = f"{i + 1:02d}_{r['uid']}{ext}"
            filepath = output_dir / filename
            filepath.write_bytes(resp.content)
            r["local_path"] = str(filepath.resolve())
        except Exception as exc:
            r["local_path"] = f"Error: {exc}"
    return results


def _fmt_authors(authors: list[dict]) -> str:
    names = [a.get("name", "") for a in authors[:5]]
    suffix = " et al." if len(authors) > 5 else ""
    return ", ".join(names) + suffix


# ── Formatters ──────────────────────────────────────────────────────────────

def _fmt_paper(
    paper: dict,
    num: int,
    *,
    abstract: str | None = None,
    structured: dict[str, str] | None = None,
    fulltext: str | None = None,
) -> list[str]:
    """Format a paper with best-available content.

    Precedence: structured abstract sections > plain abstract > nothing.
    PMC full text appended separately when available.
    """
    lines = [
        f"{num}. **{paper['title']}**",
        f"   {paper['authors']}",
        f"   *{paper['source']}* ({paper['pubdate']})",
    ]
    if paper["doi"]:
        lines.append(f"   DOI: {paper['doi']}")
    lines.append(f"   {paper['url']}")

    # Show structured abstract sections (best quality)
    if structured:
        for label in ("BACKGROUND", "METHODS", "RESULTS", "CONCLUSIONS"):
            if label in structured:
                text = structured[label]
                if len(text) > 400:
                    text = text[:400] + "…"
                lines.append(f"   {label.title()}: {text}")
    elif abstract:
        ab = abstract[:500] + ("…" if len(abstract) > 500 else "")
        lines.append(f"   Abstract: {ab}")

    if fulltext:
        ft = fulltext[:1000] + ("…" if len(fulltext) > 1000 else "")
        lines.append(f"   PMC: {ft}")

    lines.append("")
    return lines


# ── MCP Server ──────────────────────────────────────────────────────────────

server = Server("caseprep-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_pubmed",
            description=(
                "Search PubMed via NCBI E-utilities API with optional clinical query "
                "filters and abstract fetching. Returns title, authors, journal, date, "
                "DOI, and direct link. Optionally includes full abstract text. "
                "Supports clinical filters: therapy, prognosis, etiology, diagnosis, "
                "systematic_review."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "PubMed search query (supports full PubMed syntax)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results (default: 10, max: 20)",
                        "default": 10,
                    },
                    "filter_type": {
                        "type": "string",
                        "description": (
                            "Clinical query filter: therapy, prognosis, etiology, "
                            "diagnosis, systematic_review. Omit for unfiltered search."
                        ),
                        "enum": ["therapy", "prognosis", "etiology", "diagnosis", "systematic_review"],
                    },
                    "include_abstracts": {
                        "type": "boolean",
                        "description": "Include abstract text for each result (default: false)",
                        "default": False,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="build_caseplan",
            description=(
                "Run 4 targeted PubMed searches for a neurosurgical topic, fetch "
                "abstracts for the top results, and write a filled-in case prep folder. "
                "Searches cover: outcomes/therapy, surgical technique, complications, "
                "and landmark/systematic reviews. Returns organized findings and writes "
                "completed templates to disk."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The case or procedure (e.g., 'retrosigmoid vestibular schwannoma')",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (default: {slug}-caseprep/)",
                    },
                    "max_per_category": {
                        "type": "integer",
                        "description": "Max papers per search category (default: 3, max: 5)",
                        "default": 3,
                    },
                },
                "required": ["topic"],
            },
        ),
        Tool(
            name="generate_caseprep",
            description=(
                "Generate a blank (fill-in-the-blanks) structured case-prep folder "
                "with Markdown templates and a resource-links.html file."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Case or topic"},
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (default: {slug}-caseprep/)",
                    },
                },
                "required": ["topic"],
            },
        ),
        Tool(
            name="get_fulltext",
            description=(
                "Fetch the best available full content for a specific PMID. "
                "Tries three tiers: (1) PMC full text via curl, "
                "(2) structured abstract sections (BACKGROUND/METHODS/RESULTS/CONCLUSIONS), "
                "(3) plain abstract text. Returns whatever tier succeeds."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pmid": {
                        "type": "string",
                        "description": "PubMed ID to fetch full text for",
                    },
                },
                "required": ["pmid"],
            },
        ),
        Tool(
            name="search_local_pdfs",
            description=(
                "Search a directory of local PDF files for topic matches using PyMuPDF. "
                "Returns filename matches and text snippets from first 3 pages."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to search for"},
                    "pdf_dir": {"type": "string", "description": "Directory with PDFs"},
                },
                "required": ["topic", "pdf_dir"],
            },
        ),
        Tool(
            name="search_radiology",
            description=(
                "Search Open-i (NIH) for radiology images — MRI, CT, X-ray, ultrasound — "
                "from PubMed Central articles. Images are downloaded to disk as PNG/JPEG "
                "by default (set download_images=false to skip). Results are filtered for "
                "relevance: title or caption must contain at least one query term. "
                "Filter by modality: any (default), mri, ct, xray, ultrasound."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'vestibular schwannoma MRI CPA angle')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum image results (default: 5, max: 10)",
                        "default": 5,
                    },
                    "modality": {
                        "type": "string",
                        "description": (
                            "Image modality filter: any (all radiology, default), "
                            "mri, ct, xray, ultrasound"
                        ),
                        "enum": ["any", "mri", "ct", "xray", "ultrasound"],
                    },
                    "download_images": {
                        "type": "boolean",
                        "description": (
                            "Download images to disk as PNG/JPEG (default: true). "
                            "Set false to return URLs only."
                        ),
                        "default": True,
                    },
                    "output_dir": {
                        "type": "string",
                        "description": (
                            "Directory to save downloaded images. Default: "
                            "<query>-images/ in the current working directory."
                        ),
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="send_email",
            description=(
                "Send an email via Resend REST API. Requires RESEND_API_KEY in environment. "
                "Supports plain text body. Default sender: CasePrep <onboarding@resend.dev>. "
                "Returns the Resend email ID on success."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line",
                    },
                    "body": {
                        "type": "string",
                        "description": "Plain text email body",
                    },
                    "from_": {
                        "type": "string",
                        "description": (
                            "Sender address. Default: CasePrep <onboarding@resend.dev>. "
                            "Custom domains must be verified in Resend dashboard."
                        ),
                    },
                },
                "required": ["to", "subject", "body"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        match name:
            case "search_pubmed":
                result = await _handle_pubmed(arguments)
            case "build_caseplan":
                result = await _handle_build_caseplan(arguments)
            case "generate_caseprep":
                result = _handle_generate(arguments)
            case "search_local_pdfs":
                result = _handle_pdfs(arguments)
            case "get_fulltext":
                result = await _handle_get_fulltext(arguments)
            case "search_radiology":
                result = await _handle_radiology(arguments)
            case "send_email":
                result = await _handle_send_email(arguments)
            case _:
                result = f"Unknown tool: {name}"
        return [TextContent(type="text", text=result)]
    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


# ── Tool handlers ───────────────────────────────────────────────────────────

async def _handle_pubmed(args: dict) -> str:
    query = args["query"]
    max_results = min(args.get("max_results", 10), 20)
    filter_type = args.get("filter_type")
    include_abstracts = args.get("include_abstracts", False)

    pmids, total = await _pubmed_search(query, max_results, filter_type)
    if not pmids:
        filter_note = f" (filter: {filter_type})" if filter_type else ""
        return f"No PubMed results for: {query}{filter_note}"

    articles = await _pubmed_summaries(pmids[:max_results])

    abstracts = {}
    if include_abstracts:
        abstracts = await _pubmed_abstracts([a["pmid"] for a in articles])

    filter_note = f" — filter: {filter_type}" if filter_type else ""
    lines = [
        f"## PubMed{filter_note} — {query}",
        f"({len(articles)} shown of {total} total)\n",
    ]
    for i, a in enumerate(articles, 1):
        lines.extend(_fmt_paper(a, i, abstract=abstracts.get(a["pmid"])))

    return "\n".join(lines)


async def _handle_build_caseplan(args: dict) -> str:
    topic = args["topic"]
    max_per = min(args.get("max_per_category", 5), 10)
    slug = topic.strip().lower().replace(" ", "-")
    out_dir = Path(args.get("output_dir", "") or f"{slug}-caseprep")
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Define the 4 search axes ────────────────────────────────────────
    searches: list[tuple[str, str, str | None]] = [
        # (label, query suffix, filter_type)
        ("Outcomes / Evidence", f"{topic} outcomes", "therapy"),
        ("Surgical Technique", f"{topic} surgical technique approach", None),
        ("Complications", f"{topic} complications adverse", "etiology"),
        ("Reviews / Landmarks", topic, "systematic_review"),
    ]

    lines = [f"# Case Plan — {topic}\n"]
    all_articles: list[dict] = []
    axis_data: dict[str, list[dict]] = {}

    for label, query, filt in searches:
        lines.append(f"## {label}\n")

        pmids, total = await _pubmed_search(query, max_per, filt)
        if not pmids:
            lines.append(f"  No results ({total} total in PubMed).\n")
            axis_data[label] = []
            continue

        articles = await _pubmed_summaries(pmids[:max_per])
        abstracts = await _pubmed_abstracts([a["pmid"] for a in articles])
        structured = await _pubmed_structured_abstracts([a["pmid"] for a in articles])
        all_articles.extend(articles)

        # Store enriched articles for template population
        enriched = []
        for a in articles:
            entry = dict(a)
            entry["_abstract"] = abstracts.get(a["pmid"], "")
            entry["_structured"] = structured.get(a["pmid"], {})
            enriched.append(entry)
        axis_data[label] = enriched

        lines.append(f"  ({len(articles)} shown of {total} total)\n")
        for i, a in enumerate(articles, 1):
            lines.extend(_fmt_paper(
                a, i,
                abstract=abstracts.get(a["pmid"]),
                structured=structured.get(a["pmid"]),
            ))

    # Fetch PMC full text for all papers
    if all_articles:
        fulltexts = await _pubmed_fulltext([a["pmid"] for a in all_articles])
        if fulltexts:
            lines.append("\n## PMC Full Text Available\n")
            for pmid, ft in fulltexts.items():
                lines.append(f"  PMID {pmid}: {len(ft)} chars\n")
                lines.append(f"  {ft[:800]}…\n")

    summary = "\n".join(lines)

    # ── Write filled-in templates to disk ───────────────────────────────
    await _write_filled_templates(out_dir, topic, summary, axis_data)

    links = build_search_links(topic)
    resource_path = out_dir / "resource-links.html"
    resource_path.write_text(_resource_html(topic, links), encoding="utf-8")

    return f"{summary}\n\n---\nCase plan written to {out_dir.resolve()}/"


# ── Template population: domain-aware keyword extraction ──────────────────
#
# Each domain profile has keyword lists tailored to specific neurosurgical
# subspecialties. The pipeline auto-detects the best profile from the topic
# string. Profiles are additive — base keywords apply to all, profile-specific
# keywords are merged on top.

# Base keywords — always included regardless of profile
_BASE_ANATOMY = [
    "anatomy", "anatomic", "structure", "nerve", "artery", "vein",
    "nucleus", "tract", "cortex", "lobe", "foramen", "fissure",
    "sulcus", "gyrus", "ventricle", "cistern",
]
_BASE_APPROACH = [
    "approach", "technique", "positioning", "craniotomy", "incision",
    "resection", "dissection", "exposure", "retraction",
    "microsurgical", "endoscopic", "minimally invasive",
    "monitoring", "neuromonitoring", "intraoperative",
    "neuronavigation", "bone flap", "dura", "closure", "hemostasis",
]
_BASE_COMPLICATIONS = [
    "complication", "risk", "mortality", "morbidity", "deficit",
    "infection", "meningitis", "hematoma", "hemorrhage", "ischemia",
    "infarction", "edema", "seizure", "hydrocephalus",
    "thromboembolism", "rate", "%", "percent", "incidence", "n=",
]

# Domain profiles — merged with base keywords
_DOMAIN_PROFILES: dict[str, dict[str, list[str]]] = {
    "skull_base": {
        "anatomy": [
            "cranial nerve", "cn vii", "cn viii", "cn v", "cn ix", "cn x",
            "brainstem", "cerebell", "temporal bone", "sigmoid", "petrous",
            "cavernous", "sella", "clivus", "jugular", "meckel", "cpa",
            "cerebellopontine", "internal acoustic", "geniculate",
            "sphenoid", "petroclival", "tentorium",
        ],
        "approach": [
            "retrosigmoid", "translabyrinthine", "middle fossa",
            "transpetrosal", "presigmoid", "drilling",
            "ssep", "mep", "emg", "baer", "facial nerve monitor",
            "keyhole", "endonasal", "transsphenoidal",
        ],
        "complications": [
            "cerebrospinal fluid leak", "csf leak", "facial nerve",
            "hearing loss", "anosmia", "diplopia", "dysphagia",
            "aspiration", "hoarseness", "dvt", "pe",
        ],
    },
    "supratentorial_tumor": {
        "anatomy": [
            "eloquent", "frontal", "temporal", "parietal", "occipital",
            "broca", "wernicke", "supplementary motor", "sma", "insula",
            "corpus callosum", "basal ganglia", "thalamus",
            "white matter", "corticospinal", "arcuate", "precentral",
            "postcentral", "language", "motor cortex", "sensory",
            "visual cortex", "optic radiation", "internal capsule",
        ],
        "approach": [
            "awake craniotomy", "asleep", "frameless", "stereotactic",
            "neuronavigation", "intraoperative mri", "fluorescence",
            "5-ala", "aminolevulinic", "mapping", "cortical mapping",
            "subcortical", "des", "direct electrical stimulation",
            "keyhole", "tubular", "ssep", "mep", "emg",
        ],
        "complications": [
            "aphasia", "dysphasia", "hemiparesis", "visual field",
            "neglect", "cognitive", "personality", "mood",
            "wound", "dehiscence", "pseudomeningocele",
        ],
    },
    "vascular": {
        # Derived from Neurointerventional Evidence Taxonomy (7-axis faceted system).
        # Axis 2 (Vascular Territory) + Axis 3 (Pathology) → anatomy keywords.
        # Axis 4 (Procedure/Technique) → approach keywords.
        # Axis 7 (Outcome Domain, complication subtree) → complications keywords.
        "anatomy": [
            # ── Vascular territories (Axis 2) ──
            "aca", "a1", "a2", "pericallosal", "distal aca",
            "mca", "m1", "m2", "m3", "m4",
            "ica", "cavernous", "petrous", "paraophthalmic", "terminus", "bifurcation",
            "pcom", "anterior choroidal",
            "anterior circulation", "anterior perforators",
            "vertebral", "v1", "v2", "v3", "v4",
            "basilar", "mid basilar", "distal basilar",
            "pca", "p1", "p2",
            "pica", "aica", "sca", "cerebellar",
            "posterior circulation",
            "acom", "lenticulostriate", "perforators",
            # ── Venous (Axis 2) ──
            "superior sagittal sinus", "transverse sinus", "sigmoid sinus",
            "straight sinus", "torcula", "cavernous sinus", "jugular bulb",
            "internal cerebral veins", "vein of galen", "basal veins of rosenthal",
            "cortical veins", "dural sinuses",
            # ── Extracranial / spinal (Axis 2) ──
            "common carotid", "brachiocephalic", "subclavian",
            "extracranial carotid", "vertebral origin",
            "radicular arteries", "segmental arteries",
            # ── Pathology (Axis 3) ──
            "aneurysm", "saccular", "sidewall", "fusiform", "dolichoectatic",
            "blister", "dissecting", "mycotic", "traumatic pseudoaneurysm",
            "avm", "arteriovenous malformation", "compact", "diffuse",
            "spetzler-martin grade", "lawton-young supplementary grade",
            "davf", "borden i", "borden ii", "borden iii",
            "cognard i-iia", "cognard iib", "cognard iii-iv",
            "ccf", "barrow a", "barrow b", "barrow c", "barrow d",
            "atherosclerotic stenosis", "intracranial stenosis", "icad",
            "acute occlusion", "cardioembolic", "cryptogenic", "esus",
            "arterial dissection", "tandem occlusion",
            "vasospasm", "post-asah", "rcvs",
            "sinus thrombosis", "sinus stenosis", "venous sinus atresia",
            "cavernous malformation", "developmental venous anomaly",
            "capillary telangiectasia", "sinus pericranii",
            "hemorrhage", "sah", "ich", "ivh", "csdh", "subarachnoid",
            "tumor", "meningioma", "glomus tumor", "paraganglioma",
            "hemangioblastoma", "hemangiopericytoma", "metastasis",
            "juvenile nasopharyngeal angiofibroma",
            "flow-related", "with intranidal aneurysm", "ruptured vs unruptured",
            # ── Access / traversal terms (surgical context) ──
            "sylvian", "interhemispheric", "pterional", "transsylvian",
        ],
        "approach": [
            # ── Aneurysm treatment (Axis 4) ──
            "primary coiling", "coiling", "balloon-assisted coiling",
            "stent-assisted coiling", "jailing", "coil-through-stent",
            "y-stenting", "flow diversion", "telescoping",
            "intrasaccular flow disruption", "parent vessel sacrifice",
            "with adjunctive coiling",
            # ── Thrombectomy (Axis 4) ──
            "mechanical thrombectomy", "aspiration alone",
            "stent retriever alone", "contact aspiration",
            # ── AVM/dAVF/embolization (Axis 4) ──
            "avm embolization", "davf embolization", "tumor embolization",
            "mma embolization", "epistaxis embolization",
            "transarterial", "transvenous", "combined transarterial + transvenous",
            "direct puncture", "liquid embolic", "coils",
            "preoperative devascularization", "preradiosurgical",
            "staged", "multi-session",
            # ── Carotid / stenting (Axis 4) ──
            "carotid revascularization", "transfemoral cas", "transcarotid",
            "intracranial stenting", "angioplasty", "angioplasty + stenting",
            "balloon angioplasty alone", "drug-coated balloon angioplasty",
            "self-expanding", "balloon-expandable",
            "with distal embolic protection", "with proximal protection",
            "flow reversal",
            # ── Access / closure (Axis 4) ──
            "transfemoral", "transradial", "transulnar", "direct carotid",
            "closure device", "closure",
            # ── Venous / spinal / diagnostic (Axis 4) ──
            "venous sinus stenting", "venous thrombectomy", "venous manometry",
            "venous interventions", "thrombolysis",
            "spinal angiography", "spinal avm embolization", "spinal davf embolization",
            "diagnostic angiography", "4-vessel cerebral angiogram",
            "selective catheterization", "provocative testing",
            "balloon test occlusion",
            # ── Surgical open-vascular (surgeon's terms, not taxonomy) ──
            "clipping", "bypass", "ec-ic", "temporary clip",
            "burst suppression", "adenosine", "indocyanine", "icg",
            "doppler", "microdoppler", "orbitozygomatic", "far lateral",
            "subtemporal", "supraorbital",
        ],
        "complications": [
            # ── Hemorrhagic (Axis 7) ──
            "sich", "parenchymal hematoma", "sah",
            "access site hematoma", "retroperitoneal hematoma",
            "hemorrhage", "rebleed", "rebleed rate", "delayed rupture",
            # ── Ischemic (Axis 7) ──
            "territorial infarct", "perforator infarct", "distal emboli",
            "vasospasm", "delayed cerebral ischemia", "dci",
            # ── Device-related (Axis 7) ──
            "thrombosis", "in-stent stenosis", "in-stent restenosis",
            "migration", "fracture", "malapposition",
            "braid deformation", "foreshortening", "fish-mouthing",
            "wall apposition",
            # ── Access site (Axis 7) ──
            "pseudoaneurysm", "dissection", "radial artery occlusion",
            "access site",
            # ── Contrast / systemic (Axis 7) ──
            "contrast-induced nephropathy", "allergic reaction",
            "infection", "cranial neuropathy", "seizure",
            # ── Outcomes / grading (Axis 7) ──
            "mrs 0-2", "mrs 0-1", "mrs at 90 days", "mrs at discharge",
            "mrs shift", "mtici 2b", "mtici 2c", "mtici 3",
            "first-pass effect", "reperfusion",
            "nihss change", "barthel index", "cognitive outcomes",
            "mortality", "30-day", "90-day", "in-hospital",
            "aneurysm occlusion", "class i", "class ii", "class iiia",
            "aneurysm recanalization", "retreatment rate", "regrowth",
            "obliteration rate",
            "complication rate", "complications",
            # ── Disease-specific (Axis 7) ──
            "hydrocephalus", "shunt", "csf",
            "seizure freedom", "papilledema grade",
            "visual acuity", "visual field",
            "pulsatile tinnitus resolution",
            "myelopathy improvement",
            "radiation dose", "fluoroscopy time",
            # ── Surgical (surgeon's terms) ──
            "clip slippage", "parent vessel", "stroke", "infarct",
            "nimodipine",
        ],
    },
    "spine": {
        "anatomy": [
            "cervical", "thoracic", "lumbar", "sacral", "vertebra",
            "disc", "pedicle", "lamina", "facet", "foramen",
            "spinal cord", "nerve root", "cauda equina", "conus",
            "thecal sac", "ligamentum", "odontoid", "atlantoaxial",
            "spinous", "transverse process", "pars",
        ],
        "approach": [
            "laminectomy", "laminoplasty", "discectomy", "microdiscectomy",
            "fusion", "instrumentation", "pedicle screw", "cage",
            "corpectomy", "foraminotomy", "tlif", "plif", "alif",
            "xlif", "oblique", "lateral", "minimally invasive spine",
            "tubular", "endoscopic spine", "neuronavigation spine",
            "o-arm", "navigation", "robotic",
        ],
        "complications": [
            "dural tear", "nerve root injury", "pseudarthrosis",
            "adjacent segment", "instrumentation failure", "screw",
            "misplacement", "dysphagia", "hoarseness", "c5 palsy",
            "kyphosis", "sagittal", "flat back", "proximal junctional",
        ],
    },
    "functional": {
        "anatomy": [
            "basal ganglia", "thalamus", "subthalamic", "stn", "gpi",
            "vop", "vim", "striatum", "globus pallidus", "substantia nigra",
            "motor cortex", "premotor", "sma", "cingulate", "insula",
            "hippocampus", "amygdala", "anterior nucleus", "centromedian",
        ],
        "approach": [
            "deep brain stimulation", "dbs", "stereotactic", "frame",
            "frameless", "microelectrode", "mer", "macroelectrode",
            "impedance", "electrode", "lead", "pulse generator",
            "programming", "theta", "beta", "gamma",
            "radiofrequency", "rft", "rhizotomy", "thermocoagulation",
            "laser ablation", "litt", "focused ultrasound", "mrgfus",
        ],
        "complications": [
            "hemorrhage dbs", "infection dbs", "lead migration",
            "lead fracture", "erosion", "ipg", "stimulation side effects",
            "dysarthria", "gait", "cognitive dbs", "mood dbs",
            "suicide", "impulse control", "status dystonicus",
        ],
    },
    "pediatric": {
        "anatomy": [
            "fontanelle", "suture", "craniosynostosis", "hydrocephalus",
            "ventricle", "choroid plexus", "myelination", "germinal matrix",
            "posterior fossa", "fourth ventricle", "brainstem",
            "cerebell", "vermis", "tectal", "pineal",
        ],
        "approach": [
            "endoscopic third ventriculostomy", "etv", "shunt",
            "vps", "vetriculoperitoneal", "programmable",
            "posterior fossa craniotomy", "telovelar",
            "endoscopic biopsy", "navigated biopsy",
            "intraoperative ultrasound", "vagal nerve stimulator", "vns",
            "corpus callosotomy", "hemispherectomy", "lobar",
            "grid", "depth electrode", "seeg", "ecog",
        ],
        "complications": [
            "shunt infection", "shunt malfunction", "overdrainage",
            "slit ventricle", "cranial defect", "infection pediatric",
            "mutism", "cerebellar mutism", "posterior fossa syndrome",
            "endocrine", "growth", "developmental", "cognitive pediatric",
            "seizure pediatric", "hydrocephalus acquired",
        ],
    },
}

# Alias map: common topic terms → profile name
_TOPIC_TO_PROFILE: dict[str, str] = {
    # Skull base
    "vestibular schwannoma": "skull_base",
    "acoustic neuroma": "skull_base",
    "meningioma": "skull_base",
    "chordoma": "skull_base",
    "chondrosarcoma": "skull_base",
    "craniopharyngioma": "skull_base",
    "pituitary": "skull_base",
    "epidermoid": "skull_base",
    "petroclival": "skull_base",
    "cerebellopontine": "skull_base",
    "cpa": "skull_base",
    "jugular": "skull_base",
    "glomus": "skull_base",
    # Supratentorial tumor
    "glioblastoma": "supratentorial_tumor",
    "gbm": "supratentorial_tumor",
    "glioma": "supratentorial_tumor",
    "astrocytoma": "supratentorial_tumor",
    "oligodendroglioma": "supratentorial_tumor",
    "oligoastrocytoma": "supratentorial_tumor",
    "metastasis": "supratentorial_tumor",
    "brain metastasis": "supratentorial_tumor",
    "lymphoma": "supratentorial_tumor",
    # Vascular
    "aneurysm": "vascular",
    "clipping": "vascular",
    "coiling": "vascular",
    "anterior communicating": "vascular",
    "posterior communicating": "vascular",
    "anterior choroidal": "vascular",
    "basilar": "vascular",
    "avm": "vascular",
    "arteriovenous malformation": "vascular",
    "cavernous malformation": "vascular",
    "cavernoma": "vascular",
    "moyamoya": "vascular",
    "bypass": "vascular",
    "ec-ic": "vascular",
    "subarachnoid": "vascular",
    "sah": "vascular",
    "intracerebral hemorrhage": "vascular",
    "ich": "vascular",
    "hemorrhagic stroke": "vascular",
    "embolization": "vascular",
    "flow diversion": "vascular",
    "stent retriever": "vascular",
    "thrombectomy": "vascular",
    "davf": "vascular",
    "dural arteriovenous fistula": "vascular",
    "ccf": "vascular",
    "carotid cavernous fistula": "vascular",
    "carotid stenosis": "vascular",
    "carotid stenting": "vascular",
    "carotid endarterectomy": "vascular",
    "vasospasm": "vascular",
    "mechanical thrombectomy": "vascular",
    "acute ischemic stroke": "vascular",
    # Spine
    "spine": "spine",
    "spinal": "spine",
    "discectomy": "spine",
    "laminectomy": "spine",
    "fusion": "spine",
    "cervical": "spine",
    "lumbar": "spine",
    "thoracic": "spine",
    "scoliosis": "spine",
    "spondylolisthesis": "spine",
    "stenosis": "spine",
    "myelopathy": "spine",
    "radiculopathy": "spine",
    "cord": "spine",
    # Functional
    "deep brain": "functional",
    "dbs": "functional",
    "parkinson": "functional",
    "tremor": "functional",
    "dystonia": "functional",
    "epilepsy surgery": "functional",
    "seizure focus": "functional",
    "temporal lobectomy": "functional",
    "laser ablation": "functional",
    "litt": "functional",
    "focused ultrasound": "functional",
    "mrgfus": "functional",
    # Pediatric
    "pediatric": "pediatric",
    "paediatric": "pediatric",
    "child": "pediatric",
    "hydrocephalus": "pediatric",
    "shunt": "pediatric",
    "craniosynostosis": "pediatric",
    "myelomeningocele": "pediatric",
    "tethered cord": "pediatric",
    "medulloblastoma": "pediatric",
    "ependymoma": "pediatric",
}

# Build merged keyword lists from base + profile
def _build_keywords(profile: str) -> dict[str, list[str]]:
    """Merge base keywords with profile-specific keywords. Returns {anatomy, approach, complications}."""
    pd = _DOMAIN_PROFILES.get(profile, {})
    return {
        "anatomy": _BASE_ANATOMY + pd.get("anatomy", []),
        "approach": _BASE_APPROACH + pd.get("approach", []),
        "complications": _BASE_COMPLICATIONS + pd.get("complications", []),
    }


# ── Profile-specific template sections ───────────────────────────────────
# Each profile defines the headings + placeholder prompts sent to the LLM.
# Templates mirror the taxonomy axes: anatomy ← Axis 2+3, approach ← Axis 4,
# complications ← Axis 7.  Default template is used for profiles without
# custom sections.

_DEFAULT_TEMPLATES = {
    "anatomy": [
        ("Key Structures", "(list relevant structures)"),
        ("Vascular Supply", "(arteries, veins)"),
        ("Adjacent / At-Risk Structures", "(nerves, tracts, cisterns)"),
        ("Anatomic Variants", "(common variants to be aware of)"),
    ],
    "approach": [
        ("Approach Selection", "- **Approach:** (fill in)\n- **Rationale:** (fill in)"),
        ("Positioning", "(supine, prone, lateral, sitting, etc.)"),
        ("Key Steps", "1.\n2.\n3."),
        ("Intraoperative Monitoring", "(SSEP, MEP, EMG, BAER)"),
        ("Pitfalls", "(common errors and how to avoid them)"),
    ],
    "complications": [
        ("Intraoperative", "(vascular injury, neurological deficit, etc.)"),
        ("Postoperative", "(CSF leak, infection, hematoma, etc.)"),
        ("Long-Term", "(recurrence, radiation effects, etc.)"),
        ("Risk Mitigation", "(prevention strategies for each category)"),
    ],
}

# Vascular profile templates — derived from neurointerventional evidence taxonomy
# Axis 2 (Vascular Territory) + Axis 3 (Pathology) → anatomy headings
# Axis 4 (Procedure / Technique) → approach headings
# Axis 7 (Outcome Domain) → complications headings
_VASCULAR_TEMPLATES = {
    "anatomy": [
        ("Lesion Location & Morphology",
         "- **Location:** (segment, sidewall vs bifurcation, dome/neck dimensions)\n"
         "- **Size:** (maximum diameter, neck width)\n"
         "- **Morphology:** (saccular, fusiform, blister, dissecting)"),
        ("Parent Vessel & Branch Anatomy",
         "(parent artery, perforators, adjacent branches, dominance)"),
        ("Vascular Territory",
         "(anterior/posterior circulation, eloquent supply, watershed zones)"),
        ("Classification / Grading",
         "(Hunt-Hess, WFNS, modified Fisher for SAH; Spetzler-Martin, Lawton-Young for AVM; "
         "Borden/Cognard for dAVF)"),
        ("Associated Variants",
         "(multiple aneurysms, fenestrations, anatomic variants, vasospasm)"),
    ],
    "approach": [
        ("Treatment Strategy",
         "- **Indication:** (why treat)\n"
         "- **Options:** (clipping vs coiling vs flow diversion vs observation vs embolization)\n"
         "- **Decision drivers:** (rupture status, morphology, patient factors)"),
        ("Endovascular Technique",
         "(primary coiling, balloon-assisted, stent-assisted, flow diversion, "
         "intrasaccular disruption, liquid embolic, staged/multi-session)"),
        ("Open Surgical Approach",
         "(pterional, orbitozygomatic, interhemispheric, far-lateral, "
         "subtemporal, supraorbital; temporary clipping, burst suppression, adenosine)"),
        ("Access & Closure",
         "(transfemoral, transradial, direct carotid; closure device, manual compression)"),
        ("Adjunctive / Monitoring",
         "(ICG angiography, microdoppler, balloon test occlusion, "
         "provocative testing, intraoperative DSA)"),
        ("Technical Pearls / Pitfalls",
         "(clip selection, perforator preservation, brain relaxation, "
         "premature rupture management)"),
    ],
    "complications": [
        ("Hemorrhagic",
         "(SAH, ICH, access site hematoma, retroperitoneal hematoma, rebleed, delayed rupture)"),
        ("Ischemic",
         "(territorial infarct, perforator infarct, distal emboli, vasospasm / DCI)"),
        ("Device / Procedural",
         "(thrombosis, migration, malapposition, coil herniation, "
         "parent vessel compromise, dissection)"),
        ("Access Site",
         "(pseudoaneurysm, radial artery occlusion, groin hematoma, retroperitoneal)"),
        ("Functional Outcomes",
         "(mRS at discharge / 90 days, NIHSS, cognitive outcomes, "
         "aneurysm occlusion class, recanalization / retreatment rate)"),
        ("Durability",
         "(rebleed rate, long-term occlusion, in-stent stenosis, "
         "recurrence-free survival, retreatment-free survival)"),
    ],
}

_PROFILE_TEMPLATES: dict[str, dict[str, list[tuple[str, str]]]] = {
    "vascular": _VASCULAR_TEMPLATES,
    # Other profiles use the default until they get custom templates
}


def _get_template_sections(profile: str) -> dict[str, list[tuple[str, str]]]:
    """Return {anatomy, approach, complications} template sections for a profile."""
    return _PROFILE_TEMPLATES.get(profile, _DEFAULT_TEMPLATES)

def _detect_profile(topic: str) -> tuple[str, float]:
    """Detect the best domain profile for a topic string.

    Returns (profile_name, confidence) where confidence is 0.0–1.0.
    Falls back to 'skull_base' with low confidence if no match.
    """
    topic_lower = topic.lower()

    # First pass: exact substring matches (higher confidence)
    best_match = None
    best_len = 0
    for key, profile in _TOPIC_TO_PROFILE.items():
        if key in topic_lower:
            if len(key) > best_len:  # longest match wins
                best_match = profile
                best_len = len(key)

    if best_match:
        # Confidence = how much of the token space the matched key covers
        confidence = min(1.0, best_len / max(len(topic_lower), 10))
        return (best_match, confidence)

    # Second pass: word-level matching (lower confidence)
    topic_words = set(topic_lower.replace("-", " ").replace("/", " ").split())
    word_hits: dict[str, int] = {}
    for key, profile in _TOPIC_TO_PROFILE.items():
        key_words = set(key.split())
        overlap = topic_words & key_words
        if overlap:
            word_hits[profile] = word_hits.get(profile, 0) + len(overlap)

    if word_hits:
        best_profile = max(word_hits, key=lambda p: word_hits[p])  # type: ignore[arg-type]
        confidence = min(0.5, word_hits[best_profile] / max(len(topic_words), 5))
        return (best_profile, confidence)

    # Fallback: skull_base (most general neurosurgical profile)
    return ("skull_base", 0.0)


def _extract_relevant_sentences(
    articles: list[dict],
    keywords: list[str],
    max_per_article: int = 8,
    char_budget: int = 32000,
) -> list[str]:
    """Scan article abstracts for sentences matching keywords.

    Returns all sentences with ≥1 keyword hit, sorted by match density
    (descending), accumulated until char_budget is exceeded. Each article
    contributes at most max_per_article sentences.

    This is a relevance-ordering pass, NOT a filter. The LLM prompt
    already constrains to source facts — we just prioritize which
    sentences it sees first. At abstract scale, everything fits.
    """
    import re

    hits: list[tuple[int, str]] = []  # (score, sentence)
    seen: set[str] = set()

    for article in articles:
        article_hits = 0
        text = article.get("_abstract", "")
        structured = article.get("_structured", {})
        if structured:
            text += " " + " ".join(structured.values())

        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)

        for sent in sentences:
            if article_hits >= max_per_article:
                break
            sent_clean = sent.strip()
            if len(sent_clean) < 30:
                continue
            norm = sent_clean.lower()[:60]
            if norm in seen:
                continue

            score = 0
            sent_lower = sent_clean.lower()
            for kw in keywords:
                if kw in sent_lower:
                    score += 1

            if score >= 1:
                hits.append((score, sent_clean))
                seen.add(norm)
                article_hits += 1

    # Sort by score descending (most keyword-dense first), then accumulate
    hits.sort(key=lambda x: x[0], reverse=True)

    result: list[str] = []
    total_chars = 0
    for score, sent in hits:
        if total_chars + len(sent) > char_budget:
            break
        result.append(sent)
        total_chars += len(sent)

    return result


async def _populate_section(
    articles: list[dict],
    keywords: list[str],
    template_sections: list[tuple[str, str]],
    topic: str,
    section_title: str,
    char_budget: int = 32000,
    profile_name: str = "unknown",
    keyword_count: int = 0,
    split_complications: bool = False,
) -> str:
    """Run extract → synthesize → guardrail pipeline for one template section.

    Args:
        articles: Enriched article dicts with _abstract and _structured
        keywords: Domain-profile keywords for relevance ordering
        template_sections: [(section_name, placeholder_text), ...]
        topic: Case topic string
        section_title: Display title for the section
        char_budget: Max characters of source text to send to LLM (default 32K ≈ 8K tokens)
        profile_name: Name of the domain profile used (for diagnostics)
        keyword_count: Number of active keywords (for diagnostics)
        split_complications: If True, use synthesize_complications_split instead of
                            single synthesize_section call

    Returns:
        Final markdown content to write to the file.
    """
    from caseprep.llm import synthesize_section, synthesize_complications_split, verify_synthesis

    article_count = len(articles)

    # Stage 1: Extract (relevance-ordered, not filtered — all sentences with ≥1 keyword hit)
    extracted = _extract_relevant_sentences(articles, keywords, char_budget=char_budget)

    if not extracted:
        # Diagnostic: show what was attempted
        profile_line = f"  Profile: **{profile_name}** ({keyword_count} keywords)"
        count_line = f"  Articles searched: {article_count}"
        lines = [f"# {section_title} — {topic}\n"]
        lines.append(f"> *No sentences matching {section_title.lower()} keywords were found.*\n")
        lines.append(f"> {profile_line}\n")
        lines.append(f"> {count_line}\n")
        lines.append(f"> *Consider broadening search terms or adding domain-specific source material.*\n")
        lines.append("")
        for name, placeholder in template_sections:
            lines.append(f"## {name}\n")
            lines.append(f"(Insufficient data in search results)\n")
        return "\n".join(lines)

    # Stage 2: Synthesize via LLM
    try:
        if split_complications:
            synthesized = await synthesize_complications_split(
                source_sentences=extracted,
                topic=topic,
                template_sections=template_sections,
            )
        else:
            synthesized = await synthesize_section(
                template_sections=template_sections,
                source_sentences=extracted,
                topic=topic,
            )
        if not synthesized:
            raise ValueError("empty response from LLM")
    except Exception:
        # LLM failed — fall back to raw extracted sentences
        lines = [f"# {section_title} — {topic}\n"]
        lines.append("> *LLM synthesis unavailable — showing raw extracted findings.*\n")
        lines.append(f"> *{len(extracted)} sentences extracted from {article_count} articles using {profile_name} profile ({keyword_count} keywords).*\n")
        for name, placeholder in template_sections:
            lines.append(f"## {name}\n")
            lines.append(f"- (see source sentences below)\n")
        lines.append("\n## Source Sentences from Literature\n")
        for i, s in enumerate(extracted, 1):
            lines.append(f"{i}. {s}\n")
        return "\n".join(lines)

    # Stage 3: Guardrail
    result = verify_synthesis(synthesized, extracted)

    # Handle 0/0 edge case explicitly
    if result.total_count == 0:
        lines = [f"# {section_title} — {topic}\n"]
        lines.append("> *LLM synthesis produced no verifiable claims. Showing raw source sentences instead.*\n")
        for name, placeholder in template_sections:
            lines.append(f"## {name}\n")
            lines.append(f"- (see source sentences below)\n")
        lines.append("\n## Source Sentences from Literature\n")
        for i, s in enumerate(extracted, 1):
            lines.append(f"{i}. {s}\n")
        return "\n".join(lines)

    if result.passed:
        lines = [f"# {section_title} — {topic}\n"]
        # Add diagnostic header with guardrail info
        diag_lines = []
        if result.flagged_count == 0:
            diag_lines.append(f"All {result.total_count} claims verified against cited sources")
        else:
            diag_lines.append(f"{result.flagged_count}/{result.total_count} claims flagged during verification")
        diag_lines.append(f"{len(extracted)} source sentences from {article_count} articles ({profile_name} profile)")
        lines.append(f"> *{' | '.join(diag_lines)}.*\n")
        lines.append("")
        lines.append(synthesized)
        return "\n".join(lines)
    else:
        # Too many unsupported claims — fall back to raw sentences
        lines = [f"# {section_title} — {topic}\n"]
        lines.append(f"> *LLM synthesis rejected: {result.flagged_count}/{result.total_count} claims could not be verified against their cited sources.*\n")
        # Show which claims failed and why
        lines.append("> \n")
        for i, claim_info in enumerate(result.claims):
            if not claim_info["passed"] and claim_info.get("failure"):
                lines.append(f"> - Claim {i+1}: {claim_info['failure']}\n")
        lines.append("> \n")
        lines.append(f"> *({len(extracted)} sentences extracted from {article_count} articles using {profile_name} profile). Showing raw source sentences below.*\n")
        for name, placeholder in template_sections:
            lines.append(f"## {name}\n")
            lines.append(f"- (see source sentences below)\n")
        lines.append("\n## Source Sentences from Literature\n")
        for i, s in enumerate(extracted, 1):
            lines.append(f"{i}. {s}\n")
        return "\n".join(lines)


async def _write_filled_templates(
    out_dir: Path, topic: str, summary: str,
    axis_data: dict[str, list[dict]] | None = None,
) -> None:
    """Write filled-in markdown templates using keyword-extracted content from search results."""

    (out_dir / "README.md").write_text(
        f"# {topic}\n\n"
        f"## Case Overview\n\n"
        f"- **Topic:** {topic}\n"
        f"- **Date:** (fill in)\n"
        f"- **Presenter:** (fill in)\n\n"
        f"## Literature Summary\n\n"
        f"{summary}\n",
        encoding="utf-8",
    )

    (out_dir / "literature.md").write_text(
        f"# Literature Review — {topic}\n\n{summary}\n",
        encoding="utf-8",
    )

    # If no axis_data (backwards compat), write blank templates
    if not axis_data:
        for name, template in [
            ("anatomy.md", "Relevant Anatomy"),
            ("approach.md", "Surgical Approach"),
            ("complications.md", "Potential Complications"),
        ]:
            (out_dir / name).write_text(
                f"# {template} — {topic}\n\n"
                f"## (no data available)\n\n"
                f"- (run build_caseplan to populate this section)\n",
                encoding="utf-8",
            )
        return

    # Detect domain profile and build keywords
    profile_name, profile_confidence = _detect_profile(topic)
    kw = _build_keywords(profile_name)

    # Extract and populate each section via extract→synthesize→guardrail pipeline
    # Use profile-specific keywords with per-section sources
    technique_articles = axis_data.get("Surgical Technique", [])
    reviews_articles = axis_data.get("Reviews / Landmarks", [])
    outcomes_articles = axis_data.get("Outcomes / Evidence", [])
    complications_articles = axis_data.get("Complications", [])

    # Log profile detection
    conf_str = f"{profile_confidence:.0%}" if profile_confidence > 0 else "fallback"
    print(f"  [profile] Detected: {profile_name} (confidence: {conf_str})")

    # Get profile-specific template sections (from taxonomy for vascular, default for others)
    templates = _get_template_sections(profile_name)

    # ── anatomy.md ─────────────────────────────────────────────────────
    anatomy_text = await _populate_section(
        articles=technique_articles + reviews_articles,
        keywords=kw["anatomy"],
        template_sections=templates["anatomy"],
        topic=topic,
        section_title="Relevant Anatomy",
        profile_name=profile_name,
        keyword_count=len(kw["anatomy"]),
    )
    (out_dir / "anatomy.md").write_text(anatomy_text, encoding="utf-8")

    # ── approach.md ────────────────────────────────────────────────────
    approach_text = await _populate_section(
        articles=technique_articles,
        keywords=kw["approach"],
        template_sections=templates["approach"],
        topic=topic,
        section_title="Surgical Approach",
        profile_name=profile_name,
        keyword_count=len(kw["approach"]),
    )
    (out_dir / "approach.md").write_text(approach_text, encoding="utf-8")

    # ── complications.md ───────────────────────────────────────────────
    complications_text = await _populate_section(
        articles=complications_articles + outcomes_articles,
        keywords=kw["complications"],
        template_sections=templates["complications"],
        topic=topic,
        section_title="Potential Complications",
        profile_name=profile_name,
        keyword_count=len(kw["complications"]),
        split_complications=True,  # use 2-call split to avoid token truncation
    )
    (out_dir / "complications.md").write_text(complications_text, encoding="utf-8")


def _resource_html(topic: str, links: dict[str, str]) -> str:
    items = "\n".join(
        f'  <li><a href="{url}" target="_blank" rel="noopener">{name}</a></li>'
        for name, url in links.items()
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"<title>Resource Links — {topic}</title>\n"
        "<style>\n"
        "  body { font-family: system-ui, sans-serif; max-width: 700px; margin: 2em auto; padding: 0 1em; }\n"
        "  h1 { font-size: 1.4em; }\n"
        "  ul { list-style: none; padding: 0; }\n"
        "  li { margin: 0.5em 0; }\n"
        "  a { color: #1a56db; }\n"
        "</style>\n</head>\n<body>\n"
        f"<h1>Resource Links — {topic}</h1>\n<ul>\n{items}\n</ul>\n"
        "</body>\n</html>\n"
    )


def _handle_generate(args: dict) -> str:
    topic = args["topic"]
    output_dir = args.get("output_dir", "")
    out = Path(output_dir) if output_dir else None
    slug = topic.lower().replace(" ", "-")
    resource_path = _generate_caseprep(topic, out or f"{slug}-caseprep")
    return (
        f"Case prep generated.\n"
        f"  Output: {resource_path.parent.resolve()}\n"
        f"  Resources: {resource_path}\n"
    )


def _handle_pdfs(args: dict) -> str:
    topic = args["topic"]
    pdf_dir = Path(args["pdf_dir"])
    results = _search_local_pdfs(topic, pdf_dir)
    return format_pdf_results(results)


async def _handle_get_fulltext(args: dict) -> str:
    """Fetch best available content for a single PMID: PMC > structured > plain."""
    pmid = args["pmid"]
    summaries = await _pubmed_summaries([pmid])
    if not summaries:
        return f"PMID {pmid} not found."
    paper = summaries[0]
    lines = [f"## {paper['title']}", f"{paper['authors']} — *{paper['source']}* ({paper['pubdate']})", ""]

    # Tier 1: PMC full text
    fulltexts = await _pubmed_fulltext([pmid])
    if pmid in fulltexts:
        lines.append("### PMC Full Text\n")
        lines.append(fulltexts[pmid][:5000])
        return "\n".join(lines)

    # Tier 2: Structured abstract (only accept if it has recognized sections)
    structured = await _pubmed_structured_abstracts([pmid])
    if pmid in structured:
        sections = structured[pmid]
        has_content = any(
            sections.get(k) for k in ("BACKGROUND", "METHODS", "RESULTS", "CONCLUSIONS", "TEXT")
        )
        if has_content:
            lines.append("### Structured Abstract\n")
            for label in ("BACKGROUND", "METHODS", "RESULTS", "CONCLUSIONS"):
                if label in sections:
                    lines.append(f"**{label.title()}:** {sections[label]}\n")
            if "TEXT" in sections:
                lines.append(f"{sections['TEXT']}\n")
            return "\n".join(lines)

    # Tier 3: Plain abstract
    abstracts = await _pubmed_abstracts([pmid])
    if pmid in abstracts:
        lines.append("### Abstract\n")
        lines.append(abstracts[pmid])
        return "\n".join(lines)

    return f"No full text or abstract available for PMID {pmid}."


async def _handle_radiology(args: dict) -> str:
    """Search Open-i for radiology images, download them, return local paths.

    Extracts query terms for relevance filtering: a result's title or caption
    must contain at least one term to be included.  Fetches more results from
    Open-i to compensate for the filter.

    Images are downloaded to <query>-images/ (or *output_dir* if provided).
    Set download_images=false to skip downloading and return URLs only.
    """
    query = args["query"]
    max_results = min(args.get("max_results", 5), 10)
    modality = args.get("modality")
    download = args.get("download_images", True)
    output_dir = args.get("output_dir", "")

    # Extract terms for relevance post-filtering
    terms = _query_terms(query)

    results, total = await _openi_search(query, max_results, modality, query_terms=terms)

    mod_note = f" — modality: {modality}" if modality and modality != "any" else ""
    filter_note = f" (filtered by: {', '.join(terms)})" if terms else ""
    lines = [
        f"## Radiology Images{mod_note} — {query}{filter_note}",
        f"({len(results)} shown of {total} total)\n",
    ]

    if not results:
        lines.append("No radiology images found. Try a broader query or a different modality.")
        return "\n".join(lines)

    # Download images if requested
    if download and results:
        slug = query.strip().lower().replace(" ", "-")[:60]
        out_dir = Path(output_dir) if output_dir else Path(f"{slug}-images")
        if not out_dir.is_absolute():
            out_dir = Path.cwd() / out_dir
        results = await _download_images(results, out_dir, max_images=max_results)
        lines.append(f"*Images saved to {out_dir.resolve()}/*\n")

    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title'][:120]}{'…' if len(r['title']) > 120 else ''}**")
        lines.append(f"   *{r['journal']}* ({r['pubdate']}) — {r['authors'][:80]}")
        if r["pmid"]:
            lines.append(f"   PMID: [{r['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/)")
        if r.get("article_type"):
            lines.append(f"   Type: {r['article_type']}")
        if r["caption"]:
            cap = r["caption"][:300] + ("…" if len(r["caption"]) > 300 else "")
            lines.append(f"   Caption: {cap}")
        local = r.get("local_path", "")
        if local and not local.startswith("Error"):
            lines.append(f"   Image: {local}")
            # MEDIA tag so Hermes can show the image inline
            lines.append(f"   MEDIA:{local}")
        elif local:
            lines.append(f"   Download error: {local}")
        lines.append("")

    return "\n".join(lines)


async def _handle_send_email(args: dict) -> str:
    """Send an email via Resend REST API."""
    if not _RESEND_API_KEY:
        return (
            "Error: RESEND_API_KEY not set. Set it in your environment:\n"
            "  export RESEND_API_KEY=re_xxxx\n"
            "Get a key at https://resend.com/api-keys"
        )

    to = args["to"]
    subject = args["subject"]
    body = args["body"]
    sender = args.get("from_", "").strip() or RESEND_DEFAULT_FROM

    payload = {
        "from": sender,
        "to": [to],
        "subject": subject,
        "text": body,
    }

    resp = await _client().post(
        f"{RESEND_API}/emails",
        json=payload,
        headers={
            "Authorization": f"Bearer {_RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
    )

    if resp.status_code == 200:
        data = resp.json()
        email_id = data.get("id", "unknown")
        return f"Email sent ✓\n  From: {sender}\n  To: {to}\n  Subject: {subject}\n  Resend ID: {email_id}"
    else:
        try:
            detail = resp.json()
        except Exception:
            detail = {"message": resp.text}
        msg = detail.get("message", resp.text)
        return f"Email failed (HTTP {resp.status_code}): {msg}"


# ── Entry point ─────────────────────────────────────────────────────────────

def run():
    """Run the MCP server on stdio."""
    async def _main():
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    asyncio.run(_main())


if __name__ == "__main__":
    run()
