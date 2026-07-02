#!/usr/bin/env python3
"""Chunking / ingestion ablation benchmark — reproducible.

Holds the embed + rerank + synth models CONSTANT (they are the confound) and varies only
the chunker: boundary strategy (page/paragraph/sentence/heading/chapter) x (max_words,
overlap). For each arm it rebuilds a text-only LanceDB index over a FIXED sub-corpus and
runs the *real* Ask retrieval path (hybrid_search -> rerank -> off-domain sink, identical
to neuro_core.query.Engine._retrieve), then records:

  retrieval quality : recall@1/3/5/10, recall@rerank_k (synth window),
                      recall@retrieve_k (CEILING), MRR   [gold = retrieval_recall_probe.GOLD]
  chunk shape       : n_chunks, mean/median/p90 words, %chunks<50w (fragmentation)
  duplication       : overlap-induced repeated words as % of emitted words
  index size        : bytes of the chunks table on disk
  latency           : build (embed) seconds, mean per-query retrieval seconds

Why retrieval and not groundedness/citation-accuracy per arm: those are produced by the
(held-constant) synthesizer + entailment gate downstream of retrieval, so chunking's causal
effect on them is mediated entirely by whether the answer chunk is retrieved. The CEILING /
recall numbers here ARE the chunking signal; groundedness is a paid end-to-end confirmation
run once on the winner (see the report), not per arm.

Sub-corpus default = four broad-coverage general references that between them contain the 20
gold facts. Extraction happens once and is cached; only chunking+embedding re-runs per arm.

Usage:
  python3 scripts/chunking_benchmark.py                 # full arm set -> eval/chunking-benchmark/
  python3 scripts/chunking_benchmark.py --arms strategy # just the strategy sweep
  python3 scripts/chunking_benchmark.py --quick         # 1 book, 3 arms (smoke)
  python3 scripts/chunking_benchmark.py --selftest      # no models, checks stats math
"""
import argparse
import json
import os
import pickle
import statistics as st
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from neuro_core.chunk_strategies import chunk_records                       # noqa: E402
from scripts.retrieval_recall_probe import GOLD, first_hit_rank, recall_at, mrr  # noqa: E402

DEFAULT_BOOKS = [
    "Greenberg Handbook of Neurosurgery",
    "Rhoton Cranial Anatomy",
    "Decision making in neurovascular disease",
    "The NeuroICU Book",
]

OUT_DIR = REPO / "eval" / "chunking-benchmark"
CACHE = OUT_DIR / "records_cache"
WORK_INDEX = Path(os.environ.get("CLAUDE_JOB_DIR", "/tmp")) / "tmp" / "chunkbench_index"


def arm_set(name):
    """(strategy, max_words, overlap) arms. Baseline is page/600/80 (the shipped default)."""
    strategy = [(s, 600, 80) for s in ("page", "paragraph", "sentence", "heading", "chapter")]
    size = [("page", mw, ov) for mw, ov in [(300, 40), (600, 80), (900, 120), (1200, 160)]]
    overlap = [("page", 600, ov) for ov in (0, 80, 160, 240)]
    if name == "strategy":
        return strategy
    if name == "size":
        return size
    if name == "overlap":
        return overlap
    # full: dedupe (page/600/80 appears in all three)
    seen, out = set(), []
    for a in strategy + size + overlap:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def load_records(books):
    """Extract each book's PageRecords once; cache pickled per book (extraction is the slow
    I/O stage, embedding is GPU-fast, so we pay extraction once and re-chunk per arm).

    Fails fast on the mistakes that silently wasted a run: a stale/wrong CORPUS_DIR, a
    misspelled/missing book, or an empty extraction — instead of building an empty index and
    dying later inside LanceDB with "Cannot create table from empty list".
    """
    from neuro_core.config import load_config
    from neuro_core.ingest import extract_pages
    cfg = load_config()
    CACHE.mkdir(parents=True, exist_ok=True)
    all_recs = []
    for b in books:
        cf = CACHE / (b.replace("/", "_") + ".pkl")
        if cf.exists():
            recs = pickle.loads(cf.read_bytes())
        else:
            # Only touch the corpus when we actually need to extract (cached books don't).
            if not Path(cfg.corpus_dir).is_dir():
                raise SystemExit(
                    f"CORPUS_DIR does not exist: {cfg.corpus_dir}\n"
                    f"  The config default is stale on this machine. Set it, e.g.:\n"
                    f"    export CORPUS_DIR=/home/michael/textbook_pdfs")
            pdf = Path(cfg.corpus_dir) / (b + ".pdf")
            if not pdf.exists():
                available = sorted(p.stem for p in Path(cfg.corpus_dir).glob("*.pdf"))
                raise SystemExit(
                    f"book not found: {pdf}\n  available in {cfg.corpus_dir}:\n    "
                    + "\n    ".join(available))
            t = time.time()
            recs = extract_pages(pdf, render=False)   # text only; no figures/GPU
            cf.write_bytes(pickle.dumps(recs))
            print(f"  extracted {b}: {len(recs)} pages in {time.time()-t:.0f}s", flush=True)
        if not recs:
            raise SystemExit(f"book extracted 0 pages (scanned/no text layer?): {b}")
        all_recs.append((b, recs))
    if not all_recs:
        raise SystemExit("no books to benchmark — check --books and CORPUS_DIR")
    return all_recs


