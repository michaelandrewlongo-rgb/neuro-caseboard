#!/usr/bin/env python3
"""Live progress + early-termination monitor for a neuro-caseboard N-arm A/B test.

Reads the treatment run.jsonl (answers land atomically, one per question) and, if
present, the blinded grader output + keymap, and prints: answers progress, the
attribution check, per-arm running means, and a CLARITY verdict on the PRIMARY
pair (arms[1] vs arms[0]) telling you whether the result is already decisive
enough to terminate early. Safe to call repeatedly while work is in flight.

Usage:
  ab_progress.py --treatment-run <A1 dir> --total <N> \
      [--keymap <dir>/keymap.json] [--blinded-grades <file>] [--new-source "Youmans"]
"""
import argparse, json, os, math

def load_run(run_dir):
    recs = {}
    p = os.path.join(run_dir, "run.jsonl")
    if os.path.exists(p):
        for l in open(p, encoding="utf-8", errors="replace"):
            if l.strip():
                try: r = json.loads(l); recs[r["question_id"]] = r
                except: pass
    return recs

def load_jsonl(path):
    out = {}
    if path and os.path.exists(path):
        for l in open(path, encoding="utf-8", errors="replace"):
            if l.strip():
                try: g = json.loads(l); out[g["question_id"]] = g
                except: pass
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--treatment-run", required=True)
    ap.add_argument("--total", type=int, required=True)
    ap.add_argument("--keymap", default=None)
    ap.add_argument("--blinded-grades", default=None)
    ap.add_argument("--new-source", default=None)
    a = ap.parse_args()

    treat = load_run(a.treatment_run)
    done = len(treat)
    lats = [r.get("latency_seconds") for r in treat.values() if isinstance(r.get("latency_seconds"), (int, float))]
    avg = sum(lats) / len(lats) if lats else 0
    eta = (a.total - done) * avg / 60 if avg else 0
    print(f"ANSWERS:  {done}/{a.total} answered" + (f"   (avg {avg:.0f}s/q, ~{eta:.0f} min left)" if lats and done < a.total else ""))
    if a.new_source:
        hits = sum(1 for r in treat.values() if a.new_source.lower() in json.dumps(r).lower())
        print(f"          {hits}/{done} cite '{a.new_source}'  (attribution check)")

    km = json.load(open(a.keymap)) if a.keymap and os.path.exists(a.keymap) else None
    blinded = load_jsonl(a.blinded_grades)
    if not (km and blinded):
        print("GRADING:  0 graded yet — no verdict.")
        return
    arms = km["arms"]; questions = km["questions"]
    rows = []
    for q, g in blinded.items():
        if q not in questions: continue
        mapping = questions[q]["mapping"]
        scores = {arm: g.get(f"score_{slot}") for slot, arm in mapping.items()}
        if any(v is None for v in scores.values()): continue
        rows.append(scores)
    n = len(rows)
    print(f"GRADING:  {n}/{a.total} graded")
    if not n: return
    means = {ar: sum(r[ar] for r in rows) / n for ar in arms}
    print("RUNNING means: " + "  ".join(f"{ar}={means[ar]:.1f}" for ar in arms))
    if len(arms) >= 3:
        b = arms[0]
        for ar in arms[1:]:
            print(f"   {ar}-{b} = {means[ar]-means[b]:+.1f}")

    # CLARITY on primary pair arms[1] vs arms[0]
    if len(arms) < 2: return
    t, base = arms[1], arms[0]
    deltas = [r[t] - r[base] for r in rows]
    wins = sum(1 for r in rows if r[t] > r[base]); losses = sum(1 for r in rows if r[base] > r[t])
    md = sum(deltas) / n
    print(f"PRIMARY ({t} vs {base}): {t} {wins}/{n}, {base} {losses}/{n}, mean delta {md:+.1f}")
    if n >= a.total:
        print(f"CLARITY:  COMPLETE — run unblind_grades.py / export_ab.py for the verdict.")
        return
    floor = max(3, math.ceil(0.3 * a.total))
    if n < floor:
        print(f"CLARITY:  too early — need >= {floor} graded ({n} so far). Keep going.")
    elif (wins == n or losses == n) and abs(md) >= 15:
        side = t if wins == n else base
        print(f"CLARITY:  ** CLEAR ** — {side} wins all {n}/{n}, mean {md:+.1f}. "
              f"Decisive; safe to TERMINATE early. Remaining {a.total-n} unlikely to flip it.")
    elif max(wins, losses) / n >= 0.8 and abs(md) >= 12:
        side = t if wins > losses else base
        print(f"CLARITY:  LIKELY CLEAR — {side} dominates ({max(wins,losses)}/{n}, mean {md:+.1f}). "
              f"Grade 1-2 more to confirm, then stop.")
    else:
        print(f"CLARITY:  NOT decisive — mixed/small ({wins}-{losses}, mean {md:+.1f}). Finish the set.")

if __name__ == "__main__":
    main()
