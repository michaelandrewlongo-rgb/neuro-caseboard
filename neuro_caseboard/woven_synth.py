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


@dataclass
class WovenSynthesis:
    answer: str
    citations: list = field(default_factory=list)   # neuro_core Citation, [n]
    records: list = field(default_factory=list)      # literature records used, for [L#]


def build_woven_prompt(question, hits, figures, records, variant_directive=None):
    """The woven user prompt: question + textbook passages + appended figures + figure note +
    contemporary studies. Shared by synthesize_woven() and the streaming orchestrator."""
    from neuro_core.synthesize import (
        _format_passages, _appended_figures, _format_appended, _figure_note)
    from neuro_caseboard.literature.synth import _format_studies

    appended = _appended_figures(hits, figures)
    user = f"Question: {question}\n\nTextbook passages:\n{_format_passages(hits)}"
    user += _format_appended(appended)
    user += _figure_note(figures)
    if records:
        user += f"\n\nContemporary studies:\n{_format_studies(records)}"
    if variant_directive:
        user += "\n\n" + variant_directive
    return user


def synthesize_woven(question, hits, figures, images, records, synth_client,
                     *, variant_directive=None) -> WovenSynthesis:
    from neuro_core.synthesize import build_citations
    user = build_woven_prompt(question, hits, figures, records, variant_directive)
    answer = synth_client.generate(WOVEN_SYSTEM, user, images)
    return WovenSynthesis(answer=answer, citations=build_citations(hits, figures),
                          records=list(records))
