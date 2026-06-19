"""Standardize PubMed augmentation (BACKLOG P2 #7): apply a quality floor to the relevance-ranked
literature pool and explain when coverage is thin — so weak queries are not padded with low-tier
off-topic papers. Pure: no network/LLM. ``tier_fn`` is injected (lazy default) to avoid a cycle."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Augmentation:
    records: list = field(default_factory=list)
    note: str = ""


def standardize_records(ranked: list, *, k: int, max_tier: int = 2, tier_fn=None) -> Augmentation:
    if tier_fn is None:
        from neuro_caseboard.literature.retriever import pub_tier as tier_fn
    quality = [r for r in ranked if tier_fn(getattr(r, "pub_types", [])) <= max_tier]
    kept = quality[:k]
    if kept:
        note = "" if len(kept) >= k else (
            f"Limited literature: only {len(kept)} source(s) met the evidence bar for this question.")
    elif ranked:
        kept = ranked[:1]
        note = ("No high-quality evidence (guideline, trial, review, or cohort) matched; showing the "
                "single most relevant article — interpret with caution.")
    else:
        note = "No relevant literature found for this question."
    return Augmentation(records=kept, note=note)
