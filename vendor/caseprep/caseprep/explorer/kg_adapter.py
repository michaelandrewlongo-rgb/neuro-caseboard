"""PAPERS Knowledge Graph adapter for Explorer template generation.

Queries the PAPERS PostgreSQL knowledge graph (``kg_concepts``, ``kg_facts``,
``kg_edges``) to auto-generate procedure-family-specific question cards.

Each KG fact (``claim_text`` + ``confidence`` + ``work_id``) becomes a
QuestionCard with evidence already attached — no hand-written templates needed
when the KG has coverage for a procedure.

Graceful fallback: returns ``None`` when the KG is unavailable, so the
Explorer falls through to hand-written or generic templates.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest

logger = logging.getLogger(__name__)

# ── connection management ────────────────────────────────────────────────────

_KG_URL_ENV = "PAPERS_CORPUS_DB_URL"
_DEFAULT_KG_URL = (
    "postgresql+psycopg://corpus_pipeline:corpus_pipeline@127.0.0.1:5432/"
    "corpus_pipeline"
)
_CONNECTION = None  # lazy singleton


def _parse_db_url(url: str) -> dict[str, str]:
    """Convert SQLAlchemy URL to psycopg2 kwargs."""
    m = re.match(
        r"postgresql(?:\+psycopg)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)",
        url,
    )
    if not m:
        raise ValueError(f"Unsupported DB URL format: {url[:60]}")
    user, pwd, host, port, db = m.groups()
    return {"host": host, "port": int(port), "dbname": db, "user": user, "password": pwd}


def _get_connection():
    """Lazy singleton connection.  Returns None if KG is unavailable."""
    global _CONNECTION
    if _CONNECTION is not None:
        return _CONNECTION
    try:
        import psycopg2  # noqa: F811
    except ImportError:
        logger.debug("psycopg2 not installed — KG adapter disabled")
        return None

    url = os.environ.get(_KG_URL_ENV, _DEFAULT_KG_URL)
    try:
        kwargs = _parse_db_url(url)
        _CONNECTION = psycopg2.connect(**kwargs)
        logger.info("Connected to PAPERS KG at %s:%s", kwargs["host"], kwargs["port"])
    except Exception as exc:
        logger.debug("KG connection failed: %s", exc)
        _CONNECTION = None  # remain None so we don't retry every call
    return _CONNECTION


def _kg_available() -> bool:
    return _get_connection() is not None


# ── edge-type → section mapping ──────────────────────────────────────────────

_EDGE_TO_SECTION: dict[str, dict[str, str]] = {
    # Anatomy / pathology context edges
    "INVOLVES": {
        "target_file": "03-anatomy-at-risk.md",
        "section_key": "neural_structures",
        "compiler_slot": "Neural Structures",
    },
    "SUBTYPE_OF": {
        "target_file": "03-anatomy-at-risk.md",
        "section_key": "neural_structures",
        "compiler_slot": "Neural Structures",
    },
    # Operative / decision edges
    "PROCEDURE_FOR": {
        "target_file": "04-operative-plan.md",
        "section_key": "decision_points",
        "compiler_slot": "Decision Points",
    },
    "TREATS": {
        "target_file": "04-operative-plan.md",
        "section_key": "decision_points",
        "compiler_slot": "Decision Points",
    },
    "RELATED_TO": {
        "target_file": "04-operative-plan.md",
        "section_key": "decision_points",
        "compiler_slot": "Decision Points",
    },
    "DIFFERENTIAL_FOR": {
        "target_file": "04-operative-plan.md",
        "section_key": "decision_points",
        "compiler_slot": "Decision Points",
    },
    # Risk / complication edges (merged distinction)
    "COMPLICATES": {
        "target_file": "05-risk-and-rescue.md",
        "section_key": "likely_complications",
        "compiler_slot": "Likely Complications",
    },
    "COMPLICATION_OF": {
        "target_file": "05-risk-and-rescue.md",
        "section_key": "likely_complications",
        "compiler_slot": "Likely Complications",
    },
}


# ── topic → KG concept matching ─────────────────────────────────────────────


_STOP_WORDS: frozenset[str] = frozenset({
    "for", "near", "with", "and", "the", "in", "on", "to", "of",
    "a", "an", "is", "at", "by", "or", "from", "as", "has", "was",
    "due", "via",
})


def _match_concepts(topic: str, limit: int = 5) -> list[dict[str, Any]]:
    """Find KG concepts matching the case topic."""
    conn = _get_connection()
    if conn is None:
        return []

    # Normalise topic for matching: lowercase, strip trailing punct
    clean = topic.lower().rstrip(".,;:!?")

    # Extract key clinical terms, filtering stop words and short tokens
    all_terms = re.split(r"[,\s]+", clean)
    terms = [t for t in all_terms if len(t) > 3 and t not in _STOP_WORDS]
    if not terms:
        # fallback: try 2-char terms (e.g. "C1", "C2")
        terms = [t for t in all_terms if len(t) >= 2 and t not in _STOP_WORDS]
    if not terms:
        return []

    # Prefer multi-word phrase matches (adjacent terms in the topic)
    bigrams = [" ".join(all_terms[i:i+2]) for i in range(len(all_terms)-1)
               if len(all_terms[i]) > 3 and all_terms[i] not in _STOP_WORDS]

    # Combine phrases + single terms for matching, phrases first
    search_terms = bigrams[:3] + [t for t in terms if t not in " ".join(bigrams[:3])]
    search_terms = search_terms[:5]  # limit

    # Score-based matching: count how many clinical terms match each concept.
    # Require at least 2 term matches.  Rank by match count, tie-break by
    # shorter name (more specific concepts tend to have shorter names).
    search_terms = terms[:6]  # max 6 terms to check
    if len(search_terms) < 2:
        return []

    # Build a CASE expression that counts matching terms
    score_parts = " + ".join(
        f"CASE WHEN LOWER(c.name) LIKE %s THEN 1 ELSE 0 END"
        for _ in search_terms
    )
    query = f"""
        SELECT c.id, c.name, c.slug, c.node_type, c.primary_domain, c.description,
               ({score_parts}) AS match_score
        FROM kg_concepts c
        WHERE ({score_parts}) >= 2
        ORDER BY match_score DESC, LENGTH(c.name)
        LIMIT %s
    """
    # Parameters: each LIKE param appears twice (SELECT + WHERE), then LIMIT
    like_params = tuple(f"%{t}%" for t in search_terms)
    params = like_params + like_params + (limit,)

    import psycopg2
    from psycopg2.extras import RealDictCursor

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, params)
        rows = list(cur.fetchall())
        logger.debug("KG match: topic=%s terms=%s results=%d",
                     topic[:60], search_terms, len(rows))
        return rows
    except Exception as exc:
        logger.debug("KG concept matching failed: %s", exc)
        return []
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _fetch_facts_for_concept(
    concept_id: str,
    min_confidence: float = 0.85,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Fetch high-confidence facts for a KG concept."""
    conn = _get_connection()
    if conn is None:
        return []

    import psycopg2
    from psycopg2.extras import RealDictCursor

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """SELECT f.id, f.claim_text, f.confidence, f.work_id,
                      w.title AS work_title
               FROM kg_facts f
               LEFT JOIN works w ON f.work_id = w.id
               WHERE f.concept_id = %s
                 AND f.confidence >= %s
               ORDER BY f.confidence DESC
               LIMIT %s""",
            (concept_id, min_confidence, limit),
        )
        return list(cur.fetchall())
    except Exception as exc:
        logger.debug("KG fact fetch failed for %s: %s", concept_id, exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return []
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _fetch_edges_for_concept(
    concept_id: str,
    edge_types: tuple[str, ...] = (
        "INVOLVES", "COMPLICATES", "COMPLICATION_OF",
        "PROCEDURE_FOR", "TREATS", "RELATED_TO", "SUBTYPE_OF",
        "DIFFERENTIAL_FOR",
    ),
) -> list[dict[str, Any]]:
    """Fetch outgoing edges from a concept."""
    conn = _get_connection()
    if conn is None:
        return []

    import psycopg2
    from psycopg2.extras import RealDictCursor

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """SELECT e.edge_type, c2.name AS target_name, c2.slug AS target_slug,
                      c2.node_type AS target_type, c2.primary_domain
               FROM kg_edges e
               JOIN kg_concepts c2 ON e.target_concept_id = c2.id
               WHERE e.source_concept_id = %s
                 AND e.edge_type = ANY(%s)
               ORDER BY e.edge_type, c2.name""",
            (concept_id, list(edge_types)),
        )
        return list(cur.fetchall())
    except Exception as exc:
        logger.debug("KG edge fetch failed for %s: %s", concept_id, exc)
        return []
    finally:
        try:
            cur.close()
        except Exception:
            pass


