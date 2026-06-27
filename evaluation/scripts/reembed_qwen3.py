#!/usr/bin/env python3
"""Re-embed existing chunk text into a parallel INDEX_DIR with a different embedder.

Avoids the 2-4 hr PDF re-extraction in build_index: dumps the existing `chunks` table (text +
metadata + ids preserved) and re-embeds it with the target model, overwriting the destination
chunks table. Only the chunks table is needed for an Ask benchmark arm (figures/cards degrade
gracefully and are a separate lane). GPU strongly recommended.

    python evaluation/scripts/reembed_qwen3.py [SRC_INDEX_DIR] [DST_INDEX_DIR] [EMBED_MODEL]
"""
from __future__ import annotations

import sys
import time


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    src = argv[0] if argv else "/home/michael/neuro-textbook-rag/index"
    dst = argv[1] if len(argv) > 1 else "/home/michael/neuro-textbook-rag/index-qwen3"
    model = argv[2] if len(argv) > 2 else "Qwen/Qwen3-Embedding-0.6B"

    import lancedb

    from neuro_core.chunk import Chunk
    from neuro_core.embed import Embedder
    from neuro_core.index import TABLE, build_index

    rows = lancedb.connect(src).open_table(TABLE).to_arrow().to_pylist()
    chunks = [
        Chunk(id=r["id"], book=r["book"], chapter=r["chapter"] or None, page=int(r["page"]),
              text=r["text"], has_figure=bool(r.get("has_figure")),
              caption=r.get("caption") or None, figure_path=r.get("figure_path") or None)
        for r in rows
    ]
    print(f"[reembed] {len(chunks)} chunks  {src} -> {dst}  model={model}", flush=True)
    t0 = time.monotonic()
    build_index(chunks, Embedder(model, device="cuda"), dst, mode="overwrite")
    print(f"[reembed] done in {time.monotonic() - t0:.0f}s -> {dst}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
