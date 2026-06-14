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
        figs = engine.select_figures(q)
        want_book = case["expect_book_contains"].lower()
        want_page = case.get("expect_page")
        matches = [f for f in figs
                   if want_book in f.book.lower()
                   and (want_page is None or f.page == want_page)]
        ok = len(matches) > 0
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {q}")
        print(f"    figures attached: {[(f.book, f.page) for f in figs]}")
        if args.synthesize:
            result = engine.query(q)
            print(f"    answer: {result.answer[:600]}")
            print(f"    figures shown: "
                  f"{[(fg.book, fg.page) for fg in result.figures]}\n")
    print(f"\nFigure-retrieval gate: {passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