# ── fact → QuestionCard conversion ───────────────────────────────────────────


def _fact_to_card(
    fact: dict[str, Any],
    *,
    edge_type: str = "",
    target_concept_name: str = "",
) -> QuestionCard:
    """Convert a KG fact into an Explorer QuestionCard."""
    claim = fact.get("claim_text", "")
    confidence = fact.get("confidence") or 0.0

    # Determine section from edge type
    section = _EDGE_TO_SECTION.get(
        edge_type,
        {
            "target_file": "04-operative-plan.md",
            "section_key": "critical_steps",
            "compiler_slot": "Critical Steps",
        },
    )

    # Build why_it_matters from concept description or edge context
    why = f"KG fact (confidence {confidence:.0%})"
    if target_concept_name:
        why = f"Related to: {target_concept_name}"

    # Answerability: high-confidence facts are "supported", lower are "needs_review"
    answerability = "needs_patient_fact"
    if confidence >= 0.92:
        answerability = "kg_supported"

    # Build evidence reference from work
    required_facts: list[str] = []
    evidence_needed = ""
    if fact.get("work_title"):
        evidence_needed = fact["work_title"][:200]
        required_facts.append(f"work:{fact.get('work_id', '')}")

    return QuestionCard(
        target_file=section["target_file"],
        section_key=section["section_key"],
        question=claim[:300],
        why_it_matters=why[:200],
        answerability=answerability,
        compiler_slot=section["compiler_slot"],
        required_facts=required_facts,
        evidence_needed=evidence_needed,
    )


