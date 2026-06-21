#!/usr/bin/env python3
"""Phase 0B: de-confound the PubMed-literature gain from answer length / section-presence.

The 3-arm benchmark graded answers JOINTLY (A/B/C in one call), and the +3.9 "PubMed" gain
was a ~3.1k-char appended literature section on an otherwise byte-identical answer, with a
suspiciously uniform +3..+5 magnitude. That is consistent with the grader rewarding the
PRESENCE of a contemporary-literature section rather than its evidentiary content.

This harness isolates that. It reuses the existing youmans run answers (no regeneration) and
builds four arms per question:

  core      - the textbook answer, no appendix (the youmans arm).
  real      - core + the real PubMed appendix (the youmans_pubmed arm).
  placebo   - core + a LENGTH-MATCHED generic-boilerplate appendix (same shape, zero
              question-specific evidence): tests reward-for-presence/length.
  scramble  - core + a REAL appendix from a DIFFERENT-domain question (right format, wrong
              topic): tests reward-for-relevance vs reward-for-format.

Each arm's answer is graded IN ISOLATION (one answer, 0-100), removing the joint-contrast
confound. Discriminator: if real ~= placebo ~= scramble, the gain is format/length, not
evidence. If real > {placebo, scramble}, the literature content is genuinely earning score.

Caveat (stated, not solved): generation and grading both use vertex/gemini-2.5-pro, so
self-preference is possible; the frozen rubric grounds but does not remove it.

Usage:
    python3 eval/placebo_eval.py --dry-run                 # build arms, report lengths, NO Vertex
    python3 eval/placebo_eval.py --limit 5                 # pilot: 5 questions x 4 arms = 20 grades
    python3 eval/placebo_eval.py                           # full run (~4 x #questions Vertex calls)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUN = (REPO / ".claude/worktrees/session-2026-06-20-1253/evaluation/runs/"
               "youmans-full67-20260620-2210/run.jsonl")

# --- frozen single-answer rubric (faithful to evaluation/inputs/nsgy-grader.txt) -----------
# Deliberately NOT modified to mention length/appendices: contaminating the grader with an
# anti-length instruction would destroy the very effect this experiment measures.
GRADER_SYSTEM = (
    "Act as a practicing neurosurgeon, fellowship-trained subspecialist where relevant, and a "
    "rigorous clinical-evidence reviewer. You will receive ONE neurosurgical question and ONE "
    "generated answer. Grade the answer on its clinical correctness, currency, and completeness "
    "for that question.\n"
    "Rules: verify time-sensitive claims against current guidelines, randomized trials, and "
    "consensus statements; do not rely on old textbook statements when newer evidence exists; "
    "distinguish minor incompleteness from errors that could change treatment selection, "
    "operative approach, timing, monitoring, or physiologic targets; do NOT reward fluency, "
    "citation density, or confident wording unless the content is accurate; mark truncated or "
    "absent answers as not gradable.\n"
    "Rubric: A/90-100 current, nuanced, clinically reliable, substantially complete; "
    "B/80-89 useful and mostly correct, limited omissions; C/65-79 directionally useful but "
    "materially incomplete/outdated/overgeneralized; D/50-64 major omissions or potentially "
    "misleading; F/<50 materially wrong, unsafe, absent, or unusable.\n"
    "Reply with a SINGLE JSON object and nothing else."
)


def grader_user(question: str, answer: str) -> str:
    return (
        f"QUESTION:\n{question}\n\n"
        f"ANSWER UNDER REVIEW:\n<<<\n{answer}\n>>>\n\n"
        "Return JSON exactly in this shape:\n"
        '{"score": 0-100, "letter": "A|B|C|D|F", '
        '"clinically_usable": "usable|usable_with_correction|not_reliable|unsafe", '
        '"got_right": ["..."], "lowered_grade": ["..."]}'
    )


# --- arm construction (reuse the benchmark's appendix format) -------------------------------
def _compose_real(answer: str, lit: dict) -> str:
    narr = (lit or {}).get("narrative") or ""
    cits = (lit or {}).get("citations") or []
    if not (narr or cits):
        return answer
    block = ["\n\n--- Contemporary literature (PubMed lane) ---\n", narr]
    if cits:
        block.append("\n\nLiterature citations:")
        for c in cits:
            block.append(f"\n[L{c.get('n')}] PMID {c.get('pmid')} — {c.get('title')} "
                         f"({c.get('journal')}, {c.get('year')})")
    return answer + "".join(block)


# Generic, question-agnostic neurosurgical prose. Says nothing specific to any one question;
# its only job is to occupy the same textual real estate as a real literature section.
_BOILERPLATE_SENTENCES = [
    "Contemporary series continue to refine patient selection and to emphasize individualized "
    "risk-benefit assessment.",
    "Reported outcomes vary with case mix, institutional volume, and the completeness of "
    "follow-up across cohorts.",
    "Multidisciplinary evaluation and shared decision-making remain central to optimizing "
    "perioperative care.",
    "Several groups note that prospective, adequately powered comparisons are still needed to "
    "settle areas of ongoing debate.",
    "Advances in imaging and intraoperative adjuncts have incrementally improved the precision "
    "of contemporary practice.",
    "Heterogeneity in technique and reporting standards complicates direct comparison between "
    "published experiences.",
    "Longer-term durability and quality-of-life endpoints are increasingly emphasized alongside "
    "early technical success.",
]


def _compose_placebo(answer: str, lit: dict) -> str:
    """A length-matched, evidence-free appendix that mimics the real section's shape.
    Targets the real appendix's char count (header + same number of citation lines + a
    boilerplate narrative trimmed to fill the remaining budget)."""
    real = _compose_real(answer, lit)
    target = len(real) - len(answer)            # chars the real appendix added
    if target <= 0:
        return answer
    cits = (lit or {}).get("citations") or []
    head = "\n\n--- Contemporary literature (PubMed lane) ---\n"
    cit_block = ""
    if cits:                                     # match citation-line shape and count
        cit_block = "\n\nLiterature citations:"
        for n in range(1, len(cits) + 1):
            cit_block += ("\n[L%d] PMID 00000000 — Contemporary management considerations: a "
                          "review (Journal of Neurosurgery, 2023)" % n)
    budget = max(0, target - len(head) - len(cit_block))
    body = []
    while sum(len(s) + 1 for s in body) < budget:
        body.append(_BOILERPLATE_SENTENCES[len(body) % len(_BOILERPLATE_SENTENCES)])
    narrative = " ".join(body)
    if len(narrative) > budget:                  # trim to the real appendix's length
        narrative = narrative[:budget].rsplit(" ", 1)[0]
    return answer + head + narrative + cit_block


def build_arms(records):
    """Return {qid: {"question","domain","arms":{arm: answer_text}}} for gradable records."""
    by_id = {}
    ordered = []
    for r in records:
        lit = (r.get("raw_response") or {}).get("literature") or {}
        if not ((lit.get("narrative") or "").strip() or lit.get("citations")):
            continue                              # no appendix to test on this question
        by_id[r["question_id"]] = r
        ordered.append(r)

    # scramble partner: first later record (wrapping) from a DIFFERENT domain
    out = {}
    n = len(ordered)
    for idx, r in enumerate(ordered):
        partner = next((ordered[(idx + off) % n] for off in range(1, n)
                        if ordered[(idx + off) % n].get("domain") != r.get("domain")), r)
        ans = r.get("answer", "")
        lit = (r.get("raw_response") or {}).get("literature") or {}
        plit = (partner.get("raw_response") or {}).get("literature") or {}
        out[r["question_id"]] = {
            "question": r["question"], "domain": r.get("domain", ""),
            "scramble_from": partner["question_id"],
            "arms": {
                "core": ans,
                "real": _compose_real(ans, lit),
                "placebo": _compose_placebo(ans, lit),
                "scramble": _compose_real(ans, plit),
            },
        }
    return out


# --- isolated grading -----------------------------------------------------------------------
def grade_answer(question: str, answer: str, *, complete=None) -> dict:
    """Grade ONE answer in isolation. Returns {score, letter, ...} or {error}. Recovers from
    transient/parse failures (one retry) so a single bad call never aborts the run."""
    if complete is None:
        from neuro_caseboard.explore_llm import _default_complete, _extract_json
        complete = _default_complete
    else:
        from neuro_caseboard.explore_llm import _extract_json
    last = None
    for attempt in range(2):
        try:
            raw = complete(GRADER_SYSTEM, grader_user(question, answer), temperature=0.0)
            obj = json.loads(_extract_json(raw))
            score = float(obj.get("score"))
            if not 0 <= score <= 100:
                raise ValueError(f"score out of range: {score}")
            obj["score"] = score
            return obj
        except Exception as e:                    # noqa: BLE001 - recover and retry once
            last = str(e)
            time.sleep(1.0 * (attempt + 1))
    return {"error": last, "score": None}


def run(records, limit, out_dir, dry_run):
    arms = build_arms(records)
    qids = list(arms)[:limit] if limit else list(arms)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        print(f"{'qid':12s} {'domain':28s} " + "".join(f"{a:>9s}" for a in
              ["core", "real", "placebo", "scramble"]))
        for qid in qids:
            a = arms[qid]["arms"]
            print(f"{qid:12s} {arms[qid]['domain'][:28]:28s} " +
                  "".join(f"{len(a[k]):9d}" for k in ["core", "real", "placebo", "scramble"]))
        # length-match sanity: placebo/scramble appendix vs real appendix
        import statistics as st
        def app(qid, k):
            return len(arms[qid]["arms"][k]) - len(arms[qid]["arms"]["core"])
        for k in ["real", "placebo", "scramble"]:
            lens = [app(q, k) for q in qids]
            print(f"  {k:9s} appendix chars: mean={st.mean(lens):.0f} "
                  f"median={st.median(lens):.0f}")
        print(f"\n[dry-run] {len(qids)} questions x 4 arms = {len(qids) * 4} grades would run.")
        return

    from neuro_caseboard.explore_llm import _llm_provider
    print(f"grading provider: {_llm_provider()}  | {len(qids)} questions x 4 arms")
    rows = []
    grades_path = out_dir / "grades.jsonl"
    with grades_path.open("w") as fh:
        for i, qid in enumerate(qids, 1):
            entry = arms[qid]
            for arm, answer in entry["arms"].items():
                g = grade_answer(entry["question"], answer)
                rec = {"qid": qid, "domain": entry["domain"], "arm": arm,
                       "score": g.get("score"), "letter": g.get("letter"),
                       "error": g.get("error")}
                rows.append(rec)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
            done = sum(1 for r in rows if r["score"] is not None)
            print(f"  [{i}/{len(qids)}] {qid}: " +
                  " ".join(f"{r['arm']}={r['score']}" for r in rows[-4:]), flush=True)

    summarize(rows, out_dir)


def summarize(rows, out_dir):
    import statistics as st
    arms = ["core", "real", "placebo", "scramble"]
    by_arm = {a: [r["score"] for r in rows if r["arm"] == a and r["score"] is not None]
              for a in arms}
    means = {a: (st.mean(v) if v else None) for a, v in by_arm.items()}
    # paired deltas vs core and vs placebo, per question
    by_q = {}
    for r in rows:
        by_q.setdefault(r["qid"], {})[r["arm"]] = r["score"]
    def paired(a, b):
        d = [q[a] - q[b] for q in by_q.values()
             if q.get(a) is not None and q.get(b) is not None]
        return (st.mean(d) if d else None, len(d))
    summary = {
        "n_questions": len(by_q),
        "n_errors": sum(1 for r in rows if r["score"] is None),
        "mean_by_arm": {a: (round(m, 2) if m is not None else None) for a, m in means.items()},
        "real_minus_core": paired("real", "core"),
        "placebo_minus_core": paired("placebo", "core"),
        "scramble_minus_core": paired("scramble", "core"),
        "real_minus_placebo": paired("real", "placebo"),
        "real_minus_scramble": paired("real", "scramble"),
    }
    (out_dir / "placebo-summary.json").write_text(json.dumps(summary, indent=2))
    print("\n=== Phase 0B placebo eval (isolated grading) ===")
    for a in arms:
        print(f"  mean {a:9s}: {summary['mean_by_arm'][a]}")
    print(f"  real - core      : {summary['real_minus_core']}   (appendix vs none)")
    print(f"  placebo - core   : {summary['placebo_minus_core']}   (length/format only)")
    print(f"  scramble - core  : {summary['scramble_minus_core']}   (wrong-topic appendix)")
    print(f"  real - placebo   : {summary['real_minus_placebo']}   (>0 => content earns score)")
    print(f"  real - scramble  : {summary['real_minus_scramble']}   (>0 => relevance earns score)")
    print(f"\n  Interpretation: if real-placebo and real-scramble ~ 0, the +3.9 was format/length.")
    print(f"  wrote {out_dir / 'placebo-summary.json'} and {out_dir / 'grades.jsonl'}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default=str(DEFAULT_RUN), help="run.jsonl with answers+literature")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(REPO / "eval" / "placebo"))
    ap.add_argument("--dry-run", action="store_true", help="build arms + report lengths, no Vertex")
    args = ap.parse_args(argv)

    if not Path(args.run).exists():
        sys.exit(f"run.jsonl not found: {args.run}")
    records = [json.loads(l) for l in Path(args.run).read_text().splitlines() if l.strip()]
    run(records, args.limit, args.out, args.dry_run)


if __name__ == "__main__":
    main()
