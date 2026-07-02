#!/usr/bin/env python3
"""Paired LLM-judge for A/B answer grading (committed reproduction of the ad-hoc
grader behind eval/mmr-score-pilot/).

Reads two run.jsonl files (control + arm), pairs answers by question_id, presents
each pair BLINDED and order-randomized to an independent frontier judge on
OpenRouter (default anthropic/claude-sonnet-4.5 — distinct from the glm-5.2 answer
model), collects paired 0-100 scores, and aggregates to a verdict matching the
eval/mmr-score-pilot/mmr-score-summary.json schema.

Resumable (append-only, keyed by qid — never re-pays) and budget-gated (stops
BEFORE a call that would exceed --budget). No answers are regenerated: grading is
the only spend.

Usage:
  python evaluation/scripts/grade_pairs.py CONTROL.jsonl ARM.jsonl OUT_DIR \
      --label rerank_k-20 [--judge anthropic/claude-sonnet-4.5] [--budget 2.50]
  python evaluation/scripts/grade_pairs.py --selftest   # offline aggregation check
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from pathlib import Path

JUDGE_SYSTEM = (
    "You are an expert neurosurgery attending grading two answers to the same "
    "clinical question. Judge each answer independently on a 0-100 scale for: "
    "clinical correctness, completeness, appropriate citation of evidence, and "
    "operative usefulness. Penalize fabrication, unsafe recommendations, and "
    "vagueness. The two answers are labeled A and B in random order; do not assume "
    "either is better. Return ONLY compact JSON: "
    '{"score_a": <int 0-100>, "score_b": <int 0-100>}.'
)


def _load(path: str) -> dict:
    d = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        ans = r.get("answer") or ""
        if ans and r.get("status") in (None, "ok", "success", "completed"):
            d[r["question_id"]] = {"q": r["question"], "dom": r.get("domain"), "a": ans}
    return d


def _openrouter_client():
    from openai import OpenAI
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY not set (in .env)")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)


def _price_per_token(client, model: str) -> tuple[float, float]:
    try:
        import urllib.request
        with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=20) as r:
            models = json.load(r)["data"]
        for m in models:
            if m["id"] == model:
                p = m.get("pricing", {})
                return float(p.get("prompt", 0)), float(p.get("completion", 0))
    except Exception as exc:
        print(f"  (pricing lookup failed: {exc}; cost tracked as 0)")
    return 0.0, 0.0


def _arm_is_a(qid: str) -> bool:
    # Deterministic blind order from qid (reproducible/resumable — no RNG/wallclock).
    return sum(ord(c) for c in qid) % 2 == 0


def _parse_scores(text: str) -> tuple[float, float]:
    obj = json.loads(text[text.index("{"):text.rindex("}") + 1])
    return float(obj["score_a"]), float(obj["score_b"])


def _aggregate(grades: list[dict], judge: str, cost: float) -> dict:
    deltas = [g["score_arm"] - g["score_ctrl"] for g in grades]
    n = len(deltas)
    mean = statistics.fmean(deltas) if n else 0.0
    sd = statistics.stdev(deltas) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n else 0.0
    return {
        "n_paired": n,
        "mean_ctrl": round(statistics.fmean([g["score_ctrl"] for g in grades]), 2) if n else 0.0,
        "mean_arm": round(statistics.fmean([g["score_arm"] for g in grades]), 2) if n else 0.0,
        "mean_delta_arm_minus_ctrl": round(mean, 3),
        "sd": round(sd, 3),
        "se": round(se, 3),
        "ci95": [round(mean - 1.96 * se, 2), round(mean + 1.96 * se, 2)],
        "t": round(mean / se, 3) if se else 0.0,
        "wins": sum(1 for d in deltas if d > 0),
        "losses": sum(1 for d in deltas if d < 0),
        "ties": sum(1 for d in deltas if d == 0),
        "judge": judge,
        "total_cost": round(cost, 4),
    }


def _selftest() -> None:
    grades = [
        {"score_ctrl": 50, "score_arm": 60},   # +10 win
        {"score_ctrl": 70, "score_arm": 65},   # -5  loss
        {"score_ctrl": 80, "score_arm": 80},   # 0   tie
    ]
    s = _aggregate(grades, "test", 0.0)
    assert s["n_paired"] == 3, s
    assert s["wins"] == 1 and s["losses"] == 1 and s["ties"] == 1, s
    assert abs(s["mean_delta_arm_minus_ctrl"] - (5 / 3)) < 1e-3, s
    assert s["mean_ctrl"] == round((50 + 70 + 80) / 3, 2), s
    assert _arm_is_a("EASY-01") in (True, False)
    a, b = _parse_scores('noise {"score_a": 77, "score_b": 42} tail')
    assert (a, b) == (77.0, 42.0)
    print("selftest OK")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("control", nargs="?")
    ap.add_argument("arm", nargs="?")
    ap.add_argument("out_dir", nargs="?")
    ap.add_argument("--label", default="arm")
    ap.add_argument("--judge", default="anthropic/claude-sonnet-4.5")
    ap.add_argument("--budget", type=float, default=2.50)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return
    if not (args.control and args.arm and args.out_dir):
        ap.error("control, arm, out_dir required unless --selftest")

    ctrl, arm = _load(args.control), _load(args.arm)
    qids = [q for q in ctrl if q in arm]
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    grades_path = out / f"{args.label}-grades.jsonl"

    done = {}
    if grades_path.exists():
        for line in grades_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["qid"]] = r
    spent = sum(r.get("cost", 0.0) for r in done.values())

    client = _openrouter_client()
    p_in, p_out = _price_per_token(client, args.judge)
    print(f"[{args.label}] judge {args.judge}  ${p_in*1e6:.2f}/M in ${p_out*1e6:.2f}/M out  "
          f"budget ${args.budget:.2f}  resume {len(done)}/{len(qids)} (${spent:.4f})")

    fh = grades_path.open("a")
    for qid in qids:
        if qid in done:
            continue
        c, a = ctrl[qid], arm[qid]
        arm_is_a = _arm_is_a(qid)
        ans_a, ans_b = (a["a"], c["a"]) if arm_is_a else (c["a"], a["a"])
        user = (f"QUESTION:\n{c['q']}\n\n--- ANSWER A ---\n{ans_a}\n\n"
                f"--- ANSWER B ---\n{ans_b}")
        est = (len(user) // 4 + len(JUDGE_SYSTEM) // 4) * p_in + 400 * p_out
        if spent + est > args.budget:
            print(f"  stop at budget: ${spent:.4f} spent, next ~${est:.4f} > ${args.budget:.2f}")
            break
        resp = client.chat.completions.create(
            model=args.judge,
            messages=[{"role": "system", "content": JUDGE_SYSTEM},
                      {"role": "user", "content": user}],
            temperature=0, max_tokens=200,
        )
        u = resp.usage
        in_tok = u.prompt_tokens if u else (len(JUDGE_SYSTEM) + len(user)) // 4
        out_tok = u.completion_tokens if u else 200
        cost = in_tok * p_in + out_tok * p_out
        spent += cost
        try:
            s_a, s_b = _parse_scores(resp.choices[0].message.content)
        except Exception as exc:
            print(f"  {qid}: parse fail ({exc}); skipping")
            continue
        s_arm, s_ctrl = (s_a, s_b) if arm_is_a else (s_b, s_a)
        rec = {"qid": qid, "domain": c["dom"], "score_ctrl": s_ctrl, "score_arm": s_arm,
               "len_ctrl": len(c["a"]), "len_arm": len(a["a"]), "cost": cost}
        fh.write(json.dumps(rec) + "\n")
        fh.flush()
        done[qid] = rec
    fh.close()

    grades = list(done.values())
    summary = _aggregate(grades, args.judge, spent)
    (out / f"{args.label}-summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[{args.label}] {summary['n_paired']} paired  "
          f"Δ {summary['mean_delta_arm_minus_ctrl']:+.2f} "
          f"ci95 {summary['ci95']}  t {summary['t']}  "
          f"W/L/T {summary['wins']}/{summary['losses']}/{summary['ties']}  "
          f"${summary['total_cost']:.4f}")


if __name__ == "__main__":
    main()
