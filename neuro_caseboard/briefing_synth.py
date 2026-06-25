"""Section-aware evidence gathering + the 7-call guided-prose synthesis for the briefing.

Retrieval reuses the existing textbook retriever (no second stack). The pool is numbered ONCE
(T# textbook, L# PubMed) so all 7 concurrent section calls cite against the same numbering.
Synthesis goes through an injected `.generate(system, user, images)` client — offline tests pass
a fake, exactly like woven_synth.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from neuro_caseboard.briefing_model import (
    AlgoEdge, AlgoNode, BriefingItem, BriefingSection, CranialEquipment,
    DecisionAlgorithm, EndovascularEquipment, SpineEquipment, TreatmentModality,
)

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


PROSE_KEYS = {"pathology", "management", "workup", "technique", "risks"}

_PROSE_LINE = re.compile(r"^\[(critical|high|optional)\]\s*(.*?)\s*(\{([^}]*)\})?\s*$")
_REF_TOKEN = re.compile(r"^[TL]\d+$")
_ALGO_MARK = "---ALGORITHM---"


def _split_refs(blob: str) -> tuple[list[str], bool]:
    """Return (resolved T#/L# refs, unsupported_flag). Non-ref tokens (e.g. 'verify') or an
    empty brace → unsupported. ponytail: tolerant — unknown tokens just mean 'no real source'."""
    toks = [t.strip() for t in (blob or "").split(",") if t.strip()]
    refs = [t for t in toks if _REF_TOKEN.match(t)]
    unsupported = (not refs)  # no resolvable source → clinician-verify
    return refs, unsupported


def parse_prose_section(key: str, title: str, text: str) -> BriefingSection:
    items = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line == _ALGO_MARK:
            break  # algorithm block (management) is parsed separately
        m = _PROSE_LINE.match(line)
        if not m:
            continue  # ponytail: skip un-tagged lines rather than guess a priority
        priority, body, _, refblob = m.groups()
        refs, unsupported = _split_refs(refblob)
        if not body:
            continue
        items.append(BriefingItem(text=body, priority=priority,
                                  source_refs=refs, unsupported=unsupported))
    return BriefingSection(key=key, title=title, items=items)


def parse_algorithm(text: str):
    if _ALGO_MARK not in (text or ""):
        return None
    block = text.split(_ALGO_MARK, 1)[1]
    nodes, edges = [], []
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "->" in line:
            left, _, cond = line.partition("|")
            src, _, dst = left.partition("->")
            if src.strip() and dst.strip():
                edges.append(AlgoEdge(src=src.strip(), dst=dst.strip(), condition=cond.strip()))
        elif line.count("|") >= 2:
            nid, kind, label = (p.strip() for p in line.split("|", 2))
            kind = kind if kind in ("decision", "action", "terminal") else "decision"
            if nid:
                nodes.append(AlgoNode(id=nid, label=label, kind=kind))
    return DecisionAlgorithm(nodes=nodes, edges=edges) if nodes else None


def _kv_lines(text: str) -> dict:
    out = {}
    for raw in (text or "").splitlines():
        if ":" in raw:
            k, _, v = raw.partition(":")
            out[k.strip().lower()] = v.strip()
    return out


def _as_items(v: str) -> list[str]:
    return [s.strip() for s in (v or "").split(";") if s.strip()]


def parse_modalities(text: str) -> list[TreatmentModality]:
    mods = []
    blocks = re.split(r"^###\s+", text or "", flags=re.MULTILINE)
    for blk in blocks:
        blk = blk.strip()
        if not blk:
            continue
        name, _, rest = blk.partition("\n")
        kv = _kv_lines(rest)
        refs, _ = _split_refs(kv.get("refs", "").replace(",", ","))
        mods.append(TreatmentModality(
            name=name.strip(),
            role=kv.get("role", ""),
            advantages=_as_items(kv.get("advantages", "")),
            limitations=_as_items(kv.get("limitations", "")),
            favoring=_as_items(kv.get("favoring", "")),
            preferred=kv.get("preferred", "").strip().lower() in ("yes", "true", "1"),
            source_refs=refs,
        ))
    return mods


_EQUIP_CLASS = {"cranial": CranialEquipment, "spine": SpineEquipment,
                "endovascular": EndovascularEquipment}


def parse_equipment(text: str, subspecialty: str):
    cls = _EQUIP_CLASS.get(subspecialty)
    if cls is None:
        return None
    kv = _kv_lines(text)
    fields = {n for n in cls.model_fields if n not in ("kind", "source_refs")}
    data = {f: _as_items(kv[f]) for f in fields if f in kv}
    refs, _ = _split_refs(kv.get("refs", ""))
    return cls(source_refs=refs, **data)


# ---------------------------------------------------------------------------
# Task 4: 7-call concurrent orchestrator + reference assembly
# ---------------------------------------------------------------------------
from concurrent.futures import ThreadPoolExecutor

from neuro_caseboard.briefing_model import BriefingReference, OperativeBriefing

_SECTION_TITLES = {
    "pathology": "Case & Pathology Frame", "management": "Management Strategy",
    "modalities": "Treatment Modalities", "workup": "Preoperative Workup & Optimization",
    "technique": "Operative Strategy & Technique", "risks": "Risks, Complications & Rescue",
    "equipment": "Equipment & Device Plan",
}

# What each section must emit. The prose grammar is enforced by these instructions + the parsers.
_FORMAT = {
    "prose": ("Output one claim per line: `[critical|high|optional] claim text {refs}` where refs "
              "are the bracketed source numbers, e.g. {T1, L2}. Use {verify} when no source "
              "supports the claim. No other prose, no headings."),
    "management": ("First, prose claim lines: `[critical|high|optional] text {refs}`. Then a line "
                   "`---ALGORITHM---` followed by 4–7 nodes `id | decision|action|terminal | label` "
                   "and edges `src -> dst | condition`."),
    "modalities": ("For each viable modality output a block:\n### <name>\nrole: ...\nadvantages: a; b\n"
                   "limitations: a; b\nfavoring: a; b\npreferred: yes|no\nrefs: T1, L2"),
    "equipment": ("Output `key: value` lines for THIS subspecialty's fields only "
                  "(semicolon-separated lists), plus a final `refs: T#, L#` line. Name device "
                  "CLASSES, not commercial products unless a source supports it."),
}

_SYSTEM = (
    "You are an attending neurosurgeon writing ONE section of a dense, case-specific operative "
    "briefing for another attending. Be high-yield; skip basics. Cite the bracketed source "
    "number for every substantive claim — textbook [T#], contemporary studies [L#], never merged. "
    "Never invent a citation, device, dose, threshold, or rate. If the sources do not support a "
    "specific, mark it {verify}. Do not include figures or a bibliography."
)


def subspecialty_of(case) -> str:
    """Map the case to one of the three equipment schemas via the existing profile classifier."""
    from neuro_caseboard.pipeline import classify_profile
    prof = classify_profile(case.to_topic())
    if prof == "spine":
        return "spine"
    if prof == "vascular":
        return "endovascular"
    return "cranial"   # skull_base / open / unclassified default to the cranial schema


def build_section_prompt(key: str, packet, case, subspecialty: str):
    fmt = _FORMAT.get(key, _FORMAT["prose"])
    user = (f"SECTION={key} ({_SECTION_TITLES[key]})\n"
            f"Case: {case.to_topic()}\nSubspecialty: {subspecialty}\n\n"
            f"EVIDENCE (cite these numbers only):\n{packet.prompt_block}\n\n"
            f"TASK: Write the {_SECTION_TITLES[key]} section.\n{fmt}")
    return _SYSTEM, user


def _synth_one(key, packet, case, subspecialty, synth_client):
    system, user = build_section_prompt(key, packet, case, subspecialty)
    return synth_client.generate(system, user, [])   # images unused for text synthesis


def synthesize_briefing(case, dossier, packet, synth_client, *,
                        subspecialty=None, max_workers=7):
    """Run all 7 section calls concurrently (all-to-all over `packet`), parse each into the model,
    and assemble the references + support map from the refs actually cited. Failure-isolated:
    a section whose call raises is recorded in `failed_sections` and left empty."""
    subspecialty = subspecialty or subspecialty_of(case)
    raw, failed = {}, []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_synth_one, k, packet, case, subspecialty, synth_client): k
                for k in SECTION_KEYS}
        for fut, k in ((f, futs[f]) for f in futs):
            try:
                raw[k] = fut.result()
            except Exception:
                failed.append(k)
    failed.sort(key=SECTION_KEYS.index)

    brief = OperativeBriefing(title=f"Operative Briefing — {case.to_topic()}")
    for k in SECTION_KEYS:
        text = raw.get(k, "")
        if k in PROSE_KEYS:
            brief.sections.append(parse_prose_section(k, _SECTION_TITLES[k], text))
        elif k == "modalities":
            brief.modalities = parse_modalities(text)
        elif k == "equipment":
            brief.equipment = parse_equipment(text, subspecialty)
        if k == "management":
            brief.algorithm = parse_algorithm(text)

    references = _assemble_references(brief, packet)
    return brief, references, failed


def _all_refs_with_sections(brief):
    """Yield (ref_id, section_key) for every cited ref across the briefing (the support map)."""
    for s in brief.sections:
        for it in s.items:
            for r in it.source_refs:
                yield r, s.key
    for m in brief.modalities:
        for r in m.source_refs:
            yield r, "modalities"
    if brief.equipment:
        for r in brief.equipment.source_refs:
            yield r, "equipment"


def _assemble_references(brief, packet) -> list[BriefingReference]:
    used = {}
    for ref_id, sec in _all_refs_with_sections(brief):
        used.setdefault(ref_id, set()).add(sec)
    tb = {t["ref_id"]: t for t in packet.textbook}
    pm = {p["ref_id"]: p for p in packet.pubmed}
    refs = []
    for ref_id in sorted(used, key=lambda r: (r[0], int(r[1:]))):
        secs = sorted(used[ref_id])
        if ref_id in tb:
            t = tb[ref_id]
            refs.append(BriefingReference(ref_id=ref_id, kind="textbook", citation=t["citation"],
                                          meta={"book": t["book"], "page": t["page"]}, sections=secs))
        elif ref_id in pm:
            p = pm[ref_id]
            refs.append(BriefingReference(ref_id=ref_id, kind="pubmed", citation=p.get("title", ""),
                                          meta={k: p[k] for k in ("journal", "year", "pmid", "doi", "url") if k in p},
                                          sections=secs))
        # ponytail: a ref the LLM invented that isn't in the packet is dropped here — no fabrication.
    return refs