def _edge_target_to_card(
    edge: dict[str, Any],
) -> QuestionCard | None:
    """Create a QuestionCard from a KG edge relationship."""
    edge_type = edge.get("edge_type", "")
    section = _EDGE_TO_SECTION.get(edge_type)
    if section is None:
        return None

    target_name = edge.get("target_name", "")

    # Generate a meaningful question from the edge
    questions: dict[str, str] = {
        "INVOLVES": f"What is the role of {target_name} in this procedure?",
        "COMPLICATES": f"Is {target_name} a likely complication?",
        "COMPLICATION_OF": f"Is {target_name} a possible catastrophic complication?",
        "PROCEDURE_FOR": f"Is {target_name} the primary target pathology?",
        "TREATS": f"How does this procedure address {target_name}?",
        "RELATED_TO": f"How does {target_name} affect surgical decision-making?",
        "SUBTYPE_OF": f"What variant of {target_name} is relevant here?",
    }
    question = questions.get(edge_type, f"Consider: {target_name}")

    return QuestionCard(
        target_file=section["target_file"],
        section_key=section["section_key"],
        question=question,
        why_it_matters=f"KG edge: {edge_type} → {target_name}",
        answerability="needs_patient_fact",
        compiler_slot=section["compiler_slot"],
    )


# ── public API ───────────────────────────────────────────────────────────────


