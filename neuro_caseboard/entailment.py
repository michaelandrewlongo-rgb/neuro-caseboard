"""Claim↔citation entailment verification (inference-only).

A claim earns an inline [n] corpus citation only if its cited span ENTAILS the claim. The default
LexicalVerifier is stdlib-only and deterministic; NLIVerifier (Task 1) is an optional, lazily
imported off-the-shelf cross-encoder NLI backend for production. Conservative: when a premise span
is too thin to judge, `should_cite` abstains and KEEPS the citation; the gate may only ever REMOVE
a weak citation — never add or re-point one.
"""
from __future__ import annotations

import logging
import math
import os
import re
from typing import Protocol, runtime_checkable

_TOKEN = re.compile(r"[a-z0-9]+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_STOP = {"the", "and", "for", "with", "that", "this", "are", "must", "its", "into",
         "from", "their", "which", "may", "can", "not", "but", "all", "any", "per"}

# Word endings that mark a salient clinical entity (lesion / inflammation / operation / deficit).
# Anchored at the token end; case-insensitive (tokens are lowercased before matching).
# `(?<!gn)osis` blocks diagnosis/prognosis (common clinical prose) while keeping stenosis/sclerosis/
# necrosis; `asis` catches metastasis and `desis` catches arthrodesis/spondylodesis.
_MEDICAL_SUFFIX = re.compile(
    r"(oma|omas|itis|(?<!gn)osis|ectomy|otomy|ostomy|plasty|pathy|plegia|paresis|algia|"
    r"emia|aemia|cele|rrhage|rrhagia|rrhea|rrhoea|stenosis|sclerosis|malacia|oplasty|asis|desis)$",
    re.IGNORECASE,
)

# Non-clinical words that happen to carry a medical suffix but are not clinical entities; excluded
# from medical_entities so they never trigger a bleed flag. (diagnosis/prognosis are handled by the
# `(?<!gn)osis` lookbehind above; clinical suffix words like "apathy" are deliberately NOT listed.)
_BENIGN_WORDS = frozenset({
    "academia", "bohemia", "diploma", "empathy", "sympathy",
    "telepathy", "antipathy", "nostalgia",
})


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall((text or "").lower()) if len(t) >= 3 and t not in _STOP}


def _singular(tok: str) -> str:
    """Strip a single trailing plural "s" (only for tokens long enough that "s" is a suffix, not a
    stem letter), so a plural claim entity matches its singular premise form ("gliomas"→"glioma")."""
    return tok[:-1] if tok.endswith("s") and len(tok) > 3 else tok


def medical_entities(text: str) -> set[str]:
    """Salient clinical-entity tokens in ``text``: length >= 6 (avoids short coincidences) and
    bearing a medical suffix. Generic prose words never match the suffix set, so this is a low
    false-positive proxy for "named pathology/operation/deficit" rather than ordinary vocabulary."""
    return {t for t in _TOKEN.findall((text or "").lower())
            if len(t) >= 6 and _MEDICAL_SUFFIX.search(t) and t not in _BENIGN_WORDS}


def unsupported_entities(claim: str, premise: str) -> set[str]:
    """Medical entities asserted in ``claim`` but absent from its cited ``premise`` token set —
    a cross-source content bleed (e.g. "cavernoma" appearing in a glioma answer's sentence whose
    cited span never mentions it). Uses the same tokenizer/lowercasing on both sides, comparing on
    a singular-normalized form so a pluralized claim entity ("gliomas") matches its singular premise
    token ("glioma") rather than false-flagging as a bleed."""
    premise_singulars = {_singular(t) for t in _TOKEN.findall((premise or "").lower())}
    return {e for e in medical_entities(claim) if _singular(e) not in premise_singulars}


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
        h = _content_tokens(hypothesis)
        if not h:
            return True
        p = _content_tokens(premise)
        shared = len(p & h)
        # (1) recall: the premise must cover enough of the hypothesis' content tokens. Judged over
        # the WHOLE premise, so support spread across a multi-sentence passage still counts.
        if not p or (shared / len(h)) < self.threshold:
            return False
        # (2) precision: the shared tokens must be a meaningful fraction of the best-matching premise
        # SENTENCE — not the whole premise. Retrieved corpus spans are long, multi-sentence chunks;
        # a short well-supported claim is a tiny fraction of the whole chunk (~0.05) yet a large
        # fraction of the one sentence that states it. Per-sentence precision keeps the guard against
        # long *off-topic* spans (no sentence densely matches) without rejecting long *on-topic* ones.
        # ponytail: a punctuation-free blob splits to one "sentence" == the whole premise, degrading
        # to the old whole-premise precision (conservative over-flag); upgrade path is a token window.
        best_precision = 0.0
        for sentence in _SENTENCE.split(premise):
            sp = _content_tokens(sentence)
            if len(sp) < self.min_premise_tokens:
                continue
            best_precision = max(best_precision, len(sp & h) / len(sp))
        return best_precision >= self.min_precision


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


