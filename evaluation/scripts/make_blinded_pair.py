#!/usr/bin/env python3
"""Build a blinded A/B grading sheet + hidden key from two run.jsonl files.

Reuses the blinded-grading-2 convention: items in sorted-qid order, A/B side randomized
per item (stable seed derived from the set name), source hidden in the .md, revealed only
in <out_dir>/blinding-key.json. The grader picks A / B / tie per item without knowing which
side is control vs the arm.

Usage:
  make_blinded_pair.py CONTROL/run.jsonl ARM/run.jsonl OUT_DIR SET_NAME "arm-label" [arm_run_relpath]
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path


def load_answers(run_jsonl) -> dict:
    out = {}
    for line in Path(run_jsonl).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out[r["question_id"]] = {
            "question": r.get("question", ""),
            "answer": (r.get("answer") or "").rstrip(),
            "status": r.get("status", ""),
        }
    return out


def _seed(set_name: str) -> int:
    return int.from_bytes(hashlib.sha256(set_name.encode()).digest()[:4], "big")


def build(control: dict, arm: dict, set_name: str, arm_label: str, arm_run_rel: str):
    qids = sorted(set(control) & set(arm))
    rng = random.Random(_seed(set_name))
    items, sheet = {}, []
    sheet.append(f"# Blinded grading sheet — {set_name}\n")
    sheet.append("Two answers (**A**, **B**) to each clinical question. For each item pick the "
                 "better — **A**, **B**, or **tie** — optional 0-100 each. Source is hidden.\n")
    sheet.append(f"_{len(qids)} items._\n")
    sheet.append("---\n")
    for i, qid in enumerate(qids, 1):
        # Randomly decide whether control is A or B for this item.
        control_is_A = rng.random() < 0.5
        a_src, b_src = ("control", arm_label) if control_is_A else (arm_label, "control")
        a_txt = control[qid]["answer"] if control_is_A else arm[qid]["answer"]
        b_txt = arm[qid]["answer"] if control_is_A else control[qid]["answer"]
        items[str(i)] = {"qid": qid, "A": a_src, "B": b_src}
        sheet += [f"## Item {i}\n", f"**Question:** {control[qid]['question']}\n",
                  "### Answer A\n", a_txt or "_(empty)_", "\n",
                  "### Answer B\n", b_txt or "_(empty)_", "\n", "---\n"]
    key = {set_name: {"compares_control_vs": arm_label, "arm_run": arm_run_rel, "items": items}}
    return "\n".join(sheet), key


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) < 5:
        print(__doc__)
        return 2
    control_path, arm_path, out_dir, set_name, arm_label = a[:5]
    arm_run_rel = a[5] if len(a) > 5 else arm_path
    control, arm = load_answers(control_path), load_answers(arm_path)
    sheet, key = build(control, arm, set_name, arm_label, arm_run_rel)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{set_name}.md").write_text(sheet, encoding="utf-8")
    (out / "blinding-key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    n_tie_status = sum(1 for q in (set(control) & set(arm))
                       if control[q]["status"] != "completed" or arm[q]["status"] != "completed")
    print(f"[make_blinded_pair] wrote {out/(set_name+'.md')} + blinding-key.json "
          f"({len(set(control) & set(arm))} items; {n_tie_status} with a non-completed side)")
    return 0


def _selfcheck():
    """ponytail: one assert — randomization is balanced-ish and key matches sheet sources."""
    ctrl = {"Q1": {"question": "q1", "answer": "CTRL-1", "status": "completed"},
            "Q2": {"question": "q2", "answer": "CTRL-2", "status": "completed"}}
    arm = {"Q1": {"question": "q1", "answer": "ARM-1", "status": "completed"},
           "Q2": {"question": "q2", "answer": "ARM-2", "status": "completed"}}
    sheet, key = build(ctrl, arm, "selfcheck", "myarm", "runs/x")
    items = key["selfcheck"]["items"]
    # For each item, the A-source's text must be the one printed under "### Answer A".
    for i, qid in enumerate(sorted(set(ctrl) & set(arm)), 1):
        a_src = items[str(i)]["A"]
        a_txt = ctrl[qid]["answer"] if a_src == "control" else arm[qid]["answer"]
        assert a_txt in sheet, f"item {i}: Answer A text {a_txt!r} not found under its heading"
        assert {items[str(i)]["A"], items[str(i)]["B"]} == {"control", "myarm"}
    print("selfcheck ok")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selfcheck":
        _selfcheck()
    else:
        raise SystemExit(main())
