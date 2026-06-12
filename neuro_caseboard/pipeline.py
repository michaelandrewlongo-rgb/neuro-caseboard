"""Orchestrate the unified case-prep pipeline.

Reuses caseprep's Explorer -> Enricher -> Auditor stages unchanged, then hands the
AuditedManifest to this project's corrected compile + render surface. Degrades
gracefully: with no retriever every card is a clinician-verify prompt (a valid offline
checklist); with the FTS5 corpus lane, cards earn corpus-supported / quarantined status.
"""

from __future__ import annotations

from pathlib import Path
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
from neuro_caseboard.compile import compile_dossier
from neuro_caseboard.render_md import render_markdown
from neuro_caseboard.render_pdf import render_pdf

_PROFILE_SIGNALS = {
    "spine": ("spine", "spinal", "cervical", "thoracic", "lumbar", "corpectomy",
              "acdf", "laminectomy", "laminoplasty", "discectomy", "fusion",
              "myelopathy", "radiculopathy", "vertebral", "scoliosis", "kyphosis",
              "c1", "c2"),
    "skull_base": ("vestibular schwannoma", "acoustic", "cpa", "cerebellopontine",
                   "retrosigmoid", "translabyrinthine", "petrous", "clivus",
                   "pituitary", "transsphenoidal", "meningioma", "skull base",
                   "cavernous"),
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


def build_manifest(topic: str):
    """Deterministic, offline Explorer: generic rule-based cards (any topic) merged with
    hand-written family templates when the topic matches one. Avoids the KG/LLM adapters
    in build_question_manifest, which block on an unavailable knowledge-graph database.
    """
    profile = classify_profile(topic)
    generic = build_generic_manifest(topic, profile=profile)
    cards = list(generic.cards) if generic else []

    key = _detect_manifest_key("", topic)
    if key and key in _FAMILY_MANIFESTS:
        template_cards = []
        for section_cards in _FAMILY_MANIFESTS[key].values():
            template_cards.extend(section_cards)
        cards = _merge_cards(template_cards, cards)  # hand-written templates take priority

    return QuestionManifest(procedure_family=key or profile or "generic", cards=cards), profile


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


def build_dossier(topic: str, *, enrich: bool = True):
    """Run the full pipeline and return a compiled Dossier."""
    manifest, _profile = build_manifest(topic)
    retriever = build_retriever() if enrich else None
    enriched = enrich_manifest(manifest, topic=topic, retriever=retriever, top_n=3)
    audited = audit_manifest(enriched, topic=topic)
    evidence = _sources_from_audited(audited)
    return compile_dossier(audited, topic=topic, evidence=evidence)


def _slug(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (topic or "").lower()).strip("-")[:40] or "case"


def generate(topic: str, *, output_dir, pdf: bool = False, enrich: bool = True):
    """Build a dossier and write case-board.md (+ case-board.pdf) to output_dir."""
    dossier = build_dossier(topic, enrich=enrich)
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