def chunk_shape(chunks, source_words):
    words = [len(c.text.split()) for c in chunks]
    total = sum(words)
    dup = (total - source_words) / total if total else 0.0
    return {
        "n_chunks": len(chunks),
        "mean_words": round(st.mean(words), 1) if words else 0,
        "median_words": int(st.median(words)) if words else 0,
        "p90_words": int(sorted(words)[int(0.9 * len(words))]) if words else 0,
        "frag_pct_lt50w": round(100 * sum(w < 50 for w in words) / len(words), 1) if words else 0,
        "total_words": total,
        "dup_pct": round(100 * dup, 1),
    }


def dir_bytes(path):
    return sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file())


def build_arm(book_recs, strategy, max_words, overlap):
    """Chunk every book with the arm's params; assign globally-unique ids."""
    chunks, source_words = [], 0
    for book, recs in book_recs:
        cs = chunk_records(recs, strategy, max_words, overlap)
        # atoms' concatenated length == chunk words at overlap 0; approximate source words as
        # the arm's own emitted words minus overlap by re-chunking at overlap 0 once per book.
        base = chunk_records(recs, strategy, max_words, 0)
        source_words += sum(len(c.text.split()) for c in base)
        for i, c in enumerate(cs):
            c.id = f"{book}::{strategy}::{i}"
            c.book = book
            chunks.append(c)
    return chunks, source_words


