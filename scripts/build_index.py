from engine.config import load_config
from engine.ingest import iter_corpus, coverage_report
from engine.chunk import chunk_pages
from engine.embed import Embedder
from engine.index import build_index


def main():
    cfg = load_config()
    print("Coverage report (ingest gate):")
    for book, stats in coverage_report(cfg.corpus_dir).items():
        print(f"  {book}: {stats['pages_with_text']}/{stats['pages']} pages "
              f"with text ({stats['coverage'] * 100:.1f}%)")

    records = list(iter_corpus(cfg.corpus_dir))
    chunks = chunk_pages(records, cfg.chunk_max_words, cfg.chunk_overlap_words)
    print(f"Total pages: {len(records)} | total chunks: {len(chunks)}")

    embedder = Embedder(cfg.embed_model, device=cfg.embed_device)
    build_index(chunks, embedder, cfg.index_dir)
    print(f"Index built at {cfg.index_dir}")


if __name__ == "__main__":
    main()
