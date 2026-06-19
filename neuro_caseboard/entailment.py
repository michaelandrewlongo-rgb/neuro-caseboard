"""Claim↔citation entailment verification (inference-only).

A claim earns an inline [n] corpus citation only if its cited span ENTAILS the claim. The default
LexicalVerifier is stdlib-only and deterministic; NLIVerifier (Task 1) is an optional, lazily
imported off-the-shelf cross-encoder NLI backend for production. Conservative: when a premise span
is too thin to judge, `should_cite` abstains and KEEPS the citation; the gate may only ever REMOVE
a weak citation — never add or re-point one.
"""
from __future__ import annotations

import math
import os
import re
from typing import Protocol, runtime_checkable

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "and", "for", "with", "that", "this", "are", "must", "its", "into",
         "from", "their", "which", "may", "can", "not", "but", "all", "any", "per"}


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall((text or "").lower()) if len(t) >= 3 and t not in _STOP}


@runtime_checkable
class ClaimVerifier(Protocol):
    def entails(self, premise: str, hypothesis: str) -> bool: ...


class LexicalVerifier:
    """Deterministic token-overlap entailment proxy (no model/deps). `entails` is True when the
    hypothesis's content tokens are sufficiently recalled by the premise."""

    def __init__(self, threshold: float = 0.18, min_premise_tokens: int = 5,
                 min_precision: float = 0.2) -> None:
        self.threshold = threshold
        self.min_premise_tokens = min_premise_tokens
        self.min_precision = min_precision

    def entails(self, premise: str, hypothesis: str) -> bool:
        p = _content_tokens(premise)
        h = _content_tokens(hypothesis)
        if not h:
            return True
        shared = len(p & h)
        # (1) recall: the premise must cover enough of the hypothesis' content tokens.
        if (shared / len(h)) < self.threshold:
            return False
        # (2) precision: the shared tokens must also be a meaningful fraction of the *premise*, so
        # a long off-topic span can't clear the recall bar on a couple of incidental shared tokens.
        return bool(p) and (shared / len(p)) >= self.min_precision


def should_cite(premise: str, hypothesis: str, verifier: ClaimVerifier) -> bool:
    """Keep the citation unless the verifier positively rejects a JUDGEABLE premise. Abstain→keep
    when the premise is too thin to judge (cannot disprove)."""
    min_tok = getattr(verifier, "min_premise_tokens", 5)
    if len(_content_tokens(premise)) < min_tok:
        return True
    return bool(verifier.entails(premise, hypothesis))


# Last-resort fallback only: real MNLI checkpoints (e.g. roberta-large-mnli) order labels
# [contradiction, neutral, entailment], so the entailment index is read from the model's
# id2label at load time — this module default is used only when id2label is unavailable.
_ENTAIL_INDEX = 1


def _entail_index_from_id2label(id2label) -> int | None:
    """Index whose label name (lowercased) starts with ``entail``, or ``None`` if unusable."""
    if not isinstance(id2label, dict) or not id2label:
        return None
    for idx, label in id2label.items():
        try:
            if str(label).strip().lower().startswith("entail"):
                return int(idx)
        except (TypeError, ValueError):
            continue
    return None


def _softmax(scores) -> list[float]:
    vals = [float(s) for s in scores]
    if not vals:
        return []
    hi = max(vals)
    exps = [math.exp(v - hi) for v in vals]
    total = sum(exps)
    return [e / total for e in exps] if total else [0.0] * len(exps)


class NLIVerifier:
    """Off-the-shelf cross-encoder NLI backend (inference-only; lazily imported). Premise =
    retrieved corpus span; hypothesis = the claim. Production path only — the test suite must never
    trigger the import (inject ``model=`` to unit-test without ``sentence_transformers``)."""

    def __init__(self, model_name: str | None = None, *, model=None,
                 entail_threshold: float = 0.5) -> None:
        if model is None:
            from sentence_transformers import CrossEncoder  # lazy: heavy, optional dep
            model = CrossEncoder(model_name)
        self._model = model
        self.entail_threshold = entail_threshold

        # The entailment class index is read from the model's label map so MNLI checkpoints
        # (index 2 == ENTAILMENT) are handled correctly instead of mis-reading NEUTRAL as entailed.
        id2label = getattr(getattr(model, "config", None), "id2label", None)
        idx = _entail_index_from_id2label(id2label)
        if isinstance(id2label, dict) and id2label:
            # Validate the label space: a usable NLI head exposes >=3 classes incl. an entailment
            # label. A scalar/regression or mislabelled head raises -> get_default_verifier() falls
            # back to LexicalVerifier instead of crashing at inference time.
            if len(id2label) < 3 or idx is None:
                raise ValueError(
                    f"NLIVerifier requires a >=3-class entailment model; got id2label={id2label!r}")
            self._entail_index = idx
        else:
            self._entail_index = _ENTAIL_INDEX

    def entails(self, premise: str, hypothesis: str) -> bool:
        scores = self._model.predict([(premise, hypothesis)])[0]
        probs = _softmax(scores)
        if not probs:
            return False
        best = max(range(len(probs)), key=lambda i: probs[i])
        # Conservative: entailment must be the argmax AND clear the confidence threshold, so a
        # near-uniform split (e.g. 0.34/0.33/0.33) is not counted as entailment.
        return best == self._entail_index and probs[self._entail_index] >= self.entail_threshold


def get_default_verifier() -> ClaimVerifier:
    """NLIVerifier when CASEBOARD_NLI_MODEL is set and the backend imports; else LexicalVerifier."""
    model = os.environ.get("CASEBOARD_NLI_MODEL")
    if model:
        try:
            return NLIVerifier(model)
        except Exception:
            pass
    return LexicalVerifier()
