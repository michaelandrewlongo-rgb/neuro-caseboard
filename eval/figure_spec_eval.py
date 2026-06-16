"""WS-4 generated-schematic eval — reproducible, offline.

For each case in ``eval/figure_spec_cases.json`` (cranial / spine / vascular):
- the deterministic author proposes specs; the guard drops any that contradict the case;
- the primary spec's archetype + side/level must match the expected (case-specificity);
- the renderer is byte-stable (same spec -> identical PNG);
- a deliberately side-flipped spec must be REJECTED by the guard;
- each surviving spec is rendered to ``eval/_fig_specs/<id>-NN.png`` for a blind image judge.

The live image-opening judge (>=8/10 conceptual correctness + case-specificity) is DEFERRED to a
keyed/visual run; this harness produces the artifacts and pins the deterministic guarantees.

Usage:  python3 eval/figure_spec_eval.py
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from neuro_caseboard.case_context import CaseContext                       # noqa: E402
from neuro_caseboard.figures_gen.author import deterministic_figure_specs  # noqa: E402
from neuro_caseboard.figures_gen.guard import guard_spec, filter_specs     # noqa: E402
from neuro_caseboard.figures_gen.render import render_spec, render_spec_to_file  # noqa: E402


def main() -> int:
    cases = json.loads((HERE / "figure_spec_cases.json").read_text())["cases"]
    out_root = HERE / "_fig_specs"
    out_root.mkdir(exist_ok=True)
    rows = []
    arch_ok = side_ok = level_ok = stable_ok = guard_ok = 0

    for c in cases:
        case = CaseContext(**c["case"])
        specs = filter_specs(deterministic_figure_specs(case), case)
        primary = specs[0]
        a_ok = primary.archetype == c["expect_archetype"]
        s_ok = primary.side == c["expect_side"]
        l_ok = (primary.level == c["expect_level"])
        # byte-stability of the primary render
        st_ok = render_spec(primary) == render_spec(primary)
        # guard must reject a side-flipped spec
        flipped = dataclasses.replace(primary, side=("right" if primary.side == "left" else "left"))
        g_ok = (guard_spec(flipped, case)[0] is False)

        arch_ok += a_ok; side_ok += s_ok; level_ok += l_ok; stable_ok += st_ok; guard_ok += g_ok
        # render artifacts for the (deferred) image judge
        for i, spec in enumerate(specs, 1):
            render_spec_to_file(spec, out_root / f'{c["id"]}-{i:02d}.png')
        rows.append({"id": c["id"], "sub": c["subspecialty"], "arch": primary.archetype,
                     "a": a_ok, "s": s_ok, "l": l_ok, "stable": st_ok, "guard": g_ok,
                     "n": len(specs)})

    n = len(cases)
    print(f"{'id':30} {'sub':12} {'archetype':14} arch side level stable guard specs")
    for r in rows:
        print(f'{r["id"]:30} {r["sub"]:12} {r["arch"]:14} '
              f'{int(r["a"])}    {int(r["s"])}    {int(r["l"])}     '
              f'{int(r["stable"])}      {int(r["guard"])}     {r["n"]}')
    print(f"\narchetype {arch_ok}/{n} · side {side_ok}/{n} · level {level_ok}/{n} · "
          f"byte-stable {stable_ok}/{n} · guard-rejects-flip {guard_ok}/{n}")
    passed = all(v == n for v in (arch_ok, side_ok, level_ok, stable_ok, guard_ok))

    today = dt.date.today().isoformat()
    report = HERE / f"FIGURE_SPEC_REPORT_{today}.md"
    lines = [
        f"# Generated-Schematic Eval — WS-4 ({today})", "",
        "Reproduce: `python3 eval/figure_spec_eval.py`. Ground truth: `eval/figure_spec_cases.json`.",
        "Rendered artifacts: `eval/_fig_specs/<id>-NN.png` (open these for the image judge).", "",
        "Offline + deterministic: the author proposes specs, the guard drops contradictions, the PIL",
        "renderer is byte-stable. **The blind image-opening judge (>=8/10 conceptual correctness +",
        "case-specificity) is DEFERRED** to a keyed/visual run — no visual judge in this environment.",
        "", "| case | subspecialty | archetype | arch✓ | side✓ | level✓ | byte-stable | guard-rejects-flip | specs |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f'| {r["id"]} | {r["sub"]} | {r["arch"]} | {int(r["a"])} | {int(r["s"])} | '
                     f'{int(r["l"])} | {int(r["stable"])} | {int(r["guard"])} | {r["n"]} |')
    lines += [
        "", "## Scores",
        f"- Archetype matches expected: **{arch_ok}/{n}**",
        f"- Side encoded correctly (case-specificity): **{side_ok}/{n}**",
        f"- Level encoded correctly: **{level_ok}/{n}**",
        f"- Render byte-stable (same spec → identical PNG): **{stable_ok}/{n}**",
        f"- Guard rejects a side-flipped spec: **{guard_ok}/{n}**",
        "", f"**WS-4 deterministic acceptance (archetype + side/level grounding, byte-stable renders, "
        f"contradiction rejected): {'MET' if passed else 'NOT MET'}**. Image-judge ≥8/10 deferred.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {report}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
