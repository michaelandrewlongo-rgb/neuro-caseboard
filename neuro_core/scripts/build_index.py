import argparse
import sys
import time
from pathlib import Path

import lancedb

from neuro_core.config import load_config, resolve_device
from neuro_core.ingest import extract_pages, coverage_from_records, figure_records
from neuro_core.chunk import chunk_pages
from neuro_core.embed import Embedder
from neuro_core.index import build_index, TABLE, _table_names
from neuro_core.visual_embed import VisualEmbedder
from neuro_core.visual_index import build_visual_index


def _indexed_books(index_dir):
    """Distinct ``book`` stems already present in the chunks table (empty if none)."""
    db = lancedb.connect(str(index_dir))
    if TABLE not in _table_names(db):
        return set()
    return set(db.open_table(TABLE).to_arrow().column("book").to_pylist())


def select_pdfs(all_pdfs, book_args, new_only, indexed_books):
    """Choose which PDFs to (re)index and the write mode (pure; no I/O).

    - ``book_args`` (stems or paths): index exactly those, appended.
    - ``new_only``: index only corpus books absent from ``indexed_books``, appended.
    - neither: index everything with a full overwrite (unchanged default).
    Returns ``(selected_pdfs, mode)``.
    """
    if book_args:
        wanted = {Path(b).stem for b in book_args}
        return [p for p in all_pdfs if p.stem in wanted], "append"
    if new_only:
        return [p for p in all_pdfs if p.stem not in indexed_books], "append"
    return list(all_pdfs), "overwrite"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="build_index")
    ap.add_argument("--new-only", action="store_true",
                    help="index only corpus books not already in the chunks table (append)")
    ap.add_argument("--book", action="append", default=[], metavar="STEM_OR_PATH",
                    help="index only this book (stem or PDF path); repeatable; append mode")
    args = ap.parse_args(argv)

    cfg = load_config()
    all_pdfs = sorted(Path(cfg.corpus_dir).glob("*.pdf"))
    indexed = _indexed_books(cfg.index_dir) if args.new_only else set()
    pdfs, mode = select_pdfs(all_pdfs, args.book, args.new_only, indexed)

    print(f"Corpus {cfg.corpus_dir}: {len(all_pdfs)} PDFs; "
          f"selected {len(pdfs)} to index [mode={mode}]\n")
    if not pdfs:
        print("Nothing to index — all selected books already present.")
        return 0

    # Read book-by-book with progress — text extraction is the slow I/O-bound stage.
    records = []
    t0 = time.time()
    for i, pdf in enumerate(pdfs, 1):
        print(f"  [{i}/{len(pdfs)}] reading {pdf.name} ...", flush=True)
        recs = extract_pages(pdf, render=True, assets_dir=cfg.assets_dir,
                             dpi=cfg.figure_dpi,
                             area_threshold=cfg.figure_area_threshold,
                             figure_crop=cfg.figure_crop)
        records.extend(recs)
        print(f"        {len(recs)} pages "
              f"({time.time() - t0:.0f}s elapsed)", flush=True)

    print("\nCoverage report (ingest gate):")
    for book, stats in coverage_from_records(records).items():
        print(f"  {book}: {stats['pages_with_text']}/{stats['pages']} pages "
              f"with text ({stats['coverage'] * 100:.1f}%), "
              f"{stats['pages_with_figures']} figure pages")

    chunks = chunk_pages(records, cfg.chunk_max_words, cfg.chunk_overlap_words)
    print(f"\nTotal pages: {len(records)} | total chunks: {len(chunks)}")

    device = resolve_device(cfg.embed_device)
    print(f"Loading embedding model '{cfg.embed_model}' on device "
          f"'{device}' (requested '{cfg.embed_device}'; first run downloads "
          f"~1.3 GB) ...", flush=True)
    if device == "cpu":
        print("  WARNING: running on CPU — embedding is slow. "
              "Set EMBED_DEVICE=cuda if you have a GPU.", flush=True)
    embedder = Embedder(cfg.embed_model, device=device)

    def progress(done, total):
        print(f"    embedded {done}/{total} chunks", flush=True)

    t1 = time.time()
    build_index(chunks, embedder, cfg.index_dir, on_progress=progress, mode=mode)
    print(f"\nIndex {'extended' if mode == 'append' else 'built'} at {cfg.index_dir} "
          f"(embedding took {time.time() - t1:.0f}s)")

    if cfg.visual_retrieval:
        if cfg.figure_crop:
            fig_pages = figure_records(records)        # one record per cropped plate
        else:
            fig_pages = {}
            for r in records:
                if r.has_figure and r.figure_path and r.figure_path not in fig_pages:
                    fig_pages[r.figure_path] = {
                        "book": r.book, "chapter": r.chapter, "page": r.page,
                        "figure_path": r.figure_path, "caption": r.caption}
            fig_pages = list(fig_pages.values())
        kind = "cropped plates" if cfg.figure_crop else "figure pages"
        print(f"\nBuilding visual index ({len(fig_pages)} {kind}) "
              f"with '{cfg.visual_model}' [mode={mode}] ...", flush=True)
        vemb = VisualEmbedder(cfg.visual_model, device=device)
        build_visual_index(fig_pages, vemb, cfg.index_dir, mode=mode)
        print("Visual index built.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
