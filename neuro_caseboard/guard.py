"""Deterministic anti-bleed guard.

Removes cards whose anatomy is unambiguously posterior-fossa / CPA / skull-base from a
topic that is clearly *not* in that region — the cross-region bleed the eval found on a
supratentorial convexity meningioma (CPA cranial-nerve content). Conservative by design:
it only prunes when the topic carries none of the posterior/skull-base signals, and only
on terms that name posterior-specific structures (never generic ones like "brainstem
injury", which is a legitimate cranial complication).
"""

from __future__ import annotations

from caseprep.explorer.question_manifest import QuestionManifest

# Topics that legitimately involve posterior-fossa / CPA / skull-base anatomy — when any
# appears, nothing is pruned.
_POSTERIOR_TOPIC = (
    "cpa", "cerebellopontine", "retrosigmoid", "vestibular", "acoustic", "posterior fossa",
    "fourth ventricle", "suboccipital", "medulloblastoma", "petrous", "translabyrinthine",
    "foramen magnum", "far-lateral", "far lateral", "chiari", "cerebellar", "brainstem",
    "jugular", "skull base", "clivus", "petroclival", "ependymoma", "hemangioblastoma",
    "cavernous", "trigeminal", "glossopharyngeal", "tentorial",
)

# Unambiguously posterior-fossa / CPA / skull-base anatomy. On a non-posterior topic these
# are cross-region bleed. (Generic terms like "brainstem" are deliberately excluded.)
_POSTERIOR_TERMS = (
    "cerebellopontine", "aica", " pica", "pica ", "internal auditory", "labyrinth",
    "sigmoid sinus", "jugular bulb", "vestibular schwannoma", "facial colliculus",
    "fourth ventricle", "ix-xi", "ix–xi", "vii, viii", "viii, ix", "lower cranial nerve",
)


def _has_posterior_terms(text: str) -> bool:
    low = (text or "").lower()
    return any(term in low for term in _POSTERIOR_TERMS)


def prune_offtarget(manifest, topic: str):
    """Drop cross-region posterior/CPA cards when the topic is clearly not posterior."""
    t = (topic or "").lower()
    if any(sig in t for sig in _POSTERIOR_TOPIC):
        return manifest  # genuinely posterior/skull-base — keep everything
    kept = [c for c in manifest.cards
            if not _has_posterior_terms(f"{c.question} {c.why_it_matters}")]
    return QuestionManifest(
        procedure_family=getattr(manifest, "procedure_family", "generic"), cards=kept)
