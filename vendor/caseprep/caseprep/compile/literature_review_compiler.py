"""Compiler for evidence-facing CasePrep literature-review artifacts."""

from __future__ import annotations

from collections.abc import Sequence

from caseprep.core import EvidenceRecord, OutputIntentPlan
from caseprep.synthesis.section_synthesis import SectionDraft


def _snippet(text: str, *, max_chars: int = 220) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rsplit(" ", 1)[0] + "…"


def _source_line(record: EvidenceRecord) -> str:
    title = record.title.strip() or record.source
    year = str(record.metadata.get("year") or record.metadata.get("pubdate") or "").strip()
    year_text = f", {year}" if year else ""
    snippet = _snippet(record.text)
    detail = f" — {snippet}" if snippet else ""
    return f"- [{record.id}] {title}{year_text}.{detail}"


def _section_lines(sections: Sequence[SectionDraft]) -> list[str]:
    lines: list[str] = []
    for section in sections:
        if not section.body.strip():
            continue
        evidence_ids = ", ".join(f"[{evidence_id}]" for evidence_id in section.evidence_ids)
        suffix = f" Evidence: {evidence_ids}." if evidence_ids else ""
        lines.append(f"### {section.title}")
        lines.append(section.body.strip())
        if suffix:
            lines.append(suffix)
        lines.append("")
    return lines


def compile_literature_review(
    *,
    topic: str,
    intent_plan: OutputIntentPlan,
    evidence: Sequence[EvidenceRecord],
    sections: Sequence[SectionDraft],
) -> str:
    """Render a literature-review artifact from retrieved evidence only.

    This compiler intentionally does not create new clinical conclusions from
    intent-structurer output. It summarizes the retrieved evidence set and
    preserves evidence IDs for every section/body it surfaces.
    """
    evidence_list = [record for record in evidence if record.id.strip()]
    lines: list[str] = [
        f"# Literature Review — {topic}",
        "",
        "## Clinical question",
        f"- Request: {topic}",
        f"- Intent subtype: `{intent_plan.subtype}`",
        "- Framing: evidence-focused review routed by the Intent Structurer; conclusions must come from retrieved evidence below.",
        "",
        "## Why this matters",
        "- This artifact is optimized for outcomes, rates, comparative evidence, risk factors, and limitations rather than operative step-by-step preparation.",
        "",
        "## Search/retrieval strategy",
    ]

    priorities = intent_plan.retrieval_priorities or [
        "clinical_question",
        "outcomes",
        "incidence_rates",
        "risk_factors",
        "systematic_reviews_meta_analyses",
    ]
    lines.extend(f"- {priority}" for priority in priorities)
    lines.extend(["", "## Best available evidence"])

    if not evidence_list:
        lines.append("Insufficient retrieved evidence to support a literature review synthesis.")
    else:
        lines.extend(_source_line(record) for record in evidence_list[:12])

    lines.extend(["", "## Outcome/rate synthesis"])
    section_body = _section_lines(sections)
    if section_body:
        lines.extend(section_body)
    else:
        lines.append("Insufficient retrieved evidence for supported outcome/rate synthesis.")

    lines.extend([
        "",
        "## Limitations",
        "- This artifact reflects only records retrieved during this CasePrep run.",
        "- Unsupported or absent evidence is labeled as insufficient rather than inferred.",
        "",
        "## Bottom line with citations/provenance",
    ])
    if evidence_list:
        cited_ids = ", ".join(f"[{record.id}]" for record in evidence_list[:12])
        lines.append(
            f"- Retrieved evidence available for review: {cited_ids}. Interpretive conclusions require clinician review of these cited sources."
        )
    else:
        lines.append("- Insufficient retrieved evidence; no evidence-backed bottom line can be produced.")
    lines.append(
        "- No statement in this artifact is sourced from the intent-structuring LLM; intent only selected the review template and retrieval priorities."
    )
    lines.append("")
    return "\n".join(lines)