# Markdown syntax in synthesized claims ("*   **Myelomeningocele:** ...", "### Header") reads as
# noise to an NLI cross-encoder (measured on the 40-claim gold set: uncleaned bullets pushed
# well-supported claims to "neutral"); strip it from both sides before scoring.
_MARKDOWN = re.compile(r"[*_#`]+")
_MULTI_WS = re.compile(r"\s+")


def _clean_markdown(text: str) -> str:
    return _MULTI_WS.sub(" ", _MARKDOWN.sub(" ", text or "")).strip()


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
        scores = self._model.predict([(_clean_markdown(premise), _clean_markdown(hypothesis))])[0]
        probs = _softmax(scores)
        if not probs:
            return False
        # Pure probability threshold — no argmax requirement. Summarized clinical claims often
        # score entailment below neutral yet well above chance (e.g. 0.45 entail / 0.50 neutral on
        # a judge-confirmed supported claim); requiring argmax at a low threshold re-flags them.
        # The gold-set-validated operating point is P(entail) >= threshold alone.
        return probs[self._entail_index] >= self.entail_threshold


# Default semantic gate, threshold chosen for SAFETY recall, not precision. Validated out-of-sample
# by a two-lab judge panel over the verifier's real verdicts on the full pr50 run
# (evaluation/scripts/judge_verifier.py; 500-pass recall study; see evaluation/RESULTS.md). At the
# original 0.2 the gate was quiet but low-recall (~26% overall, only 43% of hard "not-supported"
# fabrications caught). At 0.3 it catches 100% of the panel's hard fabrications and ~52% overall, at
# a modest precision cost (0.33->0.24, CIs overlap) and ~3x the flag volume (3.5%->9.6% of claims).
# Beyond 0.3 precision craters for little recall gain, so 0.3 is the knee. ~33 ms/claim GPU,
# ~1.4 s/claim + ~2 GB RSS CPU. Raise/lower with CASEBOARD_NLI_THRESHOLD.
DEFAULT_NLI_MODEL = "tasksource/deberta-base-long-nli"
DEFAULT_NLI_THRESHOLD = 0.3

# Model load is ~seconds and get_default_verifier() runs per request: cache per (model, threshold).
# A failed load is cached as None so an offline/dep-less box degrades to LexicalVerifier once,
# not with a network-timeout retry on every Ask.
_NLI_CACHE: dict = {}


def get_default_verifier() -> ClaimVerifier:
    """The production claim verifier: the default NLI cross-encoder (or ``CASEBOARD_NLI_MODEL``),
    falling back to LexicalVerifier when the model can't load or the env is ``lexical``/empty."""
    model = (os.environ.get("CASEBOARD_NLI_MODEL", DEFAULT_NLI_MODEL) or "").strip()
    if not model or model.lower() == "lexical":
        return LexicalVerifier()
    try:
        threshold = float(os.environ.get("CASEBOARD_NLI_THRESHOLD") or DEFAULT_NLI_THRESHOLD)
    except ValueError:
        threshold = DEFAULT_NLI_THRESHOLD
    key = (model, threshold)
    if key not in _NLI_CACHE:
        try:
            _NLI_CACHE[key] = NLIVerifier(model, entail_threshold=threshold)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "NLI verifier %r unavailable (%s); falling back to LexicalVerifier", model, exc)
            _NLI_CACHE[key] = None
    return _NLI_CACHE[key] or LexicalVerifier()
