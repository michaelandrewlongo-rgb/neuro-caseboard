"""Dictation intake — free-text clinical narrative -> structured `CaseContext`.

LLM-first, mirroring the Explorer (`explore_llm.py`): the model call is **injected**
(`complete_fn`) so the parse/validate/merge logic is unit-testable offline and deterministic,
and any failure degrades gracefully to a regex/keyword fallback. The fallback is strictly
**topic-agnostic** — it extracts only text-structure signals (age, sex, laterality, spine
level), never clinical content from a hardcoded vocabulary; the semantic fields (pathology,
procedure, goal, comorbidities) are the model's job.

This is WS-1 of the case-dossier engine: it produces the object every later stage reads from.
"""

from __future__ import annotations

import json
import os
import re

from neuro_caseboard.case_context import CaseContext
from neuro_caseboard.explore_llm import _extract_json, _default_complete, llm_available

INTAKE_SYSTEM = """You are a neurosurgical attending normalizing a colleague's free-text case \
dictation into a STRUCTURED record. Read the dictation and extract ONLY what it states; do not \
invent facts and do not ask questions.

Output ONLY JSON with these keys (omit a key or use "" / [] when the dictation does not state it):
{
  "age": <int or null>,
  "sex": "M" | "F" | "",
  "presentation": "<chief complaint + key history, in tight prose>",
  "imaging": "<relevant imaging findings>",
  "comorbidities": ["..."],
  "medications": ["..."],           // especially anticoagulants/antiplatelets
  "prior_surgery": "<prior relevant operations>",
  "functional_status": "<baseline function / performance status>",
  "laterality": "left" | "right" | "bilateral" | "midline" | "",
  "level": "<spine level token, e.g. C5-6, or \\"\\">",
  "location": "<anatomic location for cranial cases, e.g. left frontal>",
  "pathology": "<working diagnosis / lesion>",
  "procedure": "<planned operation>",
  "surgical_goal": "<the operative goal, e.g. gross total resection, decompression, clip ligation>",
  "constraints": ["<hard constraints, e.g. preserve hearing, no transfusion>"]
}

Rules: prefer the term the dictation uses. If a specific is uncertain, state it at the level you \
are sure of rather than guessing — a wrong specific is worse than a general one. JSON only."""


# --- deterministic text-structure extraction (topic-agnostic) ---------------

# Age: "62 year old", "47-year-old", "65 y/o", "54 yo", or "age: 62".
_AGE_RE = re.compile(
    r"\b(\d{1,3})\s*(?:-|\s)?\s*(?:years?[\s-]?old|y/?o|yo|yrs?)\b", re.IGNORECASE)
_AGE_LABEL_RE = re.compile(r"\bage[:\s]+(\d{1,3})\b", re.IGNORECASE)
# Sex: explicit nouns first, then pronouns as a weak fallback.
_SEX_F_RE = re.compile(r"\b(female|woman|women|lady|girl)\b", re.IGNORECASE)
_SEX_M_RE = re.compile(r"\b(male|man|men|gentleman|boy)\b", re.IGNORECASE)
_SEX_F_PRON_RE = re.compile(r"\b(she|her)\b", re.IGNORECASE)
_SEX_M_PRON_RE = re.compile(r"\b(he|him|his)\b", re.IGNORECASE)
# Laterality: first occurrence of a directional token. Handedness ("right-handed") is a fixed
# phrase about the patient, not the lesion side, so it is stripped before the search.
_LAT_RE = re.compile(r"\b(bilateral|midline|left|right)\b", re.IGNORECASE)
_HANDED_RE = re.compile(r"\b(?:left|right)[\s-]?handed\b", re.IGNORECASE)
# Spine level: C5-6, L4-5, L5-S1, C5 - 6, C5/6, or a single body like T10 / S1. The sacral letter
# S is a first-class vertebral prefix alongside C/T/L — lumbosacral inputs (L5-S1 TLIF) are common,
# and dropping the S would silently build the no-LLM dossier around the wrong level.
_LEVEL_RE = re.compile(
    r"\b([CTLS]\d{1,2}\s*[-–/]\s*[CTLS]?\d{1,2}|[CTLS]\d{1,2})\b", re.IGNORECASE)


