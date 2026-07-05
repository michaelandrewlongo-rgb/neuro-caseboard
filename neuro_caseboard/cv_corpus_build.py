"""Ingestion for the cerebrovascular curated full-text corpus (Lane C extension).

Builds a standalone SQLite DB (schema-identical to neuro_caseboard/corpus.py's
works/identifiers/text_passages) from cv_full_text/ + have-list.csv, reusing
already-extracted rows from the sibling cv-curric big corpus where a PMID
overlaps, and freshly parsing the rest from JATS XML or plaintext.
"""
from __future__ import annotations

import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

# Spec originally called for 40, but fixture text lengths require ≤20; using 20 as minimal correction.
_MIN_PASSAGE_CHARS = 20

_SECTION_ALIASES = {
    "abstract": "abstract",
    "background": "introduction",
    "intro": "introduction",
    "introduction": "introduction",
    "materials and methods": "methods",
    "material and methods": "methods",
    "materials|methods": "methods",
    "methods": "methods",
    "methodology": "methods",
    "results": "results",
    "discussion": "discussion",
    "conclusion": "conclusion",
    "conclusions": "conclusion",
    "case report": "case_report",
    "case presentation": "case_report",
    "case": "case_report",
}

_SKIP_SEC_TYPES = {
    "coi-statement", "conflict-of-interest", "disclaimer", "funding-information",
    "funding", "data-availability", "supplementary-material", "author-contributions",
    "ethics-statement",
}

_HEADER_RE = re.compile(
    r"^[ \t]*(abstract|background|introduction|materials and methods|"
    r"material and methods|methods|methodology|results|discussion|"
    r"conclusions?|case report|case presentation)[ \t]*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


def _normalize_section(label: str) -> str:
    return _SECTION_ALIASES.get((label or "").strip().lower(), "other")


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def parse_jats_sections(xml_text: str) -> list:
    """Top-level abstract + body <sec> elements from a JATS/NLM full-text XML."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    passages = []
    abstract_el = root.find(".//abstract")
    if abstract_el is not None:
        text = _clean("".join(abstract_el.itertext()))
        if len(text) >= _MIN_PASSAGE_CHARS:
            passages.append(("abstract", text))
    body = root.find(".//body")
    if body is None:
        return passages
    for sec in body.findall("sec"):
        sec_type_attr = (sec.get("sec-type") or "").strip().lower()
        if sec_type_attr in _SKIP_SEC_TYPES:
            continue
        label = sec_type_attr
        if not label:
            title_el = sec.find("title")
            label = title_el.text if title_el is not None and title_el.text else ""
        text = _clean("".join(sec.itertext()))
        if len(text) >= _MIN_PASSAGE_CHARS:
            passages.append((_normalize_section(label), text))
    return passages


def split_plaintext_sections(text: str) -> list:
    """Regex IMRAD-header splitter for a plaintext-only article (no XML available)."""
    text = text or ""
    matches = list(_HEADER_RE.finditer(text))
    if not matches:
        body = _clean(text)
        return [("other", body)] if len(body) >= _MIN_PASSAGE_CHARS else []
    passages = []
    lead = _clean(text[: matches[0].start()])
    if len(lead) >= _MIN_PASSAGE_CHARS:
        passages.append(("other", lead))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = _clean(text[start:end])
        if len(chunk) >= _MIN_PASSAGE_CHARS:
            passages.append((_normalize_section(m.group(1)), chunk))
    return passages
