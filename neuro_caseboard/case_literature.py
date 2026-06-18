"""WS-3: attach contemporary PubMed literature to the case dossier's reasoning-bearing sections.

Reuses the existing, fully-injectable lane (`qa.build_literature_section`) — which never fabricates
(synth cites only the records it is given; citations enumerate those same records) — to give the
**Clinical Reasoning**, **Alternatives**, and **Risks** surfaces each their own synthesized
literature paragraph with `[L#]` PMID/DOI citations. This `[L#]` axis is kept strictly separate from
the corpus `[n]` evidence (which lives on the claims/appendix); the two citation spaces never merge.

Additive and failure-safe: a per-section lane failure leaves that section's `.literature` at None and
never blocks the dossier. Queries are topic-agnostic (the case's own `to_topic()` + a generic focus
token); the lane's own LLM query rewrite refines them when a provider is configured.
"""

from __future__ import annotations

from neuro_caseboard.qa import build_literature_section

# heading -> generic focus token appended to the case topic (process words, not clinical content).
LIT_SECTIONS = {
    "Clinical Reasoning": "indications outcomes",
    "Alternatives": "treatment alternatives comparison",
    "Risks": "complications",
}


def section_query(heading: str, case) -> str | None:
    """The PubMed query for a literature-bearing section, or None if the section takes no literature.

    Built from the case's **semantic** fields (pathology + procedure) + a generic per-section focus
    token — NOT the full `to_topic()`. PubMed esearch ANDs every token, so prepending case GEOMETRY
    (laterality + the level/location token) over-specifies the query and collapses recall to zero
    (observed live: "right thoracolumbar adult degenerative scoliosis coronal deformity correction
    indications outcomes" -> 0 records; dropping the geometry -> 8). Falls back to `to_topic()` only
    when both semantic fields are empty (e.g., the no-LLM deterministic floor)."""
    focus = LIT_SECTIONS.get(heading)
    if focus is None:
        return None
    semantic = " ".join(p for p in (case.pathology, case.procedure) if p).strip()
    base = semantic or case.to_topic()
    return f"{base} {focus}".strip()


def attach_case_literature(dossier, case, *, client=None, synth_client=None,
                           lit_config=None, cache=None, build_fn=None):
    """Attach a `LiteratureSection` to each of the Reasoning / Alternatives / Risks sections.

    `build_fn` defaults to `qa.build_literature_section` and is injectable for offline tests.
    Gated by the literature config (`LITERATURE_RETRIEVAL`); per-section failures are swallowed
    (additive). Returns the (mutated) dossier.
    """
    build_fn = build_fn or build_literature_section
    if lit_config is None:
        from neuro_caseboard.literature.config import load_literature_config
        lit_config = load_literature_config()
    if not lit_config.enabled:
        return dossier
    for sec in dossier.sections:
        q = section_query(sec.heading, case)
        if not q:
            continue
        try:
            lit = build_fn(q, lit_config=lit_config, client=client,
                           synth_client=synth_client, cache=cache)
        except Exception:
            lit = None
        if lit is not None:
            sec.literature = lit
    return dossier
