#!/usr/bin/env python3
"""Phase 1-D score effect: does MMR diversity selection RAISE answer quality, or only
rebalance composition?

Phase 0A/1-D validation showed MMR (book_penalty=0.15) cuts Youmans' share of the answer
context 52%->36% and adds ~1.4 books of diversity — grader-independently. This harness asks
the orthogonal question a grader must answer: do the resulting answers score *higher*?

Design (clean paired test): build the textbook pipeline ONCE and generate each question's
answer under TWO rerankers that differ ONLY in the MMR penalty — off (0.0, = today's
top-k) and on (default 0.15). Both arms share the same embedder/index/synth client and run
the same code path, so the only difference is which passages MMR keeps. The figure/visual
lanes are disabled for both arms (identical, and figures are not graded), isolating the
textbook-passage effect. Each answer is then graded IN ISOLATION with the SAME single-answer
rubric used in Phase 0B (eval/placebo_eval.py), and we report the paired on−off delta.

Cost: ~2 synthesis calls + 2 grading calls per question (Vertex). Use --limit to pilot.

Usage:
    python3 eval/mmr_score_eval.py --limit 3            # pilot (3 Qs)
    python3 eval/mmr_score_eval.py                       # full 67 Qs
    python3 eval/mmr_score_eval.py --penalty-on 0.10     # try a different penalty
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (REPO / ".claude/worktrees/session-2026-06-20-1253/evaluation/"
                    "inputs/benchmark-manifest.jsonl")


def load_questions(manifest, limit=None):
    rows = []
    for line in Path(manifest).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("enabled", True):
                rows.append((r["id"], r.get("domain", ""), r["question"]))
    return rows[:limit] if limit else rows


def build_engines(penalty_on):
    """Two Engines sharing the heavy models; they differ ONLY in the reranker MMR penalty."""
    from neuro_core.config import load_config
    from neuro_core.embed import Embedder
    from neuro_core.index import Index
    from neuro_core.rerank import Reranker
    from neuro_core.synth_clients import make_synth_client
    from neuro_core.query import Engine

    cfg = load_config()
    embedder = Embedder(cfg.embed_model, device=cfg.embed_device)
    index = Index(cfg.index_dir)
    synth_client = make_synth_client(cfg)

    def engine(pen):
        rr = Reranker(cfg.rerank_model, device=cfg.embed_device, mmr_book_penalty=pen)
        # visual/caption lanes OFF for both arms: identical figure handling => no confound,
        # and the grader scores text. This isolates the textbook-passage effect of MMR.
        return Engine(cfg, embedder, index, rr, synth_client,
                      visual_embedder=None, visual_index=None, caption_index=None)

    return engine(0.0), engine(penalty_on)


def answer_text(engine, question):
    """Textbook answer text, or None on a clarification/refusal/error (excluded from pairs)."""
    from neuro_core.query import Clarification
    try:
        res = engine.query(question)
    except Exception as e:                    # repair-and-continue: never abort the sweep
        return None, f"gen_error: {e}"
    if isinstance(res, Clarification):
        return None, "clarification"
    return res.answer, None


def run(manifest, penalty_on, limit, out_dir):
    from eval.placebo_eval import grade_answer

    eng_off, eng_on = build_engines(penalty_on)
    questions = load_questions(manifest, limit)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    path = out_dir / "grades.jsonl"
    print(f"MMR score eval: off=0.0 vs on={penalty_on} | {len(questions)} questions")
    with path.open("w") as fh:
        for i, (qid, domain, question) in enumerate(questions, 1):
            a_off, why_off = answer_text(eng_off, question)
            a_on, why_on = answer_text(eng_on, question)
            rec = {"qid": qid, "domain": domain}
            if a_off is None or a_on is None:
                rec.update({"skipped": why_off or why_on, "score_off": None, "score_on": None})
            else:
                g_off = grade_answer(question, a_off)
                g_on = grade_answer(question, a_on)
                rec.update({
                    "score_off": g_off.get("score"), "score_on": g_on.get("score"),
                    "len_off": len(a_off), "len_on": len(a_on),
                    "err_off": g_off.get("error"), "err_on": g_on.get("error")})
            rows.append(rec)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            print(f"  [{i}/{len(questions)}] {qid}: off={rec['score_off']} on={rec['score_on']}"
                  + (f"  (skip: {rec.get('skipped')})" if rec.get("skipped") else ""), flush=True)
            time.sleep(0.2)
    summarize(rows, penalty_on, out_dir)


def summarize(rows, penalty_on, out_dir):
    pairs = [(r["score_off"], r["score_on"]) for r in rows
             if r.get("score_off") is not None and r.get("score_on") is not None]
    d = [on - off for off, on in pairs]
    n = len(d)
    summary = {"penalty_on": penalty_on, "n_paired": n,
               "n_skipped": sum(1 for r in rows if r.get("skipped"))}
    if n:
        m, sd = st.mean(d), st.pstdev(d)
        se = sd / (n ** 0.5)
        summary.update({
            "mean_off": round(st.mean([o for o, _ in pairs]), 2),
            "mean_on": round(st.mean([o for _, o in pairs]), 2),
            "mean_delta_on_minus_off": round(m, 2),
            "sd": round(sd, 2), "se": round(se, 2),
            "ci95": [round(m - 1.96 * se, 2), round(m + 1.96 * se, 2)],
            "t": round(m / se, 2) if se else None,
            "wins": sum(1 for x in d if x > 0), "losses": sum(1 for x in d if x < 0),
            "ties": sum(1 for x in d if x == 0)})
    (out_dir / "mmr-score-summary.json").write_text(json.dumps(summary, indent=2))
    print("\n=== Phase 1-D score effect (isolated grading) ===")
    for k in ("n_paired", "n_skipped", "mean_off", "mean_on",
              "mean_delta_on_minus_off", "ci95", "t", "wins", "losses", "ties"):
        if k in summary:
            print(f"  {k:26s}: {summary[k]}")
    print(f"\n  >0 and CI excluding 0 => MMR raises scores. ~0 => composition change is "
          f"score-neutral (still justified structurally by 0A).")
    print(f"  wrote {out_dir / 'mmr-score-summary.json'} and {out_dir / 'grades.jsonl'}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--penalty-on", type=float, default=0.15)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(REPO / "eval" / "mmr-score"))
    args = ap.parse_args(argv)
    if not Path(args.manifest).exists():
        sys.exit(f"manifest not found: {args.manifest}")
    run(args.manifest, args.penalty_on, args.limit, args.out)


if __name__ == "__main__":
    main()
