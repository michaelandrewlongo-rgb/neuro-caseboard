#!/usr/bin/env python3
"""Build BLINDED paired-grading payloads from two run dirs (one variable between them).

For each question present (and completed) in BOTH runs, emit a self-contained markdown
payload presenting the two answers as "Answer A" / "Answer B" with the order decided
DETERMINISTICALLY per question_id (sha256 → no global seed, reproducible) so the grader
cannot infer which arm is which. A keymap records the A/B → arm mapping for unblinding.

This is the blinded equivalent of make_pair.py (which labels arms openly — fine for human
review, NOT for grading). Pairs with unblind_pairs.py.

Usage:
  build_blinded_pairs.py BASELINE/run.jsonl TREATMENT/run.jsonl --out DIR [--ids ID ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

RUBRIC = "evaluation/inputs/nsgy-grader.txt"

GRADER_INSTRUCTIONS = """\
You are a practicing fellowship-trained neurosurgeon grading two answers to the SAME
question, blind to their origin. Use the rubric at `{rubric}` (score 0-100, letter A-F,
clinical usability safe/borderline/unsafe). Judge accuracy, currency (is guidance the
current standard, e.g. AIS 2026 not 2019), completeness, safety, and over-absolute claims.

Score BOTH answers independently, then pick the better one. Reward correct, current,
well-qualified management guidance; penalize outdated/absent/unsafe content. Do NOT reward
verbosity. Return EXACTLY ONE JSON object (no prose), schema:

{{"question_id": "{qid}", "score_A": <0-100>, "letter_A": "<A-F>", "usability_A": "<safe|borderline|unsafe>",
 "score_B": <0-100>, "letter_B": "<A-F>", "usability_B": "<safe|borderline|unsafe>",
 "better": "<A|B|tie>", "margin": <0-100>,
 "winner_fixes": ["what the winner got right that the loser missed"],
 "any_new_safety_errors": "<A|B|none>", "rationale": "<2-4 sentences>"}}
"""


def load_answers(run_jsonl: Path) -> dict:
    out = {}
    for line in run_jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("status") != "completed":
            continue
        ans = r.get("answer") or (r.get("raw_response") or {}).get("answer") or ""
        out[r["question_id"]] = {"question": r.get("question", ""), "answer": ans,
                                 "domain": r.get("domain", "?")}
    return out


def order_for(qid: str) -> str:
    """Deterministic per-qid A/B order: 'BT' (A=baseline,B=treatment) or 'TB'."""
    h = hashlib.sha256(qid.encode("utf-8")).digest()[0]
    return "BT" if (h % 2 == 0) else "TB"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline_run")
    ap.add_argument("treatment_run")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", nargs="*")
    args = ap.parse_args(argv)

    base = load_answers(Path(args.baseline_run))
    treat = load_answers(Path(args.treatment_run))
    qids = sorted(set(base) & set(treat))
    if args.ids:
        qids = [q for q in qids if q in set(args.ids)]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    keymap = {}
    for qid in qids:
        o = order_for(qid)
        a_arm, b_arm = ("baseline", "treatment") if o == "BT" else ("treatment", "baseline")
        ans_a = (base if a_arm == "baseline" else treat)[qid]["answer"]
        ans_b = (base if b_arm == "baseline" else treat)[qid]["answer"]
        keymap[qid] = {"A": a_arm, "B": b_arm, "domain": base[qid]["domain"]}
        md = [GRADER_INSTRUCTIONS.format(rubric=RUBRIC, qid=qid), "",
              f"## Question ({qid}, {base[qid]['domain']})", "", base[qid]["question"], "",
              "## Answer A", "", ans_a or "(empty)", "",
              "## Answer B", "", ans_b or "(empty)", ""]
        (out / f"{qid}.md").write_text("\n".join(md), encoding="utf-8")

    keymap["arms"] = ["baseline", "treatment"]  # consumed by update_results.py --ab
    (out / "keymap.json").write_text(json.dumps(keymap, indent=2), encoding="utf-8")
    print(f"[build_blinded_pairs] wrote {len(qids)} payloads + keymap.json -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