def _extract_age(text: str):
    m = _AGE_RE.search(text) or _AGE_LABEL_RE.search(text)
    if not m:
        return None
    try:
        v = int(m.group(1))
    except (TypeError, ValueError):
        return None
    return v if 0 < v < 130 else None


def _extract_sex(text: str) -> str:
    # "woman"/"female" contain "man"/"male" but word boundaries keep them distinct; still,
    # check the female nouns first for clarity, then male nouns, then pronouns.
    if _SEX_F_RE.search(text):
        return "F"
    if _SEX_M_RE.search(text):
        return "M"
    if _SEX_F_PRON_RE.search(text):
        return "F"
    if _SEX_M_PRON_RE.search(text):
        return "M"
    return ""


def _extract_laterality(text: str) -> str:
    cleaned = _HANDED_RE.sub(" ", text or "")
    m = _LAT_RE.search(cleaned)
    return m.group(1).lower() if m else ""


def _norm_level(tok: str) -> str:
    return re.sub(r"\s+", "", tok.replace("–", "-").replace("/", "-")).upper()


def _extract_level(text: str) -> str:
    """Extract the operative spine level. When several level tokens appear (e.g. a single root
    level "C6" alongside the disc range "C5-6"), prefer a RANGE — the operative/disc level —
    over a bare single body. Pure token structure, no clinical vocabulary."""
    toks = [_norm_level(t) for t in _LEVEL_RE.findall(text or "")]
    if not toks:
        return ""
    for t in toks:
        if "-" in t:
            return t
    return toks[0]


def deterministic_parse(text: str) -> CaseContext:
    """Topic-agnostic fallback: extract only text-structure signals; keep the raw prose as the
    presentation. Semantic fields are deliberately left empty (no clinical-content lexicon)."""
    text = text or ""
    return CaseContext(
        age=_extract_age(text),
        sex=_extract_sex(text),
        laterality=_extract_laterality(text),
        level=_extract_level(text),
        presentation=text.strip(),
        raw_dictation=text,
        source="deterministic",
    )


def _merge_floor(cc: CaseContext, det: CaseContext) -> CaseContext:
    """Fill any blank text-structure field on the LLM result from the deterministic pass — the
    model may omit geometry the regexes catch reliably."""
    if cc.age is None:
        cc.age = det.age
    if not cc.sex:
        cc.sex = det.sex
    if not cc.laterality:
        cc.laterality = det.laterality
    if not cc.level:
        cc.level = det.level
    if not cc.presentation:
        cc.presentation = det.presentation
    return cc


def _provider_complete():
    """Bind to the live provider dispatch when one is configured and not disabled, else None."""
    if os.environ.get("CASEBOARD_LLM", "1") == "0":
        return None
    if not llm_available():
        return None
    return lambda system, user: _default_complete(system, user, temperature=0.1)


def parse_dictation(text: str, *, complete_fn=None) -> CaseContext:
    """Parse a free-text dictation into a `CaseContext`.

    LLM-first: with an injected ``complete_fn`` (tests) or a configured provider, the model
    structures the narrative and the deterministic text-structure pass back-fills any blank
    geometry. With no provider / no fn, or on ANY model/parse failure, falls back to the
    deterministic parser. Always records ``raw_dictation`` and ``source``.
    """
    text = text or ""
    fn = complete_fn or _provider_complete()
    if fn is None:
        return deterministic_parse(text)
    try:
        raw = json.loads(_extract_json(fn(INTAKE_SYSTEM, f"DICTATION:\n{text.strip()}")))
        cc = CaseContext.from_dict(raw)
        cc = _merge_floor(cc, deterministic_parse(text))
        cc.raw_dictation = text
        cc.source = "llm"
        return cc
    except Exception:
        return deterministic_parse(text)
