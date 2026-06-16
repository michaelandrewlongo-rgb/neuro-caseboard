"""Orchestrate the unified case-prep pipeline.

Reuses caseprep's Explorer -> Enricher -> Auditor stages unchanged, then hands the
AuditedManifest to this project's corrected compile + render surface. Degrades
gracefully: with no retriever every card is a clinician-verify prompt (a valid offline
checklist); with the FTS5 corpus lane, cards earn corpus-supported / quarantined status.
"""

from __future__ import annotations

from pathlib import Path
import logging
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


def _fig_query(question: str, topic: str) -> str:
    return f"{topic} {question}"


def _collect_figures(manifest, topic, retriever=None, *, figret=None,
                     max_total: int = 8, per_card: int = 1):
    """Gather figure-bearing evidence (textbook page images + captions) for the cards.

    Returns ``(card_evidence, page_texts)`` where card_evidence maps a card's question to
    its figure EvidenceRecords (compile turns these into inline FigureItems with a
    bidirectional claim<->figure cross-link) and page_texts maps the image path to the
    figure page's full text so the complete caption can be reassembled. Each page image is
    used at most once per board and the board is capped at ``max_total`` figures."""
    from neuro_caseboard.retrieve import build_figure_retriever
    if figret is None:
        figret = build_figure_retriever()       # caption-ranked lane (preferred)
    card_evidence: dict = {}
    page_texts: dict = {}
    used: set = set()
    total = 0
    for card in manifest.cards:
        if total >= max_total:
            break
        # figures earn their place on anatomy claims (named structures/landmarks/vessels),
        # not on generic operative steps like positioning/closure that pull OR-setup noise.
        if getattr(card, "target_file", "") != "03-anatomy-at-risk.md":
            continue
        try:
            if figret is not None:
                recs = figret.retrieve(_fig_query(card.question, topic), topic=topic, top_n=4)
            elif retriever is not None:
                recs = retriever.retrieve(_fig_query(card.question, topic), top_n=4)
            else:
                recs = []
        except Exception:
            continue
        picked = []
        for r in recs or []:
            meta = getattr(r, "metadata", {}) or {}
            fp = meta.get("figure_path")
            if not fp or fp in used:
                continue
            picked.append(r)
            used.add(fp)
            page_texts[fp] = getattr(r, "text", "") or ""
            total += 1
            if len(picked) >= per_card or total >= max_total:
                break
        if picked:
            card_evidence[card.question] = picked
    return card_evidence, page_texts


def _figures_enabled() -> bool:
    return os.environ.get("CASEBOARD_TEXTBOOK_FIGURES", "1") != "0"


def build_dossier(topic: str, *, enrich: bool = True, use_llm=None):
    """Run the full pipeline and return a compiled Dossier."""
    manifest, _profile = build_manifest(topic, use_llm=use_llm)
    retriever = build_retriever() if enrich else None
    enriched = enrich_manifest(manifest, topic=topic, retriever=retriever, top_n=3)
    audited = audit_manifest(enriched, topic=topic)
    evidence = _sources_from_audited(audited)
    card_evidence, page_texts = ({}, {})
    if retriever is not None and _figures_enabled():
        card_evidence, page_texts = _collect_figures(manifest, topic, retriever)
    return compile_dossier(audited, topic=topic, evidence=evidence,
                           card_evidence=card_evidence, page_texts=page_texts)


