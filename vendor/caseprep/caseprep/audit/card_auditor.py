"""Auditor: validate enriched question cards against attached corpus evidence.

Takes an EnrichedManifest (cards + papers from corpus), validates each claim
against its evidence, and produces an AuditedManifest with each card marked as:

- ``supported`` — evidence directly addresses the question
- ``off_target`` — papers exist but are clinically wrong
- ``no_evidence`` — no papers were found or enrichment was skipped
- ``needs_review`` — borderline; Auditor cannot confidently classify

Design rule: the Auditor should default to ``needs_review`` rather than
falsely marking a claim as ``off_target``.  Reject a paper only when its
clinical domain clearly contradicts the case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from caseprep.core.contracts import SlotConfidence


# ── data contracts ───────────────────────────────────────────────────────────


@dataclass
class AuditedCard:
    """A question card with Auditor validation."""

    question: str
    why_it_matters: str
    target_file: str
    section_key: str
    compiler_slot: str
    answerability: str

    audit_status: str = "no_evidence"
    audit_reason: str = ""
    supporting_paper_ids: list[str] = field(default_factory=list)
    confidence: Optional[SlotConfidence] = None
    contradicting_paper_ids: list[str] = field(default_factory=list)
    papers: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "why_it_matters": self.why_it_matters,
            "target_file": self.target_file,
            "section_key": self.section_key,
            "compiler_slot": self.compiler_slot,
            "answerability": self.answerability,
            "audit_status": self.audit_status,
            "audit_reason": self.audit_reason,
            "supporting_paper_ids": self.supporting_paper_ids,
            "contradicting_paper_ids": self.contradicting_paper_ids,
            "papers": self.papers,
        }


@dataclass
class AuditedManifest:
    """Explorer manifest after Auditor validation."""

    procedure_family: str
    cards: list[AuditedCard] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "procedure_family": self.procedure_family,
            "cards": [card.to_dict() for card in self.cards],
        }


# ── accepted / rejected partition ────────────────────────────────────────────
#
# The single gate every consumer must use before turning a card's retrieved papers into
# citations, "supported" grounding, or appendix entries. A card that is marked ``supported``
# can still carry an off-target paper in ``contradicting_paper_ids`` (supported wins when a
# card has both supporting AND contradicting papers), so the card stays in the primary dossier
# — it is NOT quarantined. Exporting *all* of ``card.papers`` therefore leaks the off-target
# source. These accessors project the Auditor's own id partition back onto the paper dicts so
# the leak cannot happen: only ``accepted_papers`` may be cited; ``rejected_papers`` belong in
# a separate appendix section.


def _paper_id(paper: Any) -> Any:
    """The id the Auditor keyed on (``paper.get("id", "")``), duck-typed for dict or object."""
    if isinstance(paper, dict):
        return paper.get("id", "")
    return getattr(paper, "id", "")


def rejected_papers(card: Any) -> list:
    """Papers the Auditor flagged as contradicting the case's clinical domain (off-target).

    These must never become a citation or "supported" grounding; they belong in a separate
    appendix section. Returns the paper dicts (a subset of ``card.papers``)."""
    rejected_ids = set(getattr(card, "contradicting_paper_ids", None) or [])
    if not rejected_ids:
        return []
    return [p for p in (getattr(card, "papers", None) or []) if _paper_id(p) in rejected_ids]


def accepted_papers(card: Any) -> list:
    """Papers the Auditor did NOT flag as contradicting — the only papers eligible to create
    a citation or "supported" grounding.

    Accepted = ``card.papers`` minus ``rejected_papers`` (i.e. the supporting papers plus the
    still-uncertain ``needs_review`` middle). Using the precise ``contradicting_paper_ids``
    signal — rather than a stricter "supporting only" rule — removes exactly the leaked
    off-target papers while leaving already-correct retrieved citations untouched."""
    rejected_ids = set(getattr(card, "contradicting_paper_ids", None) or [])
    return [p for p in (getattr(card, "papers", None) or []) if _paper_id(p) not in rejected_ids]


# ── domain lexicon ───────────────────────────────────────────────────────────

# Positive signals: terms that indicate the paper is in a specific clinical
# domain.  Matched against both the case topic and paper text.
_DOMAIN_LEXICON: dict[str, tuple[str, ...]] = {
    "tumor_craniotomy": (
        "glioma", "glioblastoma", "gbm", "astrocytoma", "oligodendroglioma",
        "meningioma", "schwannoma", "metastasis", "tumor resection",
        "craniotomy", "awake craniotomy", "awake surgery",
        "motor mapping", "language mapping", "cortical stimulation",
        "direct electrical stimulation", "eloquent cortex", "eloquent",
        "perirolandic", "motor strip", "central sulcus",
        "extent of resection", "eor", "gtr", "gross total",
        "supratentorial", "convexity", "parietal", "frontal", "temporal",
    ),
    "spine": (
        "spine", "spinal", "cervical", "thoracic", "lumbar", "cord",
        "laminectomy", "laminoplasty", "discectomy", "fusion",
        "pedicle", "facet", "foramen", "stenosis", "myelopathy",
        "radiculopathy", "c1", "c2", "craniocervical",
        "vertebral artery", "far lateral", "far-lateral",
    ),
    "cranial_skull_base": (
        "cpa", "cerebellopontine", "acoustic neuroma", "vestibular schwannoma",
        "retrosigmoid", "translabyrinthine", "internal auditory canal",
        "skull base", "pituitary", "transsphenoidal", "clivus",
        "petrous", "cavernous sinus", "trigeminal",
    ),
    "vascular": (
        "aneurysm", "avm", "thrombectomy", "coiling", "clipping",
        "mca", "ica", "aca", "pca", "basilar", "stroke",
        "large vessel occlusion", "lvo", "embolization",
        "flow diversion", "stent retriever", "aspiration thrombectomy",
        "tici", "mtici", "nihss", "aspects",
    ),
}

# Hard off-target signals: these terms in a paper indicate it is in a
# DIFFERENT clinical domain and should trigger quarantine.
_DOMAIN_CONTRADICTIONS: dict[str, tuple[str, ...]] = {
    "spine": (
        "cerebellopontine", "acoustic neuroma", "vestibular schwannoma",
        "trigeminal", "cavernous sinus", "pituitary", "transsphenoidal",
        "pterional", "sylvian", "aneurysm clipping",
    ),
    "cranial_skull_base": (
        "laminectomy", "laminoplasty", "pedicle screw", "discectomy",
        "fusion", "cervical spine", "lumbar spine", "acdf",
        "thrombectomy", "stent retriever",
    ),
    "tumor_craniotomy": (
        "thrombectomy", "stent retriever", "coiling", "clipping",
        "pedicle screw", "acdf", "discectomy",
    ),
    "vascular": (
        "meningioma", "glioma", "glioblastoma", "schwannoma",
        "gtr", "gross total resection", "awake craniotomy",
        "laminectomy", "acdf",
    ),
}


# ── keyword extraction ───────────────────────────────────────────────────────


def _extract_domain_terms(text: str) -> set[str]:
    """Extract domain-signalling terms from text."""
    lower = text.lower()
    found: set[str] = set()
    for terms in _DOMAIN_LEXICON.values():
        for term in terms:
            if term in lower:
                found.add(term)
    return found


def _extract_contradiction_terms(text: str, expected_domain: str) -> set[str]:
    """Extract terms that contradict the expected domain.

    Only checks the contradiction list for *this specific domain* —
    i.e., terms that should NOT appear in a paper supporting a case
    of this domain.  For a tumor_craniotomy case, we check for
    thrombectomy/coiling/spine terms in the paper, not vice versa.
    """
    if not expected_domain:
        return set()
    terms = _DOMAIN_CONTRADICTIONS.get(expected_domain, ())
    lower = text.lower()
    return {t for t in terms if t in lower}


def _detect_domain(text: str) -> str | None:
    """Detect which clinical domain a text belongs to, by term density."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for domain, terms in _DOMAIN_LEXICON.items():
        score = sum(1 for t in terms if t in lower)
        if score > 0:
            scores[domain] = score
    if not scores:
        return None
    # pyright: ignore — scores.get is a valid key function
    return max(scores, key=lambda k: scores[k])


