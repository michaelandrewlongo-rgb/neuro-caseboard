"""Corpus-backed enrichment of Explorer question cards.

Each question card from the Explorer manifest is transformed into a semantic
search query against the local neurosurgery corpus.  Retrieved evidence is
attached to the card so the Auditor can validate/reject claims, and the
Compiler can surface provenance without making the primary dossier feel like
an audit ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Optional
from caseprep.core.contracts import EvidenceRecord, SlotConfidence

# ── retriever protocol ───────────────────────────────────────────────────────


class SemanticRetriever(Protocol):
    """Minimal protocol the enricher needs."""

    def retrieve(
        self,
        query: str,
        *,
        top_n: int = 5,
        subdomain: str | None = None,
    ) -> list[EvidenceRecord]:
        ...


# ── enriched data contracts ──────────────────────────────────────────────────


@dataclass
class EnrichedCard:
    """A question card with corpus evidence attached."""

    question: str
    why_it_matters: str
    target_file: str
    section_key: str
    compiler_slot: str
    answerability: str

    # enrichment results
    search_query: str = ""
    enrichment_status: str = "skipped"  # success | no_results | skipped | error
    papers: list[dict[str, Any]] = field(default_factory=list)
    confidence: Optional[SlotConfidence] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "why_it_matters": self.why_it_matters,
            "target_file": self.target_file,
            "section_key": self.section_key,
            "compiler_slot": self.compiler_slot,
            "answerability": self.answerability,
            "search_query": self.search_query,
            "enrichment_status": self.enrichment_status,
            "papers": self.papers,
        }


@dataclass
class EnrichedManifest:
    """Explorer manifest with corpus evidence attached to each card."""

    procedure_family: str
    cards: list[EnrichedCard] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "procedure_family": self.procedure_family,
            "cards": [card.to_dict() for card in self.cards],
        }


# ── paper serialisation ──────────────────────────────────────────────────────


def _paper_summary(record: EvidenceRecord, rank: int) -> dict[str, Any]:
    """Extract a lightweight summary suitable for the Auditor to review."""
    return {
        "rank": rank,
        "id": record.id,
        "title": record.title[:200] if record.title else "",
        "source": record.source,
        "text_snippet": " ".join((record.text or "").split())[:500],
        "year": str(record.metadata.get("pubdate", "") or ""),
    }


# ── query construction ───────────────────────────────────────────────────────


def _build_card_query(question: str, topic: str) -> str:
    """Construct a clean semantic-search query from a question card.

    Strips formatting tokens (VERIFY:, [needs_patient_fact]) and appends
    the case topic for clinical grounding.
    """
    cleaned = question
    for token in ("VERIFY:", "[needs_patient_fact]", "[needs_evidence]"):
        cleaned = cleaned.replace(token, "")
    cleaned = " ".join(cleaned.split())  # normalise whitespace
    if topic and topic.strip():
        cleaned = f"{cleaned} {topic.strip()}"
    # Keep queries concise — semantic search works well with short phrases
    if len(cleaned) > 300:
        cleaned = cleaned[:300].rsplit(" ", 1)[0]
    return cleaned


# ── public API ───────────────────────────────────────────────────────────────


def enrich_manifest(
    manifest,  # QuestionManifest (from explorer.question_manifest)
    *,
    topic: str,
    retriever: SemanticRetriever | None = None,
    top_n: int = 3,
) -> EnrichedManifest:
    """Attach corpus evidence to each question card.

    Args:
        manifest: Explorer's QuestionManifest (has ``.cards`` list of
                  QuestionCard with ``.question``, ``.why_it_matters``, etc.)
        topic: The raw case topic string for query grounding.
        retriever: A semantic corpus retriever.  If ``None``, all cards
                   are marked ``skipped``.
        top_n: Max papers per card.

    Returns an EnrichedManifest with evidence-attached cards.
    """
    enriched_cards: list[EnrichedCard] = []
    can_enrich = retriever is not None

    for card in manifest.cards:
        ec = EnrichedCard(
            question=card.question,
            why_it_matters=card.why_it_matters,
            target_file=card.target_file,
            section_key=card.section_key,
            compiler_slot=card.compiler_slot,
            answerability=card.answerability,
        )

        if not can_enrich:
            enriched_cards.append(ec)
            continue

        query = _build_card_query(card.question, topic)
        ec.search_query = query

        try:
            results = retriever.retrieve(query, top_n=top_n)
        except Exception:
            ec.enrichment_status = "error"
            enriched_cards.append(ec)
            continue

        if not results:
            ec.enrichment_status = "no_results"
            enriched_cards.append(ec)
            continue

        ec.enrichment_status = "success"
        ec.papers = [
            _paper_summary(record, idx + 1)
            for idx, record in enumerate(results)
        ]
        enriched_cards.append(ec)

    return EnrichedManifest(
        procedure_family=getattr(manifest, "procedure_family", "unknown"),
        cards=enriched_cards,
    )
