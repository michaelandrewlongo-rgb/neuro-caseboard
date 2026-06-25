"""Dedicated high-yield figure selector for the briefing bundle.

Reuses the existing figure retriever (no new ranking model). Issues one intent query per axis
(pathology / anatomy / corridor / technique / device), pools candidates, drops duplicates,
unavailable, and off-target plates, then keeps the best 5–10 balancing relevance and intent
diversity. Records why each figure was selected and preserves caption + source metadata.
"""
from __future__ import annotations

from neuro_caseboard.briefing_model import BriefingFigure

FIGURE_INTENTS = ["pathology", "anatomy", "technique", "device"]
_INTENT_QUERY = {
    "pathology": "{topic} pathology imaging",
    "anatomy":   "{topic} anatomy surgical corridor",
    "technique": "{topic} operative technique steps",
    "device":    "{topic} instrumentation construct device",
}


def select_briefing_figures(case, fig_retriever, *, image_available=None,
                            min_figs=5, max_figs=10):
    """Return (figures, insufficiency_reason). reason is '' when >= min_figs were found."""
    if fig_retriever is None:
        return [], "no figure corpus available"
    topic = case.to_topic()
    # round-robin by intent so a single intent can't dominate (diversity), best score first.
    by_intent = {}
    for intent in FIGURE_INTENTS:
        q = _INTENT_QUERY[intent].format(topic=topic)
        try:
            recs = fig_retriever.retrieve(q, topic=topic, top_n=max_figs) or []
        except Exception:
            recs = []
        ranked = sorted(recs, key=lambda r: (r.metadata or {}).get("score") or 0, reverse=True)
        by_intent[intent] = ranked

    chosen, seen = [], set()
    # interleave intents: take the next-best unused plate from each intent in turn
    for rank in range(max_figs):
        for intent in FIGURE_INTENTS:
            if len(chosen) >= max_figs:
                break
            pool = by_intent.get(intent, [])
            if rank >= len(pool):
                continue
            meta = pool[rank].metadata or {}
            path = meta.get("figure_path")
            if not path or path in seen:
                continue
            if image_available is not None and not image_available(path):
                continue   # off-target / unreadable → reject before counting
            seen.add(path)
            chosen.append(BriefingFigure(
                fig_id=f"BF{len(chosen) + 1}", image_path=path,
                caption=meta.get("caption", "") or "", citation=meta.get("citation", "") or "",
                intent=intent, generated=False))
    reason = "" if len(chosen) >= min_figs else (
        f"only {len(chosen)} unique on-target figures found (min {min_figs})")
    return chosen, reason
