#!/usr/bin/env python3
"""Retrieval-recall probe — turn "is the chunking good enough?" into a number.

For a fixed set of neurosurgery questions with KNOWN answer terms, this runs the
*real* Ask-pathway retrieval (hybrid_search -> rerank -> off-domain sink, exactly
as neuro_core.query.Engine._retrieve does) and measures whether the answer-bearing
chunk actually surfaces. No synthesis, no LLM, no figures — just retrieval.

Two recall numbers, because they localize different failures:
  * recall@RETRIEVE_K (the 40-candidate pool, BEFORE rerank) = retrieval CEILING.
    A miss here means the answer chunk's vector/text never matched the query at all
    -> an EMBEDDING/CHUNKING problem (signal diluted in a big chunk, or the concept
    was split across a chunk/page boundary). This is the chunking diagnostic.
  * recall@RERANK_K (the top-12 actually handed to the synthesizer) = what the model
    sees. High ceiling but low @12 -> the RERANKER buried it, not chunking.

Matching is keyword-presence: a retrieved chunk "answers" query Q if its text
contains any of Q's `any_of` terms (case-insensitive). This is deliberately simple.
# ponytail: keyword match, not NLI. A "miss" can be a phrasing mismatch rather than
# a true retrieval failure -> the probe PRINTS the top retrieved chunks for every
# miss so you can eyeball true-miss vs false-negative. Treat absolute numbers as
# directional and the per-query snippets as the real evidence. Upgrade to an NLI/
# entailment match only if the keyword false-negative rate proves too high to read.

Usage:
  python scripts/retrieval_recall_probe.py            # run the probe (loads models)
  python scripts/retrieval_recall_probe.py --selftest # check the recall math, no models
  python scripts/retrieval_recall_probe.py --gold my_gold.json   # custom gold set
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# Known neurosurgery facts -> distinctive answer term(s) any textbook would use.
# `any_of` uses OR semantics (synonyms) to tolerate phrasing variance.
GOLD = [
    {"q": "What artery is classically torn in an epidural hematoma?",
     "any_of": ["middle meningeal"]},
    {"q": "What is the most common location of hypertensive intracerebral hemorrhage?",
     "any_of": ["putamen", "basal ganglia"]},
    {"q": "What is the most common site of saccular (berry) aneurysms?",
     "any_of": ["anterior communicating", "acom", "acoa"]},
    {"q": "Which artery typically compresses the nerve in trigeminal neuralgia?",
     "any_of": ["superior cerebellar"]},
    {"q": "What are the components of Cushing's triad in raised intracranial pressure?",
     "any_of": ["bradycardia"]},
    {"q": "At what vertebral level does the conus medullaris typically end in adults?",
     "any_of": ["conus medullaris"]},
    {"q": "Where are vestibular schwannomas (acoustic neuromas) located?",
     "any_of": ["cerebellopontine", "internal auditory", "internal acoustic"]},
    {"q": "What veins are torn in an acute subdural hematoma?",
     "any_of": ["bridging vein"]},
    {"q": "What surgical approach is used for most pituitary adenomas?",
     "any_of": ["transsphenoidal"]},
    {"q": "What is the classic triad of normal pressure hydrocephalus?",
     "any_of": ["gait", "hakim"]},
    {"q": "What grading system is used for cerebral arteriovenous malformations?",
     "any_of": ["spetzler"]},
    {"q": "What is the histologic hallmark of glioblastoma?",
     "any_of": ["pseudopalisad", "microvascular proliferation"]},
    {"q": "Which cranial nerves run within the cavernous sinus?",
     "any_of": ["cavernous sinus", "abducens"]},
    {"q": "What nerve is at risk of injury during anterior cervical discectomy and fusion?",
     "any_of": ["recurrent laryngeal"]},
    {"q": "What doctrine relates the intracranial volumes of brain, blood, and CSF?",
     "any_of": ["monro", "kellie"]},
    {"q": "What structure produces cerebrospinal fluid?",
     "any_of": ["choroid plexus"]},
    {"q": "What malformation involves cerebellar tonsillar herniation below the foramen magnum?",
     "any_of": ["chiari", "tonsillar herniation"]},
    {"q": "What syndrome results from lumbosacral nerve root compression causing saddle anesthesia?",
     "any_of": ["cauda equina"]},
    {"q": "What is the most common primary malignant brain tumor in adults?",
     "any_of": ["glioblastoma", "gbm"]},
    {"q": "What is a common deep brain stimulation target for Parkinson's disease?",
     "any_of": ["subthalamic", "globus pallidus", "stn", "gpi"]},
]


def first_hit_rank(hits, any_of):
    """1-based rank of the first hit whose text contains any `any_of` term, else None."""
    terms = [t.lower() for t in any_of]
    for i, h in enumerate(hits, 1):
        text = (getattr(h, "text", "") or "").lower()
        if any(t in text for t in terms):
            return i
    return None


def recall_at(ranks, k, n):
    """Fraction of the n queries whose first hit landed at rank <= k."""
    return sum(1 for r in ranks if r is not None and r <= k) / n if n else 0.0


def mrr(ranks):
    """Mean reciprocal rank; a miss (None) contributes 0."""
    return sum((1.0 / r) for r in ranks if r) / len(ranks) if ranks else 0.0


def _snippet(h, n=110):
    text = " ".join((getattr(h, "text", "") or "").split())
    return text[:n] + ("…" if len(text) > n else "")


def run(gold):
    from neuro_core.config import load_config
    from neuro_core.embed import Embedder
    from neuro_core.index import Index
    from neuro_core.rerank import Reranker
    from neuro_core.query import _offdomain  # the exact off-domain sink Engine._retrieve uses

    config = load_config()
    print(f"index_dir = {config.index_dir}")
    print(f"embed={config.embed_model}  rerank={config.rerank_model}  "
          f"retrieve_k={config.retrieve_k}  rerank_k={config.rerank_k}\n")

    embedder = Embedder(config.embed_model, device=config.embed_device)
    index = Index(config.index_dir)
    reranker = Reranker(config.rerank_model, device=config.embed_device)

    ranks_full = []      # rank of first hit within the full reranked pool (for recall@k / MRR)
    ceiling_hit = []     # was the answer chunk anywhere in the pre-rerank candidate pool?
    window_words = []    # word counts of the chunks the synthesizer actually receives

    for g in gold:
        q, any_of = g["q"], g["any_of"]
        qv = embedder.embed_query(q)
        pool = index.hybrid_search(q, qv, config.retrieve_k)        # candidate pool (ceiling)
        ranked = reranker.rerank(q, pool, config.retrieve_k)        # score all candidates
        ranked.sort(key=lambda h: _offdomain(q, h.text))           # stable off-domain sink
        window = ranked[: config.rerank_k]                         # what synthesis sees

        r_full = first_hit_rank(ranked, any_of)
        in_pool = first_hit_rank(pool, any_of) is not None
        ranks_full.append(r_full)
        ceiling_hit.append(in_pool)
        window_words.extend(len((getattr(h, "text", "") or "").split()) for h in window)

        in_window = r_full is not None and r_full <= config.rerank_k
        mark = "✓" if in_window else ("·" if in_pool else "✗")
        where = ""
        if r_full is not None:
            h = ranked[r_full - 1]
            where = f"  rank {r_full:>2}  [{h.book} p{h.page}]"
        elif in_pool:
            where = "  in pool, sunk below rerank_k"
        print(f"  {mark} {q[:62]:<62}{where}")
        if not in_window:  # show evidence so you can judge true-miss vs keyword false-negative
            for h in window[:3]:
                print(f"        ¬ [{h.book} p{h.page}] {_snippet(h)}")

    n = len(gold)
    print("\n" + "=" * 64)
    print(f"  queries:                 {n}")
    print(f"  recall@1:                {recall_at(ranks_full, 1, n):.2f}")
    print(f"  recall@3:                {recall_at(ranks_full, 3, n):.2f}")
    print(f"  recall@5:                {recall_at(ranks_full, 5, n):.2f}")
    print(f"  recall@10:               {recall_at(ranks_full, 10, n):.2f}")
    print(f"  recall@{config.rerank_k} (synth window):  {recall_at(ranks_full, config.rerank_k, n):.2f}")
    print(f"  recall@{config.retrieve_k} (CEILING):     {sum(ceiling_hit) / n:.2f}")
    print(f"  MRR:                     {mrr(ranks_full):.3f}")
    if window_words:
        avg = sum(window_words) / len(window_words)
        print(f"  mean words / retrieved chunk: {avg:.0f}  (config CHUNK_MAX_WORDS-bounded)")
    print("=" * 64)
    print("  ✓ in synth window   · retrieved but reranked out   ✗ not retrieved at all")
    print("  Low CEILING => chunking/embedding. High ceiling, low synth-window => reranker.")


def _selftest():
    class H:
        def __init__(self, t):
            self.text = t
    ranked = [H("alpha band"), H("the middle meningeal artery"), H("beta")]
    assert first_hit_rank(ranked, ["middle meningeal"]) == 2
    assert first_hit_rank(ranked, ["MIDDLE MENINGEAL"]) == 2          # case-insensitive
    assert first_hit_rank(ranked, ["nope"]) is None
    ranks = [1, 2, None, 5]
    assert recall_at(ranks, 1, 4) == 0.25
    assert recall_at(ranks, 3, 4) == 0.50
    assert recall_at(ranks, 5, 4) == 0.75
    assert recall_at([], 5, 0) == 0.0
    assert abs(mrr([1, 2, None, 4]) - (1 + 0.5 + 0 + 0.25) / 4) < 1e-9
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true", help="check recall math, load no models")
    ap.add_argument("--gold", type=Path, help="JSON list of {q, any_of} overriding the default set")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        return
    gold = json.loads(args.gold.read_text()) if args.gold else GOLD
    run(gold)


if __name__ == "__main__":
    main()
