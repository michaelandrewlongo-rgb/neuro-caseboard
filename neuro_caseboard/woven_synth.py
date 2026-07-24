"""Woven synthesis: ONE answer from textbook passages ([n]) and PubMed studies ([L#]).

Retrieval stays two separate lanes (neuro_core textbook, neuro_caseboard.literature PubMed);
only synthesis merges here. The two citation namespaces are kept distinct inline. This module
lives in neuro_caseboard so neuro_core stays literature-agnostic; it reuses neuro_core's passage/
figure formatters and the literature study formatter rather than duplicating them.

Retry/empty-guard/refusal/variant-prepend are intentionally NOT here — the orchestrator
(qa._answer_question_woven) owns them, mirroring Engine._answer for the non-woven path."""
from __future__ import annotations

from dataclasses import dataclass, field

from neuro_core.synthesize import REFUSAL

WOVEN_SYSTEM = (
    "You are a neurosurgical reference assistant. Write ONE integrated answer using two "
    "evidence sources: numbered textbook passages (cited [n], e.g. [2]) and numbered "
    "contemporary studies (cited [L#], e.g. [L3]). Rules:\n"
    "- Cite the bracketed source number for every clinical claim. Keep the two citation "
    "styles DISTINCT: textbook claims use [n]; literature claims use [L#]. Never renumber "
    "or merge them.\n"
    "- Weave the literature INTO the textbook answer where it updates, extends, confirms, "
    "or contradicts the textbook — do not append it as a separate section or restate it "
    "twice.\n"
    "- Some textbook sources include an attached page image (a figure/plate). When an image "
    "is attached for a source, you may describe what the figure shows and must still cite "
    "that source number. Do not describe images that are not attached.\n"
    "- If the textbook passages do NOT cover the question but the studies do, answer from "
    "the studies ([L#]) and add one sentence: \"The textbook corpus did not cover this; "
    "this answer rests on contemporary literature.\"\n"
    f"- If NEITHER the passages nor the studies contain the answer, say \"{REFUSAL}\"\n"
    "- If sources disagree, state the disagreement explicitly and attribute each view to "
    "its source.\n"
    "- Be concise and clinically precise. This is decision-support, not a substitute for "
    "clinical judgment."
)

# Phase 4.1 (decision furniture) + 4.3 (over-absolute language). Appended when
# PROMPT_DECISION_FURNITURE is set, so the change is an A/B arm, not a silent baseline shift.
# Targets ledger clusters missing_decision_threshold (33) / missing_comparator (34) /
# missing_risk_or_tradeoff (24) / missing_patient_selection (11) / overabsolute_language (38).
WOVEN_DECISION_RULES = (
    "\n- For any management recommendation, give the decision furniture the sources support: the "
    "threshold WITH ITS UNITS, the comparator, who is excluded, and the effect size with its "
    "interval. If a source does not establish one of these, say so explicitly (\"the sources do "
    "not give a threshold\") — never silently omit it.\n"
    "- Match the evidence's certainty. Avoid absolute words (always, never, all, none, "
    "contraindicated) unless a source states them; prefer calibrated language.\n"
    "- When a claim rests on a study with a year ([L#]/[D#] carry one), name the year inline so "
    "the reader can price its currency (e.g. \"the 2023 SELECT2 trial\")."
)

WOVEN_CORPUS_RULE = (
    "\n- A THIRD evidence source is provided below: numbered journal full-text passages "
    "(cited [D#], e.g. [D2]) from a frozen contemporary neurosurgical literature corpus "
    "(through March 2026). Prefer [D#] for currency-sensitive, trial-specific, and "
    "quantitative claims. Keep ALL THREE citation styles DISTINCT — textbook [n], PubMed "
    "[L#], corpus [D#] — and never merge or renumber them."
)


@dataclass
class WovenSynthesis:
    answer: str
    citations: list = field(default_factory=list)   # neuro_core Citation, [n]
    records: list = field(default_factory=list)      # literature records used, for [L#]
    corpus_records: list = field(default_factory=list)  # corpus passages used, for [D#]


def build_woven_prompt(question, hits, figures, records, variant_directive=None,
                       *, corpus_records=None):
    """The woven user prompt: question + textbook passages + appended figures + figure note +
    contemporary studies + journal-corpus passages. Shared by synthesize_woven() and the
    streaming orchestrator (corpus_records is keyword-only so positional callers are unaffected)."""
    from neuro_core.synthesize import (
        _format_passages, _appended_figures, _format_appended, _figure_note)
    from neuro_caseboard.literature.synth import _format_studies

    appended = _appended_figures(hits, figures)
    user = f"Question: {question}\n\nTextbook passages:\n{_format_passages(hits)}"
    user += _format_appended(appended)
    user += _figure_note(figures)
    if records:
        user += f"\n\nContemporary studies:\n{_format_studies(records)}"
    if corpus_records:
        from neuro_caseboard.corpus import format_corpus_studies
        user += f"\n\nJournal literature corpus (full text):\n{format_corpus_studies(corpus_records)}"
    if variant_directive:
        user += "\n\n" + variant_directive
    return user


def synthesize_woven(question, hits, figures, images, records, synth_client,
                     *, variant_directive=None, corpus_records=None) -> WovenSynthesis:
    from neuro_core.synthesize import build_citations
    import os
    user = build_woven_prompt(question, hits, figures, records, variant_directive,
                              corpus_records=corpus_records)
    system = WOVEN_SYSTEM + (WOVEN_CORPUS_RULE if corpus_records else "")
    if os.environ.get("PROMPT_DECISION_FURNITURE", "").lower() in ("1", "true", "yes", "on"):
        system += WOVEN_DECISION_RULES
    answer = synth_client.generate(system, user, images, route="ask.synth")
    return WovenSynthesis(answer=answer, citations=build_citations(hits, figures),
                          records=list(records), corpus_records=list(corpus_records or []))
