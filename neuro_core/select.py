"""Diversity-aware passage selection (Phase 1-D).

Phase 0A measured that adding Youmans (≈72% of the corpus by volume) lets it take ~44%
of the top-12 answer slots by *razor-thin* cross-encoder margins (mean gap 0.040; many
ties), often via several near-duplicate chunks from the same book/page. A flat top-K can't
see this — it just takes the highest scores, so volume wins.

``mmr_select`` is a soft Maximal-Marginal-Relevance pass: greedily pick by relevance, but
discount a candidate for each already-selected passage from the SAME book (and, more
strongly, the same book+page). The penalty is applied to per-query **normalized** scores so
it is in comparable units regardless of the cross-encoder's (uncalibrated, per-query-shifting)
logit scale — this is deliberately NOT a raw score floor, which the council flagged as the
worst option. With ``book_penalty == 0`` the function is exactly ``ranked[:k]`` (no behavior
change). A *small* penalty only flips genuine near-ties toward diversity; a decisive
single-book win (normalized relevance well above the rest) still survives the discount.
"""
from __future__ import annotations


def mmr_select(scored, k, *, book_penalty=0.0, page_penalty=0.0):
    """Select up to ``k`` passages from ``scored`` (a ``[(hit, score), ...]`` list already
    sorted best-first), trading relevance against same-source redundancy.

    ``book_penalty`` / ``page_penalty``: subtracted (per already-selected same-book /
    same-(book,page) passage) from a candidate's per-query-normalized [0,1] relevance.
    Returns the chosen ``[(hit, score), ...]`` preserving each hit's raw cross-encoder score.
    """
    if not scored:
        return []
    if book_penalty <= 0 and page_penalty <= 0:
        return list(scored[:k])

    raw = [s for _h, s in scored]
    lo, hi = min(raw), max(raw)
    rng = (hi - lo) or 1.0
    # index-keyed so duplicate scores / hit objects never collide
    norm = [(s - lo) / rng for s in raw]
    remaining = set(range(len(scored)))

    selected = []
    book_counts: dict = {}
    page_counts: dict = {}
    while remaining and len(selected) < k:
        best_i, best_val = None, None
        for i in sorted(remaining):                       # stable: ties break by rank
            hit = scored[i][0]
            penalty = (book_penalty * book_counts.get(hit.book, 0)
                       + page_penalty * page_counts.get((hit.book, hit.page), 0))
            val = norm[i] - penalty
            if best_val is None or val > best_val:
                best_i, best_val = i, val
        hit = scored[best_i][0]
        selected.append(scored[best_i])
        remaining.discard(best_i)
        book_counts[hit.book] = book_counts.get(hit.book, 0) + 1
        page_counts[(hit.book, hit.page)] = page_counts.get((hit.book, hit.page), 0) + 1
    return selected