def run(books, arm_name, out_path):
    from neuro_core.config import load_config
    from neuro_core.embed import Embedder
    from neuro_core.index import build_index, Index
    from neuro_core.rerank import Reranker
    from neuro_core.query import _offdomain

    cfg = load_config()
    print(f"embed={cfg.embed_model}  rerank={cfg.rerank_model}  "
          f"retrieve_k={cfg.retrieve_k}  rerank_k={cfg.rerank_k}", flush=True)
    print(f"sub-corpus: {books}", flush=True)

    book_recs = load_records(books)
    embedder = Embedder(cfg.embed_model, device=cfg.embed_device)   # loaded ONCE, held constant
    reranker = Reranker(cfg.rerank_model, device=cfg.embed_device)
    WORK_INDEX.parent.mkdir(parents=True, exist_ok=True)

    arms = arm_set(arm_name)
    results = []
    for strategy, mw, ov in arms:
        tag = f"{strategy}/{mw}/{ov}"
        t = time.time()
        chunks, source_words = build_arm(book_recs, strategy, mw, ov)
        chunk_s = time.time() - t
        if not chunks:
            raise SystemExit(f"arm {tag} produced 0 chunks — chunker/strategy bug")
        shape = chunk_shape(chunks, source_words)

        # Clean the work dir first: LanceDB's overwrite keeps stale versions until compaction,
        # which would make dir_bytes() accumulate across arms (a monotonically-growing, useless
        # number). A fresh dir per arm makes index_mb a true per-arm size.
        import shutil
        shutil.rmtree(WORK_INDEX, ignore_errors=True)
        t = time.time()
        build_index(chunks, embedder, WORK_INDEX, mode="overwrite")
        build_s = time.time() - t
        index_bytes = dir_bytes(WORK_INDEX)
        index = Index(WORK_INDEX)

        ranks, ceiling, qtimes, per_q = [], [], [], []
        for g in GOLD:
            q, any_of = g["q"], g["any_of"]
            t0 = time.time()
            qv = embedder.embed_query(q)
            pool = index.hybrid_search(q, qv, cfg.retrieve_k)
            ranked = reranker.rerank(q, pool, cfg.retrieve_k)
            ranked.sort(key=lambda h: _offdomain(q, h.text))
            qtimes.append(time.time() - t0)
            r = first_hit_rank(ranked, any_of)
            in_pool = first_hit_rank(pool, any_of) is not None
            ranks.append(r)
            ceiling.append(in_pool)
            per_q.append({"q": q, "rank": r, "in_pool": in_pool})

        n = len(GOLD)
        metrics = {
            "arm": tag, "strategy": strategy, "max_words": mw, "overlap": ov,
            "recall@1": round(recall_at(ranks, 1, n), 3),
            "recall@3": round(recall_at(ranks, 3, n), 3),
            "recall@5": round(recall_at(ranks, 5, n), 3),
            "recall@10": round(recall_at(ranks, 10, n), 3),
            f"recall@{cfg.rerank_k}_window": round(recall_at(ranks, cfg.rerank_k, n), 3),
            f"recall@{cfg.retrieve_k}_ceiling": round(sum(ceiling) / n, 3),
            "mrr": round(mrr(ranks), 3),
            "chunk_s": round(chunk_s, 1),
            "build_s": round(build_s, 1),
            "query_ms": round(1000 * st.mean(qtimes), 1),
            "index_mb": round(index_bytes / 1e6, 1),
            **shape,
            "misses": [p["q"][:60] for p in per_q if p["rank"] is None],
        }
        results.append(metrics)
        print(f"  {tag:<22} ceil={metrics[f'recall@{cfg.retrieve_k}_ceiling']:.2f} "
              f"win={metrics[f'recall@{cfg.rerank_k}_window']:.2f} mrr={metrics['mrr']:.3f} "
              f"n={shape['n_chunks']} dup={shape['dup_pct']}% {metrics['index_mb']}MB "
              f"chunk={chunk_s:.0f}s build={build_s:.0f}s q={metrics['query_ms']:.0f}ms",
              flush=True)

        # incremental write: a crash on a later arm never loses completed arms
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "embed_model": cfg.embed_model, "rerank_model": cfg.rerank_model,
            "retrieve_k": cfg.retrieve_k, "rerank_k": cfg.rerank_k,
            "books": books, "n_gold": len(GOLD), "arms": results,
        }
        out_path.write_text(json.dumps(payload, indent=2))

    print(f"\nwrote {out_path}", flush=True)
    return payload


def _selftest():
    class C:
        def __init__(self, t):
            self.text = t
    chunks = [C("a b c"), C("d e f g h"), C(" ".join(["x"] * 60))]
    s = chunk_shape(chunks, source_words=68)
    assert s["n_chunks"] == 3
    assert s["total_words"] == 68
    assert s["dup_pct"] == 0.0
    assert s["frag_pct_lt50w"] == round(100 * 2 / 3, 1)
    s2 = chunk_shape(chunks, source_words=34)   # emitted 68, source 34 -> 50% dup
    assert s2["dup_pct"] == 50.0
    print("chunking_benchmark selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", choices=["strategy", "size", "overlap", "full"], default="full")
    ap.add_argument("--books", nargs="*", default=DEFAULT_BOOKS)
    ap.add_argument("--quick", action="store_true", help="1 book, strategy arms (smoke)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        return
    books = [DEFAULT_BOOKS[0]] if args.quick else args.books
    arm_name = "strategy" if args.quick else args.arms
    out = args.out or (OUT_DIR / f"results_{arm_name}.json")
    run(books, arm_name, out)


if __name__ == "__main__":
    main()
