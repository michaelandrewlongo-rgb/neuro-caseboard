"""Orchestrate the unified case-prep pipeline.

Reuses caseprep's Explorer -> Enricher -> Auditor stages unchanged, then hands the
AuditedManifest to this project's corrected compile + render surface. Degrades
gracefully: with no retriever every card is a clinician-verify prompt (a valid offline
checklist); with the FTS5 corpus lane, cards earn corpus-supported / quarantined status.
"""

from __future__ import annotations

from pathlib import Path
import os
import re

from caseprep.explorer.question_manifest import (
    build_generic_manifest,
    QuestionManifest,
    _detect_manifest_key,
    _FAMILY_MANIFESTS,
    _merge_cards,
)
from caseprep.enrichment.corpus_enricher import enrich_manifest
from caseprep.audit.card_auditor import audit_manifest
from caseprep.core.contracts import EvidenceRecord

from neuro_caseboard.retrieve import build_retriever
from neuro_caseboard.guard import prune_offtarget
from neuro_caseboard.compile import compile_dossier
from neuro_caseboard.render_md import render_markdown
from neuro_caseboard.render_pdf import render_pdf

_PROFILE_SIGNALS = {
    "spine": ("spine", "spinal", "cervical", "thoracic", "lumbar", "corpectomy",
              "acdf", "laminectomy", "laminoplasty", "discectomy", "fusion",
              "myelopathy", "radiculopathy", "vertebral", "scoliosis", "kyphosis",
              "c1", "c2"),
    # NOTE: bare "meningioma" is deliberately excluded — it is location-dependent
    # (a convexity meningioma is not skull base). True skull-base meningiomas still
    # match via petrous/clivus/cpa/cavernous/etc.
    "skull_base": ("vestibular schwannoma", "acoustic", "cpa", "cerebellopontine",
                   "retrosigmoid", "translabyrinthine", "petrous", "clivus",
                   "pituitary", "transsphenoidal", "skull base", "cavernous"),
    "vascular": ("aneurysm", "avm", "carotid", "endarterectomy", "thrombectomy",
                 "bypass", "clipping", "coiling", "arteriovenous", "moyamoya",
                 "fistula", "embolization"),
}


def classify_profile(topic: str) -> str:
    t = (topic or "").lower()
    for profile, signals in _PROFILE_SIGNALS.items():
        if any(s in t for s in signals):
            return profile
    return ""


def llm_enabled() -> bool:
    """LLM Explorer is used when a key is configured and not explicitly disabled."""
    from neuro_caseboard.explore_llm import llm_available
    return llm_available() and os.environ.get("CASEBOARD_LLM", "1") != "0"


def _deterministic_manifest(topic: str, profile: str):
    """Offline Explorer: generic rule-based cards (any topic) merged with hand-written
    family templates when the topic matches one. Avoids the KG/LLM adapters in
    build_question_manifest, which block on an unavailable knowledge-graph database."""
    generic = build_generic_manifest(topic, profile=profile)
    cards = list(generic.cards) if generic else []
    key = _detect_manifest_key("", topic)
    if key and key in _FAMILY_MANIFESTS:
        template_cards = []
        for section_cards in _FAMILY_MANIFESTS[key].values():
            template_cards.extend(section_cards)
        cards = _merge_cards(template_cards, cards)  # hand-written templates take priority
    return QuestionManifest(procedure_family=key or profile or "generic", cards=cards)


def build_manifest(topic: str, *, use_llm=None):
    """Build the question manifest for *topic*.

    Clinical depth comes from the LLM Explorer (case-specific cards for any procedure)
    when a key is available; otherwise the deterministic generator. Either way the result
    passes through the anti-bleed guard, which strips cross-region content. Returns
    ``(manifest, profile)``.
    """
    profile = classify_profile(topic)
    if use_llm is None:
        use_llm = llm_enabled()

    llm_manifest = None
    if use_llm:
        from neuro_caseboard.explore_llm import build_llm_manifest
        try:
            llm_manifest = build_llm_manifest(topic)
        except Exception:
            llm_manifest = None

    if llm_manifest is not None and llm_manifest.cards:
        # Merge curated hand-written family templates (which outperform a general model on
        # their own family) as a high-priority floor; the LLM fills the long tail and the
        # subspecialties no template covers.
        cards = list(llm_manifest.cards)
        key = _detect_manifest_key("", topic)
        if key and key in _FAMILY_MANIFESTS:
            template_cards = [c for cs in _FAMILY_MANIFESTS[key].values() for c in cs]
            cards = _merge_cards(template_cards, cards)  # templates win their slots
        manifest = QuestionManifest(
            procedure_family=("llm+template" if key else "llm_generated"), cards=cards)
    else:
        manifest = _deterministic_manifest(topic, profile)

    return prune_offtarget(manifest, topic), profile


def _sources_from_audited(audited, *, limit: int = 15):
    seen: set[str] = set()
    out: list[EvidenceRecord] = []
    for c in audited.cards:
        for p in c.papers or []:
            title = (p.get("title") or "").strip()
            if title and title not in seen:
                seen.add(title)
                out.append(EvidenceRecord(
                    id=str(p.get("id", "src")), source=str(p.get("source", "corpus")),
                    title=title, metadata={"citation": title}))
                if len(out) >= limit:
                    return out
    return out


def build_dossier(topic: str, *, enrich: bool = True, use_llm=None):
    """Run the full pipeline and return a compiled Dossier."""
    manifest, _profile = build_manifest(topic, use_llm=use_llm)
    retriever = build_retriever() if enrich else None
    enriched = enrich_manifest(manifest, topic=topic, retriever=retriever, top_n=3)
    audited = audit_manifest(enriched, topic=topic)
    evidence = _sources_from_audited(audited)
    return compile_dossier(audited, topic=topic, evidence=evidence)


def _slug(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (topic or "").lower()).strip("-")[:40] or "case"


def generate(topic: str, *, output_dir, pdf: bool = False, enrich: bool = True, use_llm=None):
    """Build a dossier and write case-board.md (+ case-board.pdf) to output_dir."""
    dossier = build_dossier(topic, enrich=enrich, use_llm=use_llm)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    md_path = out / "case-board.md"
    md_path.write_text(render_markdown(dossier), encoding="utf-8")
    artifacts["markdown"] = md_path
    if pdf:
        art = render_pdf(dossier, out / "case-board.pdf")
        artifacts["pdf"] = Path(art.path)
    return dossier, artifacts