def _paper_text(paper: dict[str, Any]) -> str:
    """Get the searchable text from a paper summary."""
    return f"{paper.get('title', '')} {paper.get('text_snippet', '')}"


# ── audit logic ──────────────────────────────────────────────────────────────


def _audit_card(card, *, topic: str) -> AuditedCard:
    """Audit a single enriched card against its attached papers."""
    ac = AuditedCard(
        question=card.question,
        why_it_matters=card.why_it_matters,
        target_file=card.target_file,
        section_key=card.section_key,
        compiler_slot=card.compiler_slot,
        answerability=card.answerability,
        papers=card.papers,
        confidence=card.confidence,
    )


    if card.enrichment_status != "success" or not card.papers:
        ac.audit_status = "no_evidence"
        ac.audit_reason = "no corpus evidence available for this question"
        return ac

    # Determine the expected clinical domain from the case topic
    case_domain = _detect_domain(topic)  # e.g. "tumor_craniotomy"

    # Combined question + why_it_matters text for domain matching
    full_question_text = f"{card.question} {card.why_it_matters}"

    supported: list[str] = []
    off_target: list[str] = []

    for paper in card.papers:
        pid = paper.get("id", "")
        pt = _paper_text(paper)
        paper_domain = _detect_domain(pt)

        # ▸ Positive signal: paper domain matches case domain
        domain_match = bool(case_domain and paper_domain == case_domain)

        # ▸ Negative signal: paper has contradiction terms for case domain
        contradictions = (
            _extract_contradiction_terms(pt, case_domain or "")
            if case_domain else set()
        )

        # ▸ Question-relevance: do the question's domain terms appear in the paper?
        question_terms = _extract_domain_terms(full_question_text)
        paper_terms = _extract_domain_terms(pt)
        term_overlap = question_terms & paper_terms

        # Decision logic:
        # - Contradictions present → off_target (wrong domain)
        # - Domain match + term overlap → supported (right domain, relevant)
        # - Domain match + no overlap → needs_review (right domain, unsure)
        # - No domain match + term overlap → needs_review (some signal)
        # - Neither → unclassified, falls through to needs_review

        if contradictions:
            off_target.append(pid)
        elif domain_match and term_overlap:
            supported.append(pid)
        elif domain_match:
            # Right clinical domain, but no specific term match with
            # this question — might be relevant, Auditor isn't sure.
            pass  # falls through to needs_review
        elif term_overlap:
            # Some keyword signal but wrong domain — uncertain.
            pass  # falls through to needs_review
        # else: neither — falls through to needs_review

    if supported:
        ac.audit_status = "supported"
        ac.audit_reason = (
            f"{len(supported)} papers in matching clinical domain "
            f"({case_domain or 'unknown'})"
        )
        ac.supporting_paper_ids = supported
        ac.contradicting_paper_ids = off_target
    elif off_target and not supported:
        ac.audit_status = "off_target"
        ac.audit_reason = (
            f"{len(off_target)} papers contradict expected domain "
            f"({case_domain or 'unknown'})"
        )
        ac.contradicting_paper_ids = off_target
    else:
        ac.audit_status = "needs_review"
        ac.audit_reason = (
            "insufficient domain signal for confident classification"
        )

    return ac


# ── public API ───────────────────────────────────────────────────────────────


def audit_manifest(
    enriched_manifest,  # EnrichedManifest
    *,
    topic: str = "",
) -> AuditedManifest:
    """Validate every enriched card against its attached evidence.

    Uses clinical domain matching: papers in the same domain as the case
    topic are considered relevant even without exact keyword overlap.
    Papers from clearly different clinical domains are quarantined.
    """
    audited_cards = [_audit_card(card, topic=topic) for card in enriched_manifest.cards]
    return AuditedManifest(
        procedure_family=enriched_manifest.procedure_family,
        cards=audited_cards,
    )
