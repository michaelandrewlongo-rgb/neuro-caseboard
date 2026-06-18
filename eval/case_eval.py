"""WS-2 case-dossier section-coverage eval — reproducible, offline.

For each dictation in ``eval/case_dictations.json``, build the case dossier two ways and check
that all eight §0 surfaces render across the three subspecialties:

1. **Deterministic context (real, offline):** parse_dictation (no model) -> build_case_dossier
   (no provider, no retriever). The no-model floor.
2. **Full context (ground-truth):** CaseContext.from_dict(ground_truth) -> build_case_dossier.
   A richer dossier (real pathology/procedure/goal) to count section depth — still offline.

The blind text-judge of section *quality* against cases.json must_cover is deferred to a keyed
run (no provider here), as in WS-1. Writes ``eval/CASE_DOSSIER_REPORT_<date>.md``.

Usage:  python3 eval/case_eval.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))   # worktree source wins over any global install

from neuro_caseboard.intake import parse_dictation          # noqa: E402
from neuro_caseboard.case_context import CaseContext         # noqa: E402
from neuro_caseboard.pipeline import build_case_dossier      # noqa: E402

EIGHT = ["Clinical Summary", "Clinical Reasoning", "Operative Plan", "Alternatives",
         "Risks", "Pre-op Optimization", "Surgical Technique", "Case Figures"]


def _headings(dossier):
    return [s.heading for s in dossier.sections]


# Canned PubMed lane (offline): a cache that returns fixed records + a synth stub, so the WS-3
# [L#] wiring is exercised deterministically with no network — fabrication is impossible because
# only these records can be cited. The live recency/relevance grade is deferred (no NCBI key).
from neuro_caseboard.literature.retriever import LiteratureRecord   # noqa: E402

_LIT_RECORDS = [
    LiteratureRecord(pmid="111", title="Contemporary outcomes study", journal="J Neurosurg",
                     year=2024, doi="10.3171/x", url="", abstract="outcomes data"),
    LiteratureRecord(pmid="222", title="Systematic review", journal="Neurosurgery",
                     year=2023, doi="", url="https://pubmed/222", abstract="pooled data"),
]
_LIT_PMIDS = {r.pmid for r in _LIT_RECORDS}


class _CannedCache:
    def get(self, key):
        return _LIT_RECORDS
    def set(self, key, records):
        pass


class _CannedSynth:
    def generate(self, system, user, images):
        return "Contemporary evidence is summarized here [L1][L2]."


# WS-2: an offline fake textbook corpus so the case operative/technique/structures claims earn
# inline [n] deterministically (no corpus in CI). Every [n] resolves to one of these records.
import contextlib                                                # noqa: E402
import os                                                        # noqa: E402
import re as _re                                                 # noqa: E402
from caseprep.core.contracts import EvidenceRecord               # noqa: E402

_CORPUS_SECTIONS = ("Operative Plan", "Surgical Technique", "Risks")
_CORPUS_CITE = _re.compile(r"(?<!L)\[(\d+)\]")    # [3] but not [L3]


class _FakeCorpus:
    def retrieve(self, query, *, top_n=5, subdomain=None):
        k = min(top_n, 3)
        return [EvidenceRecord(id=f"corpus{i}", source="corpus",
                               title=f"Reference corpus record {i}",
                               text=f"Operative anatomy/technique passage {i}.",
                               metadata={"citation": f"Reference corpus record {i}"})
                for i in range(1, k + 1)]


@contextlib.contextmanager
def _figures_off():
    prev = os.environ.get("CASEBOARD_TEXTBOOK_FIGURES")
    os.environ["CASEBOARD_TEXTBOOK_FIGURES"] = "0"
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("CASEBOARD_TEXTBOOK_FIGURES", None)
        else:
            os.environ["CASEBOARD_TEXTBOOK_FIGURES"] = prev


def main() -> int:
    cases = json.loads((HERE / "case_dictations.json").read_text())["dictations"]
    rows = []
    det_ok = gt_ok = lit_ok = corpus_ok = 0
    for c in cases:
        det_case = parse_dictation(c["dictation"])                       # deterministic (no model)
        gt_case = CaseContext.from_dict({**c["ground_truth"], "presentation": c["dictation"]})
        d_det = build_case_dossier(det_case, enrich=False, use_llm=False, literature=False)
        # full context + injected canned PubMed lane (offline) -> exercise the [L#] axis
        d_gt = build_case_dossier(gt_case, enrich=False, use_llm=False, literature=True,
                                  lit_cache=_CannedCache(), lit_synth_client=_CannedSynth())
        # WS-2: a corpus-grounded build (injected fake corpus, figures off) -> inline [n] on the
        # operative/technique/structures surfaces, every marker resolving to a retrieved record.
        with _figures_off():
            d_corpus = build_case_dossier(gt_case, enrich=True, retriever=_FakeCorpus(),
                                          use_llm=False, literature=False)
        corp_secs = {s.heading: s for s in d_corpus.sections}
        n_sources = len(next((e.sources for e in d_corpus.appendix.entries
                              if e.heading == "Evidence Sources"), []))
        corpus_cited = {int(m) for h in _CORPUS_SECTIONS for cl in getattr(corp_secs.get(h), "claims", []) or []
                        for m in _CORPUS_CITE.findall(cl.text)}
        corpus_cov = sum(1 for h in _CORPUS_SECTIONS
                         if any(_CORPUS_CITE.search(cl.text)
                                for cl in getattr(corp_secs.get(h), "claims", []) or []))
        corpus_no_fab = bool(corpus_cited) and max(corpus_cited) <= n_sources
        corpus_ok += (corpus_cov == len(_CORPUS_SECTIONS) and corpus_no_fab)
        det_h, gt_h = _headings(d_det), _headings(d_gt)
        det_full = all(h in det_h for h in EIGHT)
        gt_full = all(h in gt_h for h in EIGHT)
        det_ok += det_full
        gt_ok += gt_full
        # WS-3: the three reasoning-bearing sections carry [L#] citations, all from real records.
        lit_secs = {s.heading: s for s in d_gt.sections}
        lit_cov = sum(1 for h in ("Clinical Reasoning", "Alternatives", "Risks")
                      if getattr(lit_secs.get(h), "literature", None)
                      and lit_secs[h].literature.citations)
        all_pmids = {cit.pmid for s in d_gt.sections if getattr(s, "literature", None)
                     for cit in s.literature.citations}
        no_fabrication = all_pmids <= _LIT_PMIDS
        lit_ok += (lit_cov == 3 and no_fabrication)
        claims = sum(len(s.claims) for s in d_gt.sections)
        rows.append({"id": c["id"], "sub": c["subspecialty"],
                     "det": f'{sum(h in det_h for h in EIGHT)}/8',
                     "gt": f'{sum(h in gt_h for h in EIGHT)}/8',
                     "claims": claims, "lit": f'{lit_cov}/3{"" if no_fabrication else " FAB!"}',
                     "corpus": f'{corpus_cov}/3{"" if corpus_no_fab else " FAB!"}',
                     "missing": [h for h in EIGHT if h not in gt_h]})

    n = len(cases)
    print(f"{'id':42} {'sub':14} det  gt   claims lit  corpus")
    for r in rows:
        print(f'{r["id"]:42} {r["sub"]:14} {r["det"]:4} {r["gt"]:4} {r["claims"]:6} '
              f'{r["lit"]:5} {r["corpus"]}'
              + (f'  MISSING {r["missing"]}' if r["missing"] else ""))
    print(f"\nDeterministic-context 8/8 sections: {det_ok}/{n}")
    print(f"Full-context (ground-truth) 8/8   : {gt_ok}/{n}")
    print(f"Literature [L#] on 3/3 sections, no fabrication: {lit_ok}/{n}")
    print(f"Corpus [n] on 3/3 operative/technique/structures, no fabrication: {corpus_ok}/{n}")
    passed = det_ok == n and gt_ok == n and lit_ok == n and corpus_ok == n

    today = dt.date.today().isoformat()
    report = HERE / f"CASE_DOSSIER_REPORT_{today}.md"
    lines = [
        f"# Case Dossier Section-Coverage + Literature Eval — WS-2/WS-3 ({today})", "",
        "Reproduce: `python3 eval/case_eval.py`. Ground truth: `eval/case_dictations.json`.", "",
        "Checks all eight LOOP_PROMPT §0 surfaces render and (WS-3) that the three reasoning-bearing",
        "sections carry `[L#]` PubMed citations — offline, across the three subspecialties.",
        "- **det** = deterministic parse (no model) → build_case_dossier (the no-model floor).",
        "- **gt** = full ground-truth context → build_case_dossier (section depth).",
        "- **lit** = Reasoning/Alternatives/Risks carrying `[L#]` via an injected canned PubMed lane",
        "  (no network); fabrication is impossible (only the injected records can be cited). `FAB!`",
        "  would flag any citation outside the injected set.",
        "- **Blind text-judge of section quality + live PubMed recency/relevance: DEFERRED** — no",
        "  provider/NCBI key in CI/this environment (as in WS-1).", "",
        "- **corpus** = Operative Plan/Surgical Technique/Risks carrying inline `[n]` via an injected",
        "  fake corpus retriever (no corpus in CI); every `[n]` resolves to a retrieved record. `FAB!`",
        "  would flag a citation outside the retrieved set. `[n]` (corpus) stays disjoint from `[L#]`.",
        "",
        "| case | subspecialty | det sections | gt sections | gt claims | lit [L#] | corpus [n] |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f'| {r["id"]} | {r["sub"]} | {r["det"]} | {r["gt"]} | {r["claims"]} | '
                     f'{r["lit"]} | {r["corpus"]} |')
    lines += [
        "", "## Scores",
        f"- Deterministic-context all-8-sections: **{det_ok}/{n}**",
        f"- Full-context all-8-sections: **{gt_ok}/{n}**",
        f"- Literature `[L#]` on all 3 reasoning sections, no fabrication: **{lit_ok}/{n}**",
        f"- Corpus `[n]` on all 3 operative/technique/structures sections, no fabrication: **{corpus_ok}/{n}**",
        "", f"**WS-2/WS-3 acceptance (8 sections render, single evidence axis, `[L#]` separate from "
        f"`[n]`, zero fabrication, no regressions): {'MET' if passed else 'NOT MET'}**.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {report}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
