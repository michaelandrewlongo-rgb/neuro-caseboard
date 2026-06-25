"""Section-aware evidence gathering + the 7-call guided-prose synthesis for the briefing.

Retrieval reuses the existing textbook retriever (no second stack). The pool is numbered ONCE
(T# textbook, L# PubMed) so all 7 concurrent section calls cite against the same numbering.
Synthesis goes through an injected `.generate(system, user, images)` client — offline tests pass
a fake, exactly like woven_synth.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SECTION_KEYS = ["pathology", "management", "modalities", "workup",
                "technique", "risks", "equipment"]

# Intent-query templates — section-aware gathering so no section starves (design §5).
# {topic} is case.to_topic(); kept generic (no clinical literals) so it spans all subspecialties.
SECTION_QUERIES = {
    "pathology":  "{topic} pathophysiology natural history indication",
    "management": "{topic} management strategy decision algorithm treatment selection",
    "modalities": "{topic} treatment options comparison advantages disadvantages alternatives",
    "workup":     "{topic} preoperative workup imaging optimization labs medications",
    "technique":  "{topic} operative technique approach positioning critical steps anatomy",
    "risks":      "{topic} complications risks rescue bailout management",
    "equipment":  "{topic} equipment instrumentation devices implants adjuncts",
}


@dataclass
class EvidencePacket:
    textbook: list = field(default_factory=list)   # [{ref_id:"T1", citation, text, book, page}]
    pubmed: list = field(default_factory=list)     # [{ref_id:"L1", title, journal, year, pmid, doi, url}]
    prompt_block: str = ""                         # numbered sources rendered for the LLM


def _rec_citation(rec) -> str:
    meta = getattr(rec, "metadata", {}) or {}
    return (meta.get("citation") or "").strip() or (getattr(rec, "title", "") or "").strip()


def _collect_pubmed(dossier) -> list[dict]:
    """Flatten any attached PubMed citations across dossier sections, deduped by pmid/title."""
    out, seen = [], set()
    for sec in getattr(dossier, "sections", []) or []:
        lit = getattr(sec, "literature", None)
        for c in getattr(lit, "citations", []) or []:
            key = getattr(c, "pmid", "") or getattr(c, "title", "")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append({"title": getattr(c, "title", ""), "journal": getattr(c, "journal", ""),
                        "year": getattr(c, "year", None), "pmid": getattr(c, "pmid", ""),
                        "doi": getattr(c, "doi", ""), "url": getattr(c, "url", "")})
    return out


def gather_briefing_evidence(case, dossier, retriever) -> EvidencePacket:
    """One intent query per briefing section through `retriever`, pooled with the dossier's
    PubMed citations, deduped and numbered T#/L#. Returns the packet + a rendered prompt block."""
    topic = case.to_topic()
    textbook, seen_cite = [], {}
    if retriever is not None:
        for key in SECTION_KEYS:
            q = SECTION_QUERIES[key].format(topic=topic)
            try:
                recs = retriever.retrieve(q, top_n=6) or []
            except Exception:
                recs = []
            for rec in recs:
                cite = _rec_citation(rec)
                if not cite or cite in seen_cite:
                    continue
                meta = getattr(rec, "metadata", {}) or {}
                ref_id = f"T{len(textbook) + 1}"
                seen_cite[cite] = ref_id
                textbook.append({"ref_id": ref_id, "citation": cite,
                                 "text": (getattr(rec, "text", "") or "")[:600],
                                 "book": meta.get("book", ""), "page": meta.get("page")})

    pubmed = _collect_pubmed(dossier)
    for i, p in enumerate(pubmed, 1):
        p["ref_id"] = f"L{i}"

    lines = ["TEXTBOOK SOURCES (cite as [T#]):"]
    for t in textbook:
        lines.append(f"[{t['ref_id']}] {t['citation']} — {t['text']}")
    if pubmed:
        lines.append("\nCONTEMPORARY STUDIES (cite as [L#]):")
        for p in pubmed:
            meta = ", ".join(s for s in (p.get("journal", ""), str(p.get("year") or "")) if s)
            lines.append(f"[{p['ref_id']}] {p.get('title','')} — {meta}")
    return EvidencePacket(textbook=textbook, pubmed=pubmed, prompt_block="\n".join(lines))
