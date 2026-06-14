import argparse

import yaml

from neuro_core.query import get_engine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="eval/known_answers.yaml")
    ap.add_argument("--synthesize", action="store_true",
                    help="Also call the LLM and print answers for blinded review")
    args = ap.parse_args()

    with open(args.set) as f:
        cases = yaml.safe_load(f)
    engine = get_engine()
    passed = 0
    for case in cases:
        q = case["question"]
        qv = engine.embedder.embed_query(q)
        hits = engine.index.hybrid_search(q, qv, engine.config.retrieve_k)
        top = engine.reranker.rerank(q, hits, engine.config.rerank_k)
        books = [h.book for h in top]
        want = case["expect_book_contains"].lower()
        ok = any(want in b.lower() for b in books)
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {q}")
        print(f"    top books: {books}")
        if args.synthesize:
            # Reuse the passages already retrieved/reranked above.
            syn = engine.synth_fn(q, top, [], [], engine.synth_client)
            print(f"    answer: {syn.answer[:600]}\n")
    print(f"\nRetrieval gate: {passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
