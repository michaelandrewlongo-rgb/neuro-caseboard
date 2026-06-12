"""Compile a caseprep AuditedManifest (+ evidence) into a corrected Dossier.

This replaces caseprep's case_compiler presentation entirely. It owns the fixes for
defects #2,#3,#5,#6,#7,#8,#9; the renderers own #1 and #4. Everything here is driven by
card metadata (target_file, compiler_slot, section_key, audit_status) and text
structure — never hardcoded clinical phrases — so it generalises across all of
neurosurgery.
"""

from __future__ import annotations

import re

from neuro_caseboard.model import (
    Appendix,
    AppendixEntry,
    Claim,
    Dossier,
    EvidenceSummary,
    FigureItem,
    Section,
)
from neuro_caseboard.textops import scrub_question, split_compound
from neuro_caseboard.captions import complete_caption, relevance_line
from neuro_caseboard.dedup import dedup_sections

_HEADINGS = {
    "03-anatomy-at-risk.md": "Anatomy at Risk",
    "04-operative-plan.md": "Operative Plan",
    "05-risk-and-rescue.md": "Risk and Rescue",
}
_ORDER = ["03-anatomy-at-risk.md", "04-operative-plan.md", "05-risk-and-rescue.md"]
_INTRO = {
    "Anatomy at Risk": "Structures to identify, preserve, or monitor for this approach.",
    "Operative Plan": "Critical steps, decision points, and stop criteria.",
    "Risk and Rescue": "Expected and catastrophic complications with rescue sequences.",
}
# no_evidence cards are still surgeon-facing VERIFY prompts (the Explorer designs them
# as such); only genuinely off-target retrievals are quarantined to the appendix.
_PRIMARY = {"supported", "needs_review", "no_evidence"}
_STATUS = {"supported": "supported", "needs_review": "verify", "no_evidence": "verify"}


def _humanize(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    if base.endswith(".md"):
        base = base[:-3]
    base = re.sub(r"^\d+[-_]?", "", base)
    return base.replace("-", " ").replace("_", " ").strip().title() or name


def _heading_for(target_file: str) -> str:
    return _HEADINGS.get(target_file) or _humanize(target_file)


def _short(text: str, limit: int = 60) -> str:
    t = text.strip()
    return t if len(t) <= limit else t[: limit - 1].rsplit(" ", 1)[0] + "…"


def compile_dossier(
    audited_manifest,
    *,
    topic: str = "",
    evidence=None,
    card_evidence=None,
    page_texts=None,
) -> Dossier:
    evidence = list(evidence or [])
    card_evidence = card_evidence or {}
    page_texts = page_texts or {}
    cards = list(audited_manifest.cards)

    seen_tf: list[str] = []
    for c in cards:
        if c.target_file not in seen_tf:
            seen_tf.append(c.target_file)
    ordered_tf = [tf for tf in _ORDER if tf in seen_tf] + \
                 [tf for tf in seen_tf if tf not in _ORDER]

    fig_counter = 0
    sections: list[Section] = []
    appendix_entries: list[AppendixEntry] = []

    for tf in ordered_tf:
        heading = _heading_for(tf)
        tf_cards = [c for c in cards if c.target_file == tf]
        primary = [c for c in tf_cards if c.audit_status in _PRIMARY]
        quarantined = [c for c in tf_cards if c.audit_status not in _PRIMARY]

        claims: list[Claim] = []
        figures: list[FigureItem] = []
        for c in primary:
            sub = split_compound(c.question)
            text = (c.compiler_slot or _humanize(c.section_key)) if sub \
                else scrub_question(c.question)
            claim = Claim(
                text=text,
                why=(c.why_it_matters or "").strip(),
                status=_STATUS.get(c.audit_status, "verify"),
                sub_items=sub,
                raw=c.question,
            )
            for rec in card_evidence.get(c.question, []):
                meta = getattr(rec, "metadata", {}) or {}
                if not meta.get("figure_path"):
                    continue
                fig_counter += 1
                fid = f"F{fig_counter}"
                cite = meta.get("citation", "")
                figures.append(FigureItem(
                    fig_id=fid,
                    image_path=meta["figure_path"],
                    caption=complete_caption(rec, page_text=page_texts.get(meta["figure_path"])),
                    citation=cite,
                    relevance=relevance_line(text, cite),
                    claim_ref=_short(text),
                ))
                claim.figure_ids.append(fid)
            claims.append(claim)

        if claims or figures:
            sections.append(Section(heading=heading, intro=_INTRO.get(heading, ""),
                                    claims=claims, figures=figures))
        if quarantined:
            items = [
                f"{scrub_question(c.question)} — {c.audit_reason or 'quarantined'}"
                for c in quarantined
            ]
            appendix_entries.append(AppendixEntry(heading=heading, items=items))

    # #9 collapse cross-section near-duplicates
    dedup_sections(sections)

    # #8 evidence sources belong in a real appendix
    citations: list[str] = []
    for rec in evidence:
        meta = getattr(rec, "metadata", {}) or {}
        cite = meta.get("citation")
        if cite and cite not in citations:
            citations.append(cite)
    if citations:
        appendix_entries.append(AppendixEntry(heading="Evidence Sources", sources=citations))

    # #2 single evidence axis (no confidence); one clean partition
    summary = EvidenceSummary(
        supported=sum(1 for c in cards if c.audit_status == "supported"),
        to_verify=sum(1 for c in cards if c.audit_status in ("needs_review", "no_evidence")),
        quarantined=sum(1 for c in cards if c.audit_status == "off_target"),
    )

    title = f"Case Board — {topic}" if topic else "Case Board"
    return Dossier(title=title, summary=summary, sections=sections,
                   appendix=Appendix(entries=appendix_entries))
