"""WS-1 — offline quality-regression gate (`caseboard case`).

Aggregates the offline-computable, deterministic quality signals on the **eval** split and fails
(exit 1) if any metric regresses below the committed `eval/BASELINE.json`. This is the hard CI bar
the rest of the Output-Quality loop is graded on; the LLM-graded live judges (WS-6) are separate and
never required.

Design (LOOP_PROMPT §2):
- **Reuse the production engine, not a fork.** The same functions the product calls compute every
  signal — `deterministic_parse` (the no-model intake floor), `build_case_dossier(use_llm=False,
  <canned PubMed lane>)`, the `figures_gen` author/guard/renderer, and `dedup`.
- **Forced offline / deterministic in any environment.** Even where a provider is configured, the
  gate never makes a model/network call: intake uses `deterministic_parse` and an injected fake
  `complete_fn`; dossiers are built `use_llm=False` with the canned literature lane. So the metrics
  are byte-reproducible (the `test_gate_deterministic` invariant).
- **Per-metric direction.** `min` metrics must stay >= baseline (coverages/accuracies); `max`
  metrics must stay <= baseline (near-dup rate, red-flag contamination).

Usage:
    python3 eval/quality_gate.py                 # score eval split vs eval/BASELINE.json; exit 0/1
    python3 eval/quality_gate.py --baseline P     # use an alternate baseline file
    python3 eval/quality_gate.py --emit-baseline  # print measured metrics as a BASELINE.json body
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))   # worktree source wins over any global install

from neuro_caseboard.intake import parse_dictation, deterministic_parse   # noqa: E402
from neuro_caseboard.case_context import CaseContext                      # noqa: E402
from neuro_caseboard.pipeline import build_case_dossier                   # noqa: E402
from neuro_caseboard.case_literature import attach_case_literature        # noqa: E402
from neuro_caseboard.literature.config import load_literature_config      # noqa: E402
from neuro_caseboard.dedup import _similar, DEFAULT_THRESHOLD             # noqa: E402
from neuro_caseboard.figures_gen.author import deterministic_figure_specs  # noqa: E402
from neuro_caseboard.figures_gen.guard import guard_spec, filter_specs    # noqa: E402
from neuro_caseboard.figures_gen.render import render_spec                # noqa: E402
import dataclasses                                                        # noqa: E402

# Shared canned PubMed lane (offline) — single source of truth, imported (not re-defined) so the
# gate's [L#] check is identical to eval/case_eval's. Fabrication is impossible: only these PMIDs
# can be cited.
from eval.case_eval import _CannedCache, _CannedSynth, _LIT_PMIDS        # noqa: E402

DEFAULT_BASELINE = HERE / "BASELINE.json"

# A literature config with the lane forced ON (offline; the canned cache/synth keep it off the
# network). Built from the ambient defaults so cache_dir/k/recency stay realistic, then `enabled`
# is pinned True so the gate's [L#] signal does not depend on the LITERATURE_RETRIEVAL env flag.
_ENABLED_LIT_CONFIG = dataclasses.replace(load_literature_config(), enabled=True)

EIGHT = ["Clinical Summary", "Clinical Reasoning", "Operative Plan", "Alternatives",
         "Risks", "Pre-op Optimization", "Surgical Technique", "Case Figures"]
# Sections whose claims should become corpus-grounded ([n]) once WS-2 lands.
CORPUS_ELIGIBLE = ("Operative Plan", "Surgical Technique", "Risks")
LIT_SECTIONS = ("Clinical Reasoning", "Alternatives", "Risks")

# higher-is-better (min) unless listed here as lower-is-better (max).
DIRECTIONS = {
    "section_coverage_det": "min",
    "section_coverage_gt": "min",
    "intake_side_acc": "min",
    "intake_level_acc": "min",
    "intake_goal_acc": "min",
    "lit_coverage": "min",
    "corpus_n_coverage": "min",
    "figure_archetype_acc": "min",
    "figure_side_acc": "min",
    "figure_byte_stable": "min",
    "figure_guard_reject": "min",
    "near_dup_rate": "max",
    "red_flag_contamination": "max",
}

_CORPUS_CITE = re.compile(r"\[\d+\]")        # [1], [2] — corpus axis
_LIT_CITE = re.compile(r"\[L\d+\]")          # [L1] — literature axis (excluded from corpus scan)


@dataclass
class EvalData:
    cases: list          # eval/cases.json entries (must_cover / red_flags), eval split
    dictations: list     # eval/case_dictations.json entries, eval split
    figure_cases: list   # eval/figure_spec_cases.json entries, eval split


def _read(name):
    return json.loads((HERE / name).read_text())


def load_split(split: str = "eval") -> EvalData:
    cases = [c for c in _read("cases.json")["cases"] if c.get("split") == split]
    ids = {c["id"] for c in cases}
    dictations = [d for d in _read("case_dictations.json")["dictations"]
                  if d["id"] in ids]
    figure_cases = [c for c in _read("figure_spec_cases.json")["cases"]
                    if c.get("split") == split]
    return EvalData(cases=cases, dictations=dictations, figure_cases=figure_cases)


def _fake(payload: str):
    return lambda system, user: payload


def _section_text(dossier) -> str:
    """All human-visible text of a dossier (for lexical contamination + corpus-cite scans)."""
    parts = []
    for s in dossier.sections:
        parts.append(s.heading)
        parts.append(getattr(s, "intro", "") or "")
        parts.extend(s.cross_refs)
        for c in s.claims:
            parts.append(c.text)
            parts.append(c.why or "")
            parts.extend(c.sub_items)
    return "\n".join(parts)


def _residual_near_dup_pairs(dossier) -> int:
    """Cross-section near-duplicate claim pairs remaining after the dedup pass (should be ~0)."""
    items = [(s.heading, c.dedup_text) for s in dossier.sections for c in s.claims]
    pairs = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i][0] != items[j][0] and _similar(items[i][1], items[j][1], DEFAULT_THRESHOLD):
                pairs += 1
    return pairs


def _frac(num: int, den: int) -> float:
    return round(num / den, 6) if den else 0.0


def compute_metrics(data: EvalData) -> dict:
    """Compute every offline gate metric on *data* (the eval split). Deterministic and offline."""
    cases_by_id = {c["id"]: c for c in data.cases}
    n = len(data.dictations)

    det_cov = gt_cov = side_ok = level_ok = goal_ok = 0
    lit_ok = corpus_n_ok = 0
    near_dup_total = 0
    contamination = 0

    for d in data.dictations:
        gt = d["ground_truth"]
        # --- intake (deterministic floor + injected-ground-truth full parse) ---
        det = deterministic_parse(d["dictation"])
        side_ok += (det.laterality == gt["laterality"])
        level_ok += (det.level == gt["level"])
        full = parse_dictation(d["dictation"], complete_fn=_fake(json.dumps(gt)))
        goal_ok += bool(full.surgical_goal) and gt["surgical_goal"].lower() in full.surgical_goal.lower()

        # --- dossiers (offline, no model): deterministic-context + ground-truth-context ---
        det_dossier = build_case_dossier(det, enrich=False, use_llm=False, literature=False)
        gt_case = CaseContext.from_dict({**gt, "presentation": d["dictation"]})
        gt_dossier = build_case_dossier(gt_case, enrich=False, use_llm=False, literature=False)
        # Drive the [L#] lane EXPLICITLY with a forced-enabled offline config + the canned PubMed
        # lane, so the signal is deterministic regardless of the ambient LITERATURE_RETRIEVAL flag
        # (the unit-test conftest turns it off; we never touch the network either way).
        attach_case_literature(gt_dossier, gt_case, cache=_CannedCache(),
                               synth_client=_CannedSynth(), lit_config=_ENABLED_LIT_CONFIG)

        det_h = [s.heading for s in det_dossier.sections]
        gt_h = [s.heading for s in gt_dossier.sections]
        det_cov += all(h in det_h for h in EIGHT)
        gt_cov += all(h in gt_h for h in EIGHT)

        # --- literature [L#] on the reasoning-bearing sections, no fabrication ---
        secs = {s.heading: s for s in gt_dossier.sections}
        lit_cov = sum(1 for h in LIT_SECTIONS
                      if getattr(secs.get(h), "literature", None)
                      and secs[h].literature.citations)
        all_pmids = {cit.pmid for s in gt_dossier.sections if getattr(s, "literature", None)
                     for cit in s.literature.citations}
        lit_ok += (lit_cov == len(LIT_SECTIONS) and all_pmids <= _LIT_PMIDS)

        # --- corpus [n] presence on corpus-eligible sections (0 until WS-2 wires enrichment) ---
        has_n = any(
            _CORPUS_CITE.search(_LIT_CITE.sub("", c.text + " " + (c.why or "")))
            for s in gt_dossier.sections if s.heading in CORPUS_ELIGIBLE for c in s.claims
        )
        corpus_n_ok += bool(has_n)

        # --- near-dup residual (both contexts share the same dedup pass) ---
        near_dup_total += _residual_near_dup_pairs(gt_dossier)

        # --- red-flag lexical contamination (content-accuracy, not a safety signal) ---
        case = cases_by_id.get(d["id"], {})
        blob = (_section_text(det_dossier) + "\n" + _section_text(gt_dossier)).lower()
        for phrase in case.get("red_flags", []):
            if phrase.lower() in blob:
                contamination += 1

    # --- figures (deterministic author/guard/renderer) ---
    fc = data.figure_cases
    fa = fs = fb = fg = 0
    for c in fc:
        case = CaseContext(**c["case"])
        specs = filter_specs(deterministic_figure_specs(case), case)
        primary = specs[0]
        fa += (primary.archetype == c["expect_archetype"])
        fs += (primary.side == c["expect_side"])
        fb += (render_spec(primary) == render_spec(primary))
        flipped = dataclasses.replace(primary, side=("right" if primary.side == "left" else "left"))
        fg += (guard_spec(flipped, case)[0] is False)
    nf = len(fc)

    return {
        "section_coverage_det": _frac(det_cov, n),
        "section_coverage_gt": _frac(gt_cov, n),
        "intake_side_acc": _frac(side_ok, n),
        "intake_level_acc": _frac(level_ok, n),
        "intake_goal_acc": _frac(goal_ok, n),
        "lit_coverage": _frac(lit_ok, n),
        "corpus_n_coverage": _frac(corpus_n_ok, n),
        "figure_archetype_acc": _frac(fa, nf),
        "figure_side_acc": _frac(fs, nf),
        "figure_byte_stable": _frac(fb, nf),
        "figure_guard_reject": _frac(fg, nf),
        "near_dup_rate": _frac(near_dup_total, n),
        "red_flag_contamination": float(contamination),
    }


def load_baseline(path=DEFAULT_BASELINE) -> dict:
    return json.loads(Path(path).read_text())


def compare(metrics: dict, baseline: dict, *, eps: float = 1e-9):
    """Returns (ok, rows). A `min` metric fails below baseline; a `max` metric fails above it."""
    rows = []
    ok = True
    for metric, spec in baseline.items():
        value = metrics.get(metric)
        base = spec["value"]
        direction = spec.get("direction", DIRECTIONS.get(metric, "min"))
        if value is None:
            passed = False
        elif direction == "min":
            passed = value >= base - eps
        else:  # max
            passed = value <= base + eps
        ok = ok and passed
        rows.append({"metric": metric, "value": value, "baseline": base,
                     "direction": direction, "ok": passed})
    return ok, rows


def _emit_baseline(metrics: dict) -> str:
    body = {m: {"value": v, "direction": DIRECTIONS.get(m, "min")} for m, v in metrics.items()}
    return json.dumps(body, indent=2) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Offline quality-regression gate (eval split).")
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    ap.add_argument("--split", default="eval")
    ap.add_argument("--emit-baseline", action="store_true",
                    help="print the measured metrics as a BASELINE.json body and exit 0")
    args = ap.parse_args(argv)

    data = load_split(args.split)
    metrics = compute_metrics(data)

    if args.emit_baseline:
        sys.stdout.write(_emit_baseline(metrics))
        return 0

    baseline = load_baseline(args.baseline)
    ok, rows = compare(metrics, baseline)

    print(f"Quality gate — {args.split} split: {len(data.dictations)} cases, "
          f"{len(data.figure_cases)} figure cases")
    print(f"{'metric':26} {'value':>8} {'baseline':>9} {'dir':>4}  result")
    for r in rows:
        print(f"{r['metric']:26} {r['value']:>8} {r['baseline']:>9} {r['direction']:>4}  "
              f"{'PASS' if r['ok'] else 'FAIL'}")

    today = dt.date.today().isoformat()
    report = HERE / f"QUALITY_GATE_REPORT_{today}.md"
    lines = [
        f"# Quality-Regression Gate — WS-1 ({today})", "",
        "Reproduce: `python3 eval/quality_gate.py`. Offline + deterministic (no keys/network) on the",
        f"held-out **{args.split}** split. Fails CI if any metric regresses below `eval/BASELINE.json`.",
        "", "| metric | value | baseline | dir | result |", "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['metric']} | {r['value']} | {r['baseline']} | {r['direction']} | "
                     f"{'PASS' if r['ok'] else 'FAIL'} |")
    lines += ["", f"**Gate: {'PASS' if ok else 'FAIL'}**"]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nGate: {'PASS' if ok else 'FAIL'}  (wrote {report.name})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
