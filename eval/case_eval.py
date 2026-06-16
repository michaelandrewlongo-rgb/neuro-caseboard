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


def main() -> int:
    cases = json.loads((HERE / "case_dictations.json").read_text())["dictations"]
    rows = []
    det_ok = gt_ok = 0
    for c in cases:
        det_case = parse_dictation(c["dictation"])                       # deterministic (no model)
        gt_case = CaseContext.from_dict({**c["ground_truth"], "presentation": c["dictation"]})
        d_det = build_case_dossier(det_case, enrich=False, use_llm=False)
        d_gt = build_case_dossier(gt_case, enrich=False, use_llm=False)
        det_h, gt_h = _headings(d_det), _headings(d_gt)
        det_full = all(h in det_h for h in EIGHT)
        gt_full = all(h in gt_h for h in EIGHT)
        det_ok += det_full
        gt_ok += gt_full
        claims = sum(len(s.claims) for s in d_gt.sections)
        rows.append({"id": c["id"], "sub": c["subspecialty"],
                     "det": f'{sum(h in det_h for h in EIGHT)}/8',
                     "gt": f'{sum(h in gt_h for h in EIGHT)}/8',
                     "claims": claims,
                     "missing": [h for h in EIGHT if h not in gt_h]})

    n = len(cases)
    print(f"{'id':42} {'sub':14} det  gt   claims")
    for r in rows:
        print(f'{r["id"]:42} {r["sub"]:14} {r["det"]:4} {r["gt"]:4} {r["claims"]}'
              + (f'  MISSING {r["missing"]}' if r["missing"] else ""))
    print(f"\nDeterministic-context 8/8 sections: {det_ok}/{n}")
    print(f"Full-context (ground-truth) 8/8   : {gt_ok}/{n}")
    passed = det_ok == n and gt_ok == n

    today = dt.date.today().isoformat()
    report = HERE / f"CASE_DOSSIER_REPORT_{today}.md"
    lines = [
        f"# Case Dossier Section-Coverage Eval — WS-2 ({today})", "",
        "Reproduce: `python3 eval/case_eval.py`. Ground truth: `eval/case_dictations.json`.", "",
        "Checks all eight LOOP_PROMPT §0 surfaces render, offline, across the three subspecialties.",
        "- **det** = deterministic parse (no model) → build_case_dossier (the no-model floor).",
        "- **gt** = full ground-truth context → build_case_dossier (section depth).",
        "- **Blind text-judge of section quality vs cases.json must_cover: DEFERRED** — no provider",
        "  key in CI/this environment (as in WS-1).", "",
        "| case | subspecialty | det sections | gt sections | gt claims |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f'| {r["id"]} | {r["sub"]} | {r["det"]} | {r["gt"]} | {r["claims"]} |')
    lines += [
        "", "## Scores",
        f"- Deterministic-context all-8-sections: **{det_ok}/{n}**",
        f"- Full-context all-8-sections: **{gt_ok}/{n}**",
        "", f"**WS-2 acceptance (8 sections render, single evidence axis, no regressions): "
        f"{'MET' if passed else 'NOT MET'}**.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {report}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
