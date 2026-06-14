import time
from pathlib import Path

import lancedb

from neuro_core.config import load_config, resolve_device
from neuro_core.ingest import extract_pages, figure_records
from neuro_core.visual_embed import VisualEmbedder
from neuro_core.visual_index import build_visual_index


def figure_records_from_corpus(cfg):
    """One record per CROPPED plate, re-extracted from the corpus PDFs (renders skip
    already-cropped PNGs). Used in crop mode because the chunks table keeps only the
    first plate per page — this is the reliable per-plate source for a standalone
    (OOM-recovery) visual build."""
    out = []
    for pdf in sorted(Path(cfg.corpus_dir).glob("*.pdf")):
        recs = extract_pages(pdf, render=True, assets_dir=cfg.assets_dir,
                             dpi=cfg.figure_dpi,
                             area_threshold=cfg.figure_area_threshold,
                             figure_crop=True)
        out.extend(figure_records(recs))
    return out


def figure_pages_from_chunks(index_dir):
    """Distinct figure pages (deduped by figure_path) read from the existing
    `chunks` table, so we reuse the PNGs rendered during the text-index build."""
    tbl = lancedb.connect(str(index_dir)).open_table("chunks")
    t = tbl.to_arrow()
    cols = {c: t.column(c).to_pylist()
            for c in ("book", "chapter", "page", "has_figure", "figure_path",
                      "caption")}
    seen = {}
    for b, ch, p, hf, fp, cap in zip(cols["book"], cols["chapter"], cols["page"],
                                     cols["has_figure"], cols["figure_path"],
                                     cols["caption"]):
        if hf and fp and fp not in seen:
            seen[fp] = {"book": b, "chapter": ch or None, "page": p,
                        "figure_path": fp, "caption": cap or None}
    return list(seen.values())


def main():
    cfg = load_config()
    if cfg.figure_crop:
        pages = figure_records_from_corpus(cfg)
        print(f"{len(pages)} cropped plates to embed")
    else:
        pages = figure_pages_from_chunks(cfg.index_dir)
        print(f"{len(pages)} distinct figure pages to embed")
    device = resolve_device(cfg.embed_device)
    print(f"Loading visual model '{cfg.visual_model}' on '{device}' "
          f"(first run downloads weights) ...", flush=True)
    embedder = VisualEmbedder(cfg.visual_model, device=device)

    def progress(done, total):
        print(f"    embedded {done}/{total} figure images", flush=True)

    t0 = time.time()
    build_visual_index(pages, embedder, cfg.index_dir, on_progress=progress)
    print(f"\nVisual index built at {cfg.index_dir} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
