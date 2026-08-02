#!/usr/bin/env python3
"""Unblind N-arm A/B grader output: per-arm scores, all pairwise deltas, drift.

Consumes keymap.json (from build_ab_payloads.py: {"arms":[...], "questions":{q:{
"domain","mapping":{slot:arm}}}}) and the blinded grader records, each a JSON
object with a score per slot and the winning slot:
  {"question_id","score_A","score_B"[,"score_C"...],"better":"A|B|C","margin",...}

Maps slots back to arms, computes each arm's per-question score, every pairwise
delta vs the baseline arm (arms[0]), the head-to-head tally, and — if the ORIGINAL
baseline grades are supplied — grader drift (fresh blinded baseline mean vs original
baseline mean). Small drift is what makes the cross-arm deltas credible.

Usage:
  unblind_grades.py --keymap <dir>/keymap.json --grades <blinded.jsonl> \
      [--baseline-grades <baselinerun>/post-grades.jsonl] --out-dir <dir>
Writes: <out-dir>/ab-comparison.csv and <out-dir>/<arm>-grades.jsonl per arm.
"""
import argparse, json, csv, os, sys, string

def load_jsonl_or_array(path):
    txt = open(path, encoding="utf-8", errors="replace").read().strip()
    return json.loads(txt) if txt.startswith("[") else [json.loads(l) for l in txt.splitlines() if l.strip()]

def letter(s):
    return "A" if s >= 90 else "B" if s >= 80 else "C" if s >= 65 else "D" if s >= 50 else "F"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keymap", required=True)
    ap.add_argument("--grades", required=True)
    ap.add_argument("--baseline-grades", default=None)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)

    km = json.load(open(a.keymap))
    arms = km["arms"]; questions = km["questions"]
    base_arm = arms[0]
    grades = {g["question_id"]: g for g in load_jsonl_or_array(a.grades)}
    orig = {}
    if a.baseline_grades:
        for g in load_jsonl_or_array(a.baseline_grades):
            orig[g["question_id"]] = g.get("score")

    # per question: {arm: score}, winner arm
    per_q = {}
    for q, g in grades.items():
        if q not in questions:
            sys.exit(f"ERROR: {q} graded but not in keymap")
        mapping = questions[q]["mapping"]   # slot -> arm
        scores = {}
        for slot, arm in mapping.items():
            key = f"score_{slot}"
            if key not in g:
                sys.exit(f"ERROR: {q} grader record missing {key}")
            scores[arm] = g[key]
        winner = mapping.get(g.get("better")) if g.get("better") in mapping else None
        per_q[q] = {"domain": questions[q].get("domain", ""), "scores": scores,
                    "winner": winner, "margin": g.get("margin", "")}

    ids = sorted(per_q)
    # comparison CSV
    other = [ar for ar in arms if ar != base_arm]
    cols = ["question_id", "domain"] + [f"{ar}_score" for ar in arms] \
           + [f"{ar}_minus_{base_arm}" for ar in other] + ["blinded_winner", "margin"]
    with open(os.path.join(a.out_dir, "ab-comparison.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(cols)
        for q in ids:
            s = per_q[q]["scores"]
            row = [q, per_q[q]["domain"]] + [s.get(ar, "") for ar in arms]
            row += [(s[ar] - s[base_arm]) if ar in s and base_arm in s else "" for ar in other]
            row += [per_q[q]["winner"], per_q[q]["margin"]]
            w.writerow(row)

    # per-arm grade jsonl (for export_ab)
    for ar in arms:
        with open(os.path.join(a.out_dir, f"{ar}-grades.jsonl"), "w") as fh:
            for q in ids:
                sc = per_q[q]["scores"].get(ar)
                if sc is None: continue
                fh.write(json.dumps({"question_id": q, "score": sc, "letter_grade": letter(sc),
                                     "grader_model": "claude (blinded N-arm)"}) + "\n")

    # report
    n = len(ids)
    means = {ar: sum(per_q[q]["scores"].get(ar, 0) for q in ids) / n for ar in arms}
    print(f"Arms: {arms}   (baseline = {base_arm})   n={n}")
    print(f"{'QID':16} " + " ".join(f"{ar[:9]:>9}" for ar in arms) + "   winner")
    for q in ids:
        s = per_q[q]["scores"]
        print(f"{q:16} " + " ".join(f"{s.get(ar,''):>9}" for ar in arms) + f"   {per_q[q]['winner']}")
    print("\nMEAN per arm:")
    for ar in arms:
        print(f"  {ar:18} {means[ar]:.1f}" + (f"   ({means[ar]-means[base_arm]:+.1f} vs {base_arm})" if ar != base_arm else "   (baseline)"))
    print("\nHEAD-TO-HEAD (blinded best-of):")
    for ar in arms:
        wins = sum(1 for q in ids if per_q[q]["winner"] == ar)
        print(f"  {ar:18} wins {wins}/{n}")
    print("\nPAIRWISE mean deltas:")
    for i, x in enumerate(arms):
        for y in arms[i+1:]:
            d = means[x] - means[y]
            print(f"  {x} - {y}: {d:+.1f}")
    if orig:
        mo = sum(orig[q] for q in ids if isinstance(orig.get(q), (int, float))) / n
        mb = means[base_arm]
        print(f"\nDRIFT CONTROL: original {base_arm} mean {mo:.1f} vs fresh blinded {mb:.1f} -> drift {mb-mo:+.1f}")
        if abs(mb - mo) > 5:
            print("  WARNING: drift > 5 — graders not reproducing baseline; cross-arm deltas confounded. Fix grading first.")

if __name__ == "__main__":
    main()
