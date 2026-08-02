#!/usr/bin/env python3
"""Export an analysis-ready package comparing neuro-caseboard benchmark runs.

Emits, across the supplied runs: a per-question comparison CSV (scores, grades,
response time, # textbooks/figures/PubMed pulled, deltas), detail tables for
textbook citations, PubMed articles, and response times, plus a readable answer
dossier per run. Does NOT write the verdict/SUMMARY — that is a judgement call
the operator makes from these files.

Each run is given as  label:run_dir[:grades_file]
The FIRST run listed is the baseline; the SECOND is the primary treatment used
for the per-question delta columns.

Usage:
  export_ab.py --out <dir> \
      baseline:evaluation/runs/baseline-...:baseline-grades.jsonl \
      treatment:evaluation/runs/<treatment>...:treatment-grades.jsonl
"""
import argparse, json, os, csv

def load_jsonl(path):
    if not path or not os.path.exists(path):
        return []
    out = []
    for l in open(path, encoding="utf-8", errors="replace"):
        if l.strip():
            try: out.append(json.loads(l))
            except: pass
    return out

def distinct_books(rec):
    books = set()
    for c in (rec.get("citations") or []):
        if c.get("book"): books.add(c["book"])
    for f in (rec.get("figures") or []):
        if f.get("book"): books.add(f["book"])
    return sorted(books)

def lit_cits(rec):
    return ((rec.get("raw_response") or {}).get("literature") or {}).get("citations") or []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("runs", nargs="+", help="label:run_dir[:grades_file]")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    runs = {}
    order = []
    for spec in a.runs:
        parts = spec.split(":")
        label, rundir = parts[0], parts[1]
        gfile = parts[2] if len(parts) > 2 else None
        recs = {r["question_id"]: r for r in load_jsonl(os.path.join(rundir, "run.jsonl"))}
        grades = {g["question_id"]: g for g in load_jsonl(os.path.join(rundir, gfile))} if gfile else {}
        runs[label] = {"dir": rundir, "recs": recs, "grades": grades}
        order.append(label)
    base_l, treat_l = order[0], order[1]

    qids = []
    for label in (base_l, treat_l):
        for q in runs[label]["recs"]:
            if q not in qids: qids.append(q)
    qids.sort()

    # 1. per-question comparison
    with open(f"{a.out}/per_question_comparison.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["question_id", "domain", "question",
            f"{base_l}_score", f"{treat_l}_score", "score_delta",
            f"{base_l}_letter", f"{treat_l}_letter",
            f"{base_l}_latency_s", f"{treat_l}_latency_s", "latency_delta_s",
            f"{base_l}_n_textbook_cites", f"{treat_l}_n_textbook_cites",
            f"{base_l}_n_books", f"{treat_l}_n_books",
            f"{base_l}_n_figures", f"{treat_l}_n_figures",
            f"{base_l}_n_pubmed", f"{treat_l}_n_pubmed",
            f"{base_l}_status", f"{treat_l}_status",
            f"{base_l}_books", f"{treat_l}_books"])
        for q in qids:
            b = runs[base_l]["recs"].get(q, {}); p = runs[treat_l]["recs"].get(q, {})
            bg = runs[base_l]["grades"].get(q, {}); pg = runs[treat_l]["grades"].get(q, {})
            bs, ps = bg.get("score"), pg.get("score")
            d = (ps - bs) if isinstance(bs, (int, float)) and isinstance(ps, (int, float)) else ""
            bl, pl = b.get("latency_seconds"), p.get("latency_seconds")
            ld = round(pl - bl, 1) if isinstance(bl, (int, float)) and isinstance(pl, (int, float)) else ""
            w.writerow([q, b.get("domain") or p.get("domain"), b.get("question") or p.get("question") or "",
                bs, ps, d, bg.get("letter_grade"), pg.get("letter_grade"),
                round(bl, 1) if isinstance(bl, (int, float)) else "",
                round(pl, 1) if isinstance(pl, (int, float)) else "", ld,
                len(b.get("citations") or []), len(p.get("citations") or []),
                len(distinct_books(b)), len(distinct_books(p)),
                len(b.get("figures") or []), len(p.get("figures") or []),
                len(lit_cits(b)), len(lit_cits(p)),
                b.get("status"), p.get("status"),
                "; ".join(distinct_books(b)), "; ".join(distinct_books(p))])

    # 2. textbook citations / 3. pubmed / 4. timing
    with open(f"{a.out}/textbook_citations.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["run", "question_id", "kind", "n", "book", "chapter", "page"])
        for label in runs:
            for q, rec in runs[label]["recs"].items():
                for c in (rec.get("citations") or []):
                    w.writerow([label, q, "text", c.get("n"), c.get("book"), c.get("chapter"), c.get("page")])
                for f in (rec.get("figures") or []):
                    w.writerow([label, q, "figure", f.get("source_n"), f.get("book"), f.get("chapter"), f.get("page")])
    with open(f"{a.out}/pubmed_articles.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["run", "question_id", "n", "pmid", "title", "journal", "year", "doi", "url"])
        for label in runs:
            for q, rec in runs[label]["recs"].items():
                for c in lit_cits(rec):
                    w.writerow([label, q, c.get("n"), c.get("pmid"), c.get("title"), c.get("journal"), c.get("year"), c.get("doi"), c.get("url")])
    with open(f"{a.out}/response_times.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["run", "question_id", "domain", "status", "attempts", "started_at", "completed_at", "latency_seconds"])
        for label in runs:
            for q, rec in runs[label]["recs"].items():
                w.writerow([label, q, rec.get("domain"), rec.get("status"), rec.get("attempts"),
                            rec.get("started_at"), rec.get("completed_at"), rec.get("latency_seconds")])

    # 5. readable dossiers
    for label in runs:
        r = runs[label]
        if not r["recs"]: continue
        with open(f"{a.out}/answers_{label}.md", "w") as fh:
            fh.write(f"# Answers — {label}\n\nRun dir: `{r['dir']}`\n\n")
            for q in sorted(r["recs"]):
                rec = r["recs"][q]; g = r["grades"].get(q, {})
                fh.write(f"\n---\n\n## {q} — {rec.get('domain','')}\n\n")
                fh.write(f"**Question:** {rec.get('question','')}\n\n")
                if g:
                    fh.write(f"**Grade:** {g.get('score')}/100 ({g.get('letter_grade')})\n\n")
                fh.write(f"**Response time:** {rec.get('latency_seconds')}s | status: {rec.get('status')} | attempts: {rec.get('attempts')}\n\n")
                fh.write(f"**Answer:**\n\n{rec.get('answer','')}\n\n")
                cites = rec.get("citations") or []
                if cites:
                    fh.write(f"**Textbook citations ({len(cites)}):**\n\n")
                    for c in cites:
                        fh.write(f"- [{c.get('n')}] {c.get('book')} — {c.get('chapter')} (p.{c.get('page')})\n")
                    fh.write("\n")
                lit = (rec.get("raw_response") or {}).get("literature") or {}
                lc = lit.get("citations") or []
                if lc:
                    fh.write(f"**PubMed articles pulled ({len(lc)}) — NOT in graded answer (TKT-C1):**\n\n")
                    for c in lc:
                        fh.write(f"- [{c.get('n')}] PMID {c.get('pmid')} — {c.get('title')} ({c.get('journal')}, {c.get('year')})\n")
                    fh.write("\n")

    print(f"WROTE to {a.out}")
    for f in sorted(os.listdir(a.out)):
        print(f"  {os.path.getsize(os.path.join(a.out, f)):>9,d}  {f}")

if __name__ == "__main__":
    main()
