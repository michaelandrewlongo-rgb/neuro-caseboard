"""WS-1 intake eval — reproducible, offline.

Two graded checks per dictation in ``eval/case_dictations.json``:

1. **Deterministic extraction (real, offline):** run the regex/keyword fallback parser and score
   side (laterality) + level against ground truth. This measures what the engine captures with NO
   model — the floor.
2. **Full parse-path integration (offline, injected ground-truth):** feed the ground-truth JSON
   to ``parse_dictation`` as the (faked) model output and confirm the structured object captures
   surgical goal + comorbidities and that ``missing_critical()`` is empty for a complete record.
   This validates the parse/merge logic, NOT model quality — the live model-quality blind grade is
   deferred to a run with a configured provider (no key in CI / this environment).

Also asserts ``missing_critical()`` <= 3 on the deterministic parse for every case (the cap that
keeps intake from interrogating for everything).

Usage:  python3 eval/intake_eval.py        # prints a table, writes a dated report, exits 0/1
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
# Ensure the worktree's package source wins over any globally-installed neuro-caseboard (which
# may point at a different checkout that lacks this branch's new modules). Mirrors pyproject's
# `pythonpath=["."]` for pytest, so `python3 eval/intake_eval.py` works from the repo root.
sys.path.insert(0, str(HERE.parent))

from neuro_caseboard.intake import parse_dictation, deterministic_parse  # noqa: E402


def _fake(payload: str):
    return lambda system, user: payload


def _comorbid_match(got: list[str], want: list[str]) -> bool:
    """Every ground-truth comorbidity appears (case-insensitive substring) in the captured list."""
    got_l = " | ".join(got).lower()
    return all(w.lower() in got_l for w in want)


def main() -> int:
    cases = json.loads((HERE / "case_dictations.json").read_text())["dictations"]
    rows = []
    side_ok = level_ok = goal_ok = comorbid_ok = complete_ok = cap_ok = 0

    for c in cases:
        gt = c["ground_truth"]
        det = deterministic_parse(c["dictation"])
        full = parse_dictation(c["dictation"], complete_fn=_fake(json.dumps(gt)))

        s_ok = det.laterality == gt["laterality"]
        l_ok = det.level == gt["level"]
        g_ok = bool(full.surgical_goal) and gt["surgical_goal"].lower() in full.surgical_goal.lower()
        cm_ok = _comorbid_match(full.comorbidities, gt["comorbidities"])
        det_missing = det.missing_critical()
        comp_ok = full.missing_critical() == []
        c_ok = len(det_missing) <= 3

        side_ok += s_ok; level_ok += l_ok; goal_ok += g_ok
        comorbid_ok += cm_ok; complete_ok += comp_ok; cap_ok += c_ok
        rows.append({
            "id": c["id"], "subspecialty": c["subspecialty"],
            "side": f'{det.laterality or "-"} {"OK" if s_ok else "x("+gt["laterality"]+")"}',
            "level": f'{det.level or "-"} {"OK" if l_ok else "x("+(gt["level"] or "none")+")"}',
            "goal": "OK" if g_ok else "x", "comorbid": "OK" if cm_ok else "x",
            "det_missing": len(det_missing), "complete_missing0": "OK" if comp_ok else "x",
        })

    n = len(cases)
    print(f"{'id':42} {'side':18} {'level':14} goal comorbid det_miss")
    for r in rows:
        print(f'{r["id"]:42} {r["side"]:18} {r["level"]:14} '
              f'{r["goal"]:4} {r["comorbid"]:8} {r["det_missing"]}')
    print(f"\nDeterministic side  : {side_ok}/{n}")
    print(f"Deterministic level : {level_ok}/{n}")
    print(f"Goal captured       : {goal_ok}/{n}  (full parse path)")
    print(f"Comorbidities       : {comorbid_ok}/{n}  (full parse path)")
    print(f"missing_critical==0 : {complete_ok}/{n}  (complete record)")
    print(f"missing_critical<=3 : {cap_ok}/{n}  (deterministic parse)")

    passed = (side_ok == n and level_ok == n and goal_ok == n
              and comorbid_ok == n and complete_ok == n and cap_ok == n)

    today = dt.date.today().isoformat()
    report = HERE / f"CASE_INTAKE_REPORT_{today}.md"
    lines = [
        f"# Case Intake Eval — WS-1 ({today})", "",
        "Reproduce: `python3 eval/intake_eval.py`. Ground truth: `eval/case_dictations.json`.",
        "",
        "- **Deterministic extraction** (side/level) is real and fully offline — the no-model floor.",
        "- **Goal / comorbidities / missing_critical==0** validate the full parse/merge path fed the",
        "  ground-truth JSON (an injected fake) — they prove *capture*, not model quality.",
        "- **Live model-quality blind grade: DEFERRED** — no provider key in CI/this environment",
        "  (consistent with the skipped live-PubMed test). Re-run with `CASEBOARD_LLM_PROVIDER` set",
        "  to grade the model's own extraction.", "",
        "| case | subspecialty | side (det) | level (det) | goal | comorbid | det missing_critical | complete→0 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f'| {r["id"]} | {r["subspecialty"]} | {r["side"]} | {r["level"]} | '
                     f'{r["goal"]} | {r["comorbid"]} | {r["det_missing"]} | {r["complete_missing0"]} |')
    lines += [
        "", "## Scores",
        f"- Deterministic side: **{side_ok}/{n}**",
        f"- Deterministic level: **{level_ok}/{n}**",
        f"- Goal captured (parse path): **{goal_ok}/{n}**",
        f"- Comorbidities captured (parse path): **{comorbid_ok}/{n}**",
        f"- `missing_critical()==0` on complete record: **{complete_ok}/{n}**",
        f"- `missing_critical()<=3` on deterministic parse: **{cap_ok}/{n}**",
        "", f"**WS-1 acceptance: {'MET' if passed else 'NOT MET'}** "
        "(side/level extracted, goal+comorbidities captured, missing_critical conservative).",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {report}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