def build_case_dossier(case, *, enrich: bool = True, use_llm=None, literature=None,
                       lit_client=None, lit_synth_client=None, lit_cache=None,
                       figures_dir=None, fig_complete_fn=None):
    """Case path: a CaseContext -> the 8-section case Dossier.

    Mirrors build_dossier but authors over the eight case surfaces (build_case_manifest) and
    compiles with compile_case_dossier. Reuses the same anti-bleed guard, enricher, auditor, and
    retriever as build — degrades to a clinician-verify checklist offline. ``case.to_topic()`` is
    the bridge that keeps classify_profile / retrieval working off the structured context.

    When ``literature`` (None -> the LITERATURE_RETRIEVAL config flag), the Reasoning / Alternatives
    / Risks sections are augmented with a contemporary-PubMed paragraph on a separate ``[L#]`` axis
    (WS-3); the lit client/synth/cache are injectable for offline tests. The lane is additive — any
    failure leaves those sections without a literature block and never affects the rest.
    """
    from neuro_caseboard.case_author import build_case_manifest, deterministic_case_manifest
    from neuro_caseboard.compile import compile_case_dossier

    if use_llm is None:
        use_llm = llm_enabled()
    manifest = build_case_manifest(case) if use_llm else deterministic_case_manifest(case)
    topic = case.to_topic()
    manifest = prune_offtarget(manifest, topic)        # anti-bleed (LOOP_PROMPT §6)

    retriever = build_retriever() if enrich else None
    enriched = enrich_manifest(manifest, topic=topic, retriever=retriever, top_n=3)
    audited = audit_manifest(enriched, topic=topic)
    evidence = _sources_from_audited(audited)
    card_evidence, page_texts = ({}, {})
    if retriever is not None and _figures_enabled():
        card_evidence, page_texts = _collect_figures(manifest, topic, retriever)
    dossier = compile_case_dossier(audited, case=case, evidence=evidence,
                                   card_evidence=card_evidence, page_texts=page_texts)

    if literature is None:
        from neuro_caseboard.literature.config import load_literature_config
        literature = load_literature_config().enabled
    if literature:
        from neuro_caseboard.case_literature import attach_case_literature
        attach_case_literature(dossier, case, client=lit_client,
                               synth_client=lit_synth_client, cache=lit_cache)

    # WS-4: generated case schematics (deterministic PIL renderer; offline-safe). Attached to the
    # "Case Figures" section as FigureItems alongside any retrieved plates.
    if figures_dir is not None:
        from neuro_caseboard.figures_gen import generate_case_figures
        items = generate_case_figures(case, figures_dir, complete_fn=fig_complete_fn)
        if items:
            fig_sec = next((s for s in dossier.sections if s.heading == "Case Figures"), None)
            if fig_sec is None:
                from neuro_caseboard.model import Section
                fig_sec = Section(heading="Case Figures",
                                  intro="Generated schematics for this case.")
                dossier.sections.append(fig_sec)
            fig_sec.figures.extend(items)
    return dossier


def _slug(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (topic or "").lower()).strip("-")[:40] or "case"


def _exec_renderer_unavailable(exc: Exception) -> bool:
    """True only for the *expected* "can't render here" cases — Playwright not installed
    (``ImportError``) or its Chromium binary missing / failing to launch (a ``playwright.*``
    error) — so we fall back to fpdf2. Genuine bugs in the exec renderer (``AttributeError``,
    ``KeyError``, …) return False and are re-raised instead of being masked behind a silently
    degraded PDF."""
    if isinstance(exc, ImportError):
        return True
    return (type(exc).__module__ or "").startswith("playwright")


def render_case_pdf(dossier, topic, path):
    """Render the case-board PDF — the single source of truth for every ``build`` pathway
    (CLI ``caseboard build --pdf`` and the Streamlit Build lane).

    Default is the Executive-Navy design that matches the web console (``caseboard_pdf``,
    HTML->PDF via Playwright/Chromium). Falls back to the offline fpdf2 renderer when the exec
    renderer is unavailable (e.g. no Chromium in CI) or when ``CASEBOARD_PDF_STYLE=clinical`` is
    set. Returns the written path."""
    style = os.environ.get("CASEBOARD_PDF_STYLE", "exec").strip().lower()
    if style != "clinical":
        try:
            from neuro_caseboard.caseboard_pdf import render_caseboard_pdf
            render_caseboard_pdf(dossier, path, subtitle=topic)
            return Path(path)
        except Exception as e:
            if not _exec_renderer_unavailable(e):
                raise  # a real bug in the exec renderer — surface it, don't mask it
            logging.getLogger(__name__).warning(
                "Executive-Navy PDF renderer unavailable (%r); using the clinical fpdf2 "
                "fallback.", e)
    art = render_pdf(dossier, path)
    return Path(art.path)


def render_ask_pdf(result, question, path):
    """Render the ask (Q&A) PDF — the single source of truth for every ``ask`` pathway
    (CLI ``caseboard ask --pdf`` and the Streamlit Ask lane).

    Default is the Executive-Navy briefing that matches the web console (``briefing_pdf``,
    HTML->PDF via Playwright/Chromium). Falls back to the offline fpdf2 renderer when the exec
    renderer is unavailable (e.g. no Chromium in CI) or when ``CASEBOARD_PDF_STYLE=clinical`` is
    set. Returns the written path."""
    style = os.environ.get("CASEBOARD_PDF_STYLE", "exec").strip().lower()
    if style != "clinical":
        try:
            from neuro_caseboard.briefing_pdf import render_briefing_pdf
            render_briefing_pdf(result, path, title=question)
            return Path(path)
        except Exception as e:
            if not _exec_renderer_unavailable(e):
                raise  # a real bug in the exec renderer — surface it, don't mask it
            logging.getLogger(__name__).warning(
                "Executive-Navy ask PDF renderer unavailable (%r); using the clinical fpdf2 "
                "fallback.", e)
    from neuro_caseboard.briefing_pdf import render_briefing_clinical_pdf
    render_briefing_clinical_pdf(result, path, title=question)
    return Path(path)


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
        artifacts["pdf"] = render_case_pdf(dossier, topic, out / "case-board.pdf")
    return dossier, artifacts
