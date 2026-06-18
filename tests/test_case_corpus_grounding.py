"""WS-2 — ground the case dossier in the textbook corpus ([n]).

Offline + deterministic. An injected fake corpus retriever stands in for the textbook corpus (none
in required CI); every [n] must resolve to a record it returned (zero fabrication), and the corpus
[n] axis must never collide with the PubMed [L#] axis.
"""

from __future__ import annotations

import re

import pytest

from caseprep.core.contracts import EvidenceRecord
from neuro_caseboard.case_context import CaseContext
from neuro_caseboard.pipeline import build_case_dossier

_CORPUS = re.compile(r"(?<!L)\[(\d+)\]")   # [3] but not [L3]


class FakeCorpus:
    """Minimal SemanticRetriever: returns deterministic corpus records for any query."""

    def __init__(self, n=3):
        self.n = n

    def retrieve(self, query, *, top_n=5, subdomain=None):
        k = min(top_n, self.n)
        return [
            EvidenceRecord(id=f"rec{i}", source="corpus",
                           title=f"Greenberg Handbook of Neurosurgery, p.{100 + i}",
                           text=f"Operative anatomy and technique passage {i}.",
                           metadata={"citation": f"Greenberg Handbook of Neurosurgery, p.{100 + i}"})
            for i in range(1, k + 1)
        ]


def _case():
    return CaseContext.from_dict({
        "laterality": "right", "level": "C5-6",
        "pathology": "cervical spondylotic myelopathy", "procedure": "ACDF",
        "surgical_goal": "decompression", "presentation": "C5-6 ACDF for CSM",
    })


def _corpus_marks(section):
    out = []
    for c in section.claims:
        out += [int(m) for m in _CORPUS.findall(c.text)]
    return out


def _sources(dossier):
    for e in dossier.appendix.entries:
        if e.heading == "Evidence Sources":
            return e.sources
    return []


def test_case_claims_carry_corpus_citations():
    d = build_case_dossier(_case(), enrich=True, retriever=FakeCorpus(),
                           use_llm=False, literature=False)
    by_heading = {s.heading: s for s in d.sections}
    for heading in ("Operative Plan", "Surgical Technique", "Risks"):
        sec = by_heading.get(heading)
        assert sec is not None, f"missing section {heading}"
        marks = _corpus_marks(sec)
        assert marks, f"{heading} has no inline [n] corpus citations"


def test_corpus_citations_resolve_to_sources_no_fabrication():
    d = build_case_dossier(_case(), enrich=True, retriever=FakeCorpus(),
                           use_llm=False, literature=False)
    n_sources = len(_sources(d))
    assert n_sources > 0
    cited = set()
    for s in d.sections:
        cited |= set(_corpus_marks(s))
    assert cited, "no [n] cited anywhere"
    assert max(cited) <= n_sources, f"cited {max(cited)} > {n_sources} sources (fabrication)"
    assert min(cited) >= 1


def test_offline_case_path_has_no_corpus_citations():
    # No retriever and no enrichment -> the offline floor: builds, zero [n], no error.
    d = build_case_dossier(_case(), enrich=False, use_llm=False, literature=False)
    cited = []
    for s in d.sections:
        cited += _corpus_marks(s)
    assert cited == [], f"offline path must carry no [n]; got {cited}"
    assert len(d.sections) == 8


def test_corpus_and_literature_axes_disjoint(monkeypatch):
    # The suite's conftest turns the literature lane OFF by default; turn it back on here (the
    # canned cache/synth keep it offline) so both axes are exercised at once.
    monkeypatch.setenv("LITERATURE_RETRIEVAL", "true")
    from eval.case_eval import _CannedCache, _CannedSynth
    d = build_case_dossier(_case(), enrich=True, retriever=FakeCorpus(),
                           use_llm=False, literature=True,
                           lit_cache=_CannedCache(), lit_synth_client=_CannedSynth())
    # [L#] lives on section.literature.citations; [n] is inline in claim text. The two number
    # spaces are rendered separately and must not be conflated.
    lit_present = any(getattr(s, "literature", None) and s.literature.citations for s in d.sections)
    corpus_present = any(_corpus_marks(s) for s in d.sections)
    assert lit_present and corpus_present, "both axes should be exercised in this test"
    # corpus markers are bare ints [n]; literature markers render as [L#] — never the same token
    for s in d.sections:
        for c in s.claims:
            assert "[L" not in c.text, "literature [L#] must not appear inline in claim text"
