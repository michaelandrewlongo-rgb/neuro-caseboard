import time
from pathlib import Path

from engine.config import load_config
from engine.ingest import extract_pages, coverage_from_records
from engine.chunk import chunk_pages
from engine.embed import Embedder
from engine.index import build_index


def main():
    cfg = load_config()
    pdfs = sorted(Path(cfg.corpus_dir).glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs in {cfg.corpus_dir}\n")

    # Read book-by-book with progress — extracting text off the D: drive is the
    # slow, I/O-bound stage, so show each book as it completes.
    records = []
    t0 = time.time()
    for i, pdf in enumerate(pdfs, 1):
        print(f"  [{i}/{len(pdfs)}] reading {pdf.name} ...", flush=True)
        recs = extract_pages(pdf)
        records.extend(recs)
        print(f"        {len(recs)} pages "
              f"({time.time() - t0:.0f}s elapsed)", flush=True)

    print("\nCoverage report (ingest gate):")
    for book, stats in coverage_from_records(records).items():
        print(f"  {book}: {stats['pages_with_text']}/{stats['pages']} pages "
              f"with text ({stats['coverage'] * 100:.1f}%)")

    chunks = chunk_pages(records, cfg.chunk_max_words, cfg.chunk_overlap_words)
    print(f"\nTotal pages: {len(records)} | total chunks: {len(chunks)}")

    print(f"Loading embedding model '{cfg.embed_model}' on device "
          f"'{cfg.embed_device}' (first run downloads ~1.3 GB) ...", flush=True)
    embedder = Embedder(cfg.embed_model, device=cfg.embed_device)

    def progress(done, total):
        print(f"    embedded {done}/{total} chunks", flush=True)

    t1 = time.time()
    build_index(chunks, embedder, cfg.index_dir, on_progress=progress)
    print(f"\nIndex built at {cfg.index_dir} "
          f"(embedding took {time.time() - t1:.0f}s)")


if __name__ == "__main__":
    main()
