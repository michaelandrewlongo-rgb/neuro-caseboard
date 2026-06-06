import argparse

from engine.query import query


def main():
    ap = argparse.ArgumentParser(
        description="Ask the neurosurgery textbook RAG a clinical question.")
    ap.add_argument("question", help="The clinical question, in quotes")
    args = ap.parse_args()

    result = query(args.question)
    print(result.answer)
    print("\nSources:")
    for c in result.citations:
        loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
        print(f"  [{c.n}] {loc}")
    if result.figures:
        print("\nFigures:")
        for f in result.figures:
            print(f"  [{f.source_n}] {f.book}, p.{f.page} -> {f.image_path}")


if __name__ == "__main__":
    main()
