import argparse

import yaml

from engine.query import get_engine


def main():
    ap = argparse.ArgumentParser(
        description="Figure-retrieval gate: did a figure page from the expected "
                    "book/page get surfaced?")
    ap.add_argument("--set", default="eval/figure_answers.yaml")
    ap.add_argument("--synthesize", action="store_true",
                    help="Also run full multimodal query() and print the answer "
                         "+ which figures were shown, for blinded faithfulness review")
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
        want_book = case["expect_book_contains"].lower()
        want_page = case.get("expect_page")
        fig_hits = [h for h in top if h.has_figure
                    and want_book in h.book.lower()
                    and (want_page is None or h.page == want_page)]
        ok = len(fig_hits) > 0
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {q}")
        print(f"    figure hits in top: "
              f"{[(h.book, h.page) for h in top if h.has_figure]}")
        if args.synthesize:
            result = engine.query(q)
            print(f"    answer: {result.answer[:600]}")
            print(f"    figures shown: "
                  f"{[(fg.book, fg.page) for fg in result.figures]}\n")
    print(f"\nFigure-retrieval gate: {passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
