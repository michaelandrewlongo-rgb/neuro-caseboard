from __future__ import annotations

from dataclasses import dataclass, field

LIT_REFUSAL = "No relevant recent literature found."

LIT_SYSTEM = (
    "You are a neurosurgical evidence summarizer. Using ONLY the numbered studies "
    "provided, write a compressed but readable narrative summary of the contemporary "
    "literature relevant to the question. Rules:\n"
    "- Cite the bracketed study number for every claim, e.g. [L2]. Never invent a "
    "citation number that is not in the list.\n"
    "- Synthesize across studies into flowing prose (a short paragraph or two), not a "
    "bullet list of isolated facts; note agreement, disagreement, and recency.\n"
    "- Do not use any knowledge beyond the provided studies. Do not restate the "
    "textbook answer.\n"
    f"- If none of the studies are relevant to the question, reply exactly "
    f"\"{LIT_REFUSAL}\"\n"
    "- Be clinically precise. This is decision-support, not clinical judgment."
)


def is_lit_refusal(text: str) -> bool:
    def norm(s: str) -> str:
        return (s or "").strip().rstrip(".").strip().casefold()
    return norm(text) == norm(LIT_REFUSAL)


@dataclass
class LiteratureSynthesis:
    narrative: str
    records: list = field(default_factory=list)


def _format_studies(records) -> str:
    blocks = []
    for i, r in enumerate(records, 1):
        body = r.abstract or " ".join(f"{k}: {v}" for k, v in (r.sections or {}).items())
        head = f"[L{i}] {r.title} — {r.journal} {r.year or ''} (PMID {r.pmid})"
        blocks.append(f"{head}\n{body}")
    return "\n\n".join(blocks)


def synthesize_literature(question, records, synth_client):
    """Grounded narrative over PubMed abstracts. Returns None on empty input or refusal."""
    if not records:
        return None
    user = f"Question: {question}\n\nStudies:\n{_format_studies(records)}"
    narrative = synth_client.generate(LIT_SYSTEM, user, [])
    if not narrative or is_lit_refusal(narrative):
        return None
    return LiteratureSynthesis(narrative=narrative, records=list(records))
