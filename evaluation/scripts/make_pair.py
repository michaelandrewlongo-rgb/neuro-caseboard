#!/usr/bin/env python3
"""Render a side-by-side control-vs-arm answer pair (hard questions first) for manual grading."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load_answers(run_jsonl) -> dict:
    out = {}
    for line in Path(run_jsonl).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out[r["question_id"]] = {"question": r.get("question", ""), "answer": r.get("answer") or ""}
    return out


def render_pair(control: dict, arm: dict, hard_ids: set, knob_label: str) -> str:
    qids = sorted(set(control) & set(arm), key=lambda q: (q not in hard_ids, q))
    lines = [f"# Baseline vs `{knob_label}`", ""]
    for qid in qids:
        tier = "HARD" if qid in hard_ids else "easy"
        lines += [f"## {qid} ({tier})", "", f"**Q:** {control[qid]['question']}", "",
                  "### baseline", control[qid]["answer"], "",
                  f"### {knob_label}", arm[qid]["answer"], "", "---", ""]
    return "\n".join(lines)


HARD = {"NIS-02", "OPEN-CV-04", "OPEN-CV-07", "TUMOR-01", "TUMOR-05",
        "SPINE-01", "SPINE-06", "FUNCTIONAL-02", "TRAUMA-02", "GENERAL-01", "CUSTOM-11"}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 3:
        print("usage: make_pair.py CONTROL/run.jsonl ARM/run.jsonl 'KNOB=value' [out.md]")
        return 2
    control, arm, label = load_answers(argv[0]), load_answers(argv[1]), argv[2]
    md = render_pair(control, arm, HARD, label)
    out = Path(argv[3]) if len(argv) > 3 else Path(argv[1]).parent / "baseline-vs-arm.md"
    out.write_text(md, encoding="utf-8")
    print(f"[make_pair] wrote {out} ({len(set(control) & set(arm))} questions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