def build_kg_manifest(
    topic: str,
    *,
    procedure_family_id: str = "",
    min_confidence: float = 0.85,
    max_facts_per_concept: int = 8,
) -> QuestionManifest | None:
    """Build a QuestionManifest from PAPERS KG facts.

    Returns ``None`` when the KG is unavailable (graceful fallback to
    hand-written or generic templates).
    """
    if not _kg_available():
        return None

    # 1. Match KG concepts to the topic
    concepts = _match_concepts(topic, limit=5)
    if not concepts:
        logger.debug("No KG concepts matched for topic: %s", topic[:80])
        return None

    family_name = procedure_family_id or "kg_auto"
    all_cards: list[QuestionCard] = []

    for concept in concepts:
        concept_id = concept["id"]

        # 2. Fetch facts for each matched concept
        facts = _fetch_facts_for_concept(
            concept_id,
            min_confidence=min_confidence,
            limit=max_facts_per_concept,
        )
        for fact in facts:
            card = _fact_to_card(fact)
            all_cards.append(card)

        # 3. Fetch edges to generate structure cards
        edges = _fetch_edges_for_concept(concept_id)
        for edge in edges:
            card = _edge_target_to_card(edge)
            if card is not None:
                all_cards.append(card)

    if not all_cards:
        return None

    return QuestionManifest(procedure_family=family_name, cards=all_cards)


# ── KG template generator: auto-generate complete procedure-family templates ─


def build_kg_template(
    topic: str,
    *,
    min_confidence: float = 0.85,
) -> dict[str, list[QuestionCard]] | None:
    """Auto-generate a complete procedure-family template from the KG.

    Walks edges from matched procedure concepts to populate anatomy,
    operative, and risk sections.  Fills coverage gaps with generic
    cards so every section key is addressed.

    Returns a dict with the same shape as ``_FAMILY_MANIFESTS`` entries:
    ``{"anatomy_at_risk": [...], "operative_plan": [...], "risk_and_rescue": [...]}``
    or ``None`` when the KG is unavailable or no concepts match.
    """
    if not _kg_available():
        return None

    concepts = _match_concepts(topic, limit=5)
    if not concepts:
        return None

    # Collect cards organised by target_file → section_key
    anatomy_cards: list[QuestionCard] = []
    operative_cards: list[QuestionCard] = []
    risk_cards: list[QuestionCard] = []

    for concept in concepts:
        concept_id = concept["id"]

        # Pull facts for this concept
        facts = _fetch_facts_for_concept(concept_id, min_confidence=min_confidence, limit=8)
        for fact in facts:
            card = _fact_to_card(fact)
            if card.target_file == "03-anatomy-at-risk.md":
                anatomy_cards.append(card)
            elif card.target_file == "04-operative-plan.md":
                operative_cards.append(card)
            elif card.target_file == "05-risk-and-rescue.md":
                risk_cards.append(card)

        # Note: edge-generated cards are excluded from the template.
        # Edge data in the KG can be semantically inconsistent
        # (e.g. COMPLICATES edges that produce nonsense cards like
        # "Is Vestibular schwannoma a likely complication?").  Facts
        # are higher quality and more directly useful.

    # Deduplicate cards by question text similarity
    def _dedupe(cards: list[QuestionCard]) -> list[QuestionCard]:
        result: list[QuestionCard] = []
        seen_words: list[set[str]] = []
        for card in cards:
            words = set(card.question.lower().split())
            is_dup = False
            for sw in seen_words:
                if not words or not sw:
                    continue
                overlap = len(words & sw) / min(len(words), len(sw))
                if overlap > 0.7:
                    is_dup = True
                    break
            if not is_dup:
                result.append(card)
                seen_words.append(words)
        return result

    anatomy_cards = _dedupe(anatomy_cards)
    operative_cards = _dedupe(operative_cards)
    risk_cards = _dedupe(risk_cards)

    if not (anatomy_cards or operative_cards or risk_cards):
        return None

    return {
        "anatomy_at_risk": anatomy_cards,
        "operative_plan": operative_cards,
        "risk_and_rescue": risk_cards,
    }
