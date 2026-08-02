#!/usr/bin/env python3
"""Build BLINDED N-arm grading payloads for a neuro-caseboard A/B(/C...) test.

For each question id, emits a payload file containing the question and N answers
in UNLABELED slots (ANSWER A, ANSWER B, ...). The arm->slot assignment is ROTATED
per question so no arm sits in the same slot every time (origin is hidden from the
grader). keymap.json records, per question, which arm each slot holds; it is
consumed by unblind_grades.py after grading.

Why blinded + rotated: a grader that can tell which answer is "new" inflates it.

Arms (>=2). Two equivalent ways to specify:
  Sugar (2-arm):   --baseline-run DIR --treatment-run DIR
  General (N-arm): --arm LABEL:RUN_DIR[:compose]   (repeatable; FIRST arm = baseline)
                   :compose folds that run's PubMed `literature` section into the
                   graded answer text (used to build a "+PubMed" arm with no re-answer).

Usage:
  build_ab_payloads.py --out <dir> --ids Q1 Q2 ... \
      --arm recent:evaluation/runs/post-improvement-...      \
      --arm youmans:evaluation/runs/youmans-full67-...       \
      --arm youmans_pubmed:evaluation/runs/youmans-full67-...:compose
  (omit --ids to use every question present in ALL arms)
"""
import argparse, json, os, sys, string

def load_run(run_dir):
    recs = {}
    for l in open(os.path.join(run_dir, "run.jsonl"), encoding="utf-8", errors="replace"):
        if l.strip():
            r = json.loads(l); recs[r["question_id"]] = r
    return recs

def answer_text(rec, compose):
    txt = rec.get("answer", "")
    if not compose:
        return txt
    lit = (rec.get("raw_response") or {}).get("literature") or {}
    narr = lit.get("narrative") or ""
    cits = lit.get("citations") or []
    if not (narr or cits):
        return txt  # nothing to compose for this question
    block = ["\n\n--- Contemporary literature (PubMed lane) ---\n", narr]
    if cits:
        block.append("\n\nLiterature citations:")
        for c in cits:
            block.append(f"\n[L{c.get('n')}] PMID {c.get('pmid')} — {c.get('title')} "
                         f"({c.get('journal')}, {c.get('year')})")
    return txt + "".join(block)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", nargs="*", default=None)
    ap.add_argument("--arm", action="append", default=[], help="LABEL:RUN_DIR[:compose]")
    ap.add_argument("--baseline-run", default=None)
    ap.add_argument("--treatment-run", default=None)
    a = ap.parse_args()

    # assemble arms: [(label, recs, compose)]
    arms = []
    if a.baseline_run or a.treatment_run:
        if not (a.baseline_run and a.treatment_run):
            sys.exit("ERROR: --baseline-run and --treatment-run must be given together")
        arms.append(("baseline", load_run(a.baseline_run), False))
        arms.append(("treatment", load_run(a.treatment_run), False))
    for spec in a.arm:
        parts = spec.split(":")
        label, rundir = parts[0], parts[1]
        compose = len(parts) > 2 and parts[2] == "compose"
        arms.append((label, load_run(rundir), compose))
    if len(arms) < 2:
        sys.exit("ERROR: need >=2 arms (use --arm twice, or --baseline-run/--treatment-run)")
    n = len(arms)
    if n > len(string.ascii_uppercase):
        sys.exit("ERROR: too many arms")

    common = set(arms[0][1])
    for _, recs, _ in arms[1:]:
        common &= set(recs)
    ids = a.ids or sorted(common)
    missing = [q for q in ids if q not in common]
    if missing:
        sys.exit(f"ERROR: ids missing from some arm: {missing}")

    os.makedirs(a.out, exist_ok=True)
    slots = string.ascii_uppercase
    keymap = {}
    for i, q in enumerate(ids):
        rot = i % n  # rotate arm order per question to hide origin
        ordered = arms[rot:] + arms[:rot]
        domain = arms[0][1][q].get("domain", "")
        mapping = {}
        body = [f"QUESTION_ID: {q}\nDOMAIN: {domain}\n\nQUESTION:\n{arms[0][1][q]['question']}\n"]
        for s, (label, recs, compose) in enumerate(ordered):
            slot = slots[s]
            mapping[slot] = label
            body.append(f"\n===== ANSWER {slot} =====\n{answer_text(recs[q], compose)}\n")
        keymap[q] = {"domain": domain, "mapping": mapping}
        open(os.path.join(a.out, f"{q}.md"), "w").write("".join(body))
    json.dump({"arms": [lbl for lbl, _, _ in arms], "questions": keymap},
              open(os.path.join(a.out, "keymap.json"), "w"), indent=1)
    print(f"wrote {len(ids)} blinded {n}-arm payloads + keymap.json -> {a.out}")
    print(f"  arms (first=baseline for drift): {[lbl for lbl,_,_ in arms]}")
    for q in ids[:5]:
        print(f"  {q:16} {keymap[q]['mapping']}")
    if len(ids) > 5:
        print(f"  ... ({len(ids)} total)")

if __name__ == "__main__":
    main()
