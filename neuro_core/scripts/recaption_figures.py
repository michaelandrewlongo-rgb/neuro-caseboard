"""Re-caption figure plates with Gemini multimodal so each figure's caption NAMES the
specific surgical anatomy it shows (arteries/branches, cranial nerves, bony landmarks,
screw trajectories, the approach) — not the source's generic first-line label.

Why: the lexical figure-retrieval lane (neuro-caseboard ``FigureCaptionRetriever``) pools
and ranks figures by their OWN caption. Source captions are column-truncated first lines
("FIGURE 2.3. Pterional exposure of the circle of Willis ...") that never name the M1/MCA
bifurcation even when the plate clearly shows it, so the gold plate can't be pooled. A
Gemini caption that reads the labels off the plate and names the structures fixes this at
the corpus layer (no retrieval-code tuning, no re-embedding — the image vectors are
untouched).

Two phases:
  caption  — call Gemini per figure image, append {id, caption} to a JSONL checkpoint
             (resumable: already-captioned ids are skipped).
  apply    — read the checkpoint, add/refresh a ``gemini_caption`` column on the
             ``figures`` LanceDB table (preserving every other field incl. ``vector``),
             rewriting the table in place.

Caseboard prefers ``gemini_caption`` when non-empty, else the source ``caption`` — so
partial application is always safe.

Usage:
  python -m scripts.recaption_figures caption --books "Rhoton" --workers 24
  python -m scripts.recaption_figures caption --all --workers 24
  python -m scripts.recaption_figures apply
  python -m scripts.recaption_figures status
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import lancedb

from neuro_core.config import load_config
from neuro_core.synth_clients import VertexSynthClient

CKPT = Path(__file__).resolve().parent.parent / "index" / "_gemini_captions.jsonl"

# Diagnostic / ICU books are radiographs and tracings, not operative anatomy; the caseboard
# figure lane filters them out entirely, so don't spend caption calls on them.
DIAGNOSTIC_BOOKS = ("neuroradiology core requisites", "neuroradiology key differential",
                    "neuroicu", "neurocritical")

SYSTEM = (
    "You are a neurosurgical anatomist writing a dense retrieval caption for a surgical "
    "anatomy figure. In at most two sentences, NAME the specific structures a surgeon "
    "needs from this figure and the surgical approach/exposure or construct shown. Put the "
    "single most surgically important structures and the approach FIRST. Name arteries and "
    "their branches, cranial nerves, bony and dural landmarks, named tissue planes, and "
    "screw entry points / trajectories. For every abbreviation give the clean abbreviation "
    "WITHOUT periods immediately followed by the full name in parentheses on first use, "
    "e.g. 'MCA (middle cerebral artery) M1 segment bifurcating into superior and inferior "
    "M2 trunks with lenticulostriate perforators', 'CN VII (facial nerve)', 'C2 pars "
    "interarticularis'. READ any anatomical labels printed on the figure and incorporate "
    "them, rewriting dotted abbreviations (M.C.A.) as clean ones (MCA). Use precise "
    "neurosurgical terminology. Do NOT describe page layout, panel letters, or say 'this "
    "figure shows'. Do NOT mention imaging modality unless the image ITSELF is a "
    "radiograph/CT/MRI/angiogram. If the figure shows only surgical instruments, patient "
    "positioning, or a skin incision with no internal anatomy, say that plainly in a few "
    "words and name nothing anatomical."
)
USER = ("Write the retrieval caption naming the specific surgical anatomy, landmarks, and "
        "approach in this figure. Output only the caption text, no preamble.")

MAX_CAPTION_CHARS = 700  # safety clamp; Gemini 1-2 sentence captions run ~250-800 chars


def _load_done() -> set[str]:
    done: set[str] = set()
    if CKPT.exists():
        with CKPT.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    done.add(json.loads(line)["id"])
                except Exception:
                    pass
    return done


def _select_rows(cfg, book_filters, include_all):
    db = lancedb.connect(str(cfg.index_dir))
    t = db.open_table("figures").to_arrow()
    ids = t.column("id").to_pylist()
    books = t.column("book").to_pylist()
    paths = t.column("figure_path").to_pylist()
    rows = []
    for _id, book, path in zip(ids, books, paths):
        bl = (book or "").lower()
        if any(d in bl for d in DIAGNOSTIC_BOOKS):
            continue
        if not (path and os.path.isfile(path)):
            continue
        if not include_all:
            if not any(bf.lower() in bl for bf in book_filters):
                continue
        rows.append({"id": _id, "book": book, "figure_path": path})
    return rows


def cmd_caption(args):
    cfg = load_config()
    rows = _select_rows(cfg, args.books or [], args.all)
    done = _load_done()
    todo = [r for r in rows if r["id"] not in done]
    print(f"selected {len(rows)} figures; {len(done)} already captioned; {len(todo)} to do",
          flush=True)
    if not todo:
        return
    # One client per region. gemini-2.5-pro latency is ~15s/call in EVERY region, so a single
    # region is quota-bound (429 RESOURCE_EXHAUSTED), not latency-bound. Spreading calls across
    # regions multiplies throughput at the SAME (pro) quality. On a 429 we immediately fail over
    # to the next region rather than waiting out one region's quota.
    locations = [s.strip() for s in (args.locations or "").split(",") if s.strip()]
    if not locations:
        locations = [cfg.google_cloud_location]
    model = args.model or cfg.vertex_model
    # Per-call timeout so a hung connection to the endpoint can't freeze a worker thread
    # indefinitely (a no-timeout pool stalls silently when the endpoint stops responding);
    # the timeout raises, the work() loop then fails over / backs off and retries.
    clients = [VertexSynthClient(cfg.google_cloud_project, loc, model, timeout_ms=120_000)
               for loc in locations]
    print(f"model={model}; using {len(locations)} region(s): {', '.join(locations)}", flush=True)
    lock = threading.Lock()
    counter = {"done": 0, "err": 0}
    fh = CKPT.open("a")

    def work(row):
        with open(row["figure_path"], "rb") as f:
            img = f.read()
        order = list(range(len(clients)))
        random.shuffle(order)                    # spread initial load across regions
        last = None
        for attempt in range(max(6, 2 * len(clients))):
            cl = clients[order[attempt % len(order)]]
            try:
                cap = (cl.generate(SYSTEM, USER, [img]) or "").strip()
                return row["id"], " ".join(cap.split())[:MAX_CAPTION_CHARS]
            except Exception as e:  # 429 / 5xx / transient — rotate region, back off per cycle
                last = e
                if (attempt + 1) % len(order) == 0:   # backed off only after trying all regions
                    time.sleep(min(2 ** (attempt // len(order)), 20) + random.random())
        raise last

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, r): r for r in todo}
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                _id, cap = fut.result()
            except Exception as e:
                counter["err"] += 1
                print(f"  ERR {r['book']} {r['id']}: {e}", flush=True)
                continue
            with lock:
                fh.write(json.dumps({"id": _id, "caption": cap, "model": model}) + "\n")
                fh.flush()
                counter["done"] += 1
                n = counter["done"]
            if n % 25 == 0 or n == len(todo):
                print(f"  captioned {n}/{len(todo)} (err {counter['err']})", flush=True)
    fh.close()
    print(f"done: {counter['done']} captioned, {counter['err']} errors", flush=True)


def cmd_apply(args):
    cfg = load_config()
    # Fold human review corrections (exported from caption_review.html) into the checkpoint
    # first, as authoritative last-wins lines, so they override the model caption.
    if getattr(args, "corrections", None):
        data = json.loads(Path(args.corrections).read_text())
        edited = [d for d in data if d.get("edited") and d.get("caption")]
        flagged_only = [d["id"] for d in data if d.get("flag") and not d.get("edited")]
        with CKPT.open("a") as fh:
            for d in edited:
                fh.write(json.dumps({"id": d["id"], "caption": d["caption"].strip(),
                                     "model": "human-corrected"}) + "\n")
        print(f"folded {len(edited)} human corrections into checkpoint")
        if flagged_only:
            print(f"{len(flagged_only)} flagged (no edit) — re-caption these with pro:")
            for i in flagged_only:
                print(f"  FLAG {i}")
    caps: dict[str, str] = {}
    if CKPT.exists():
        with CKPT.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    if d.get("caption"):
                        caps[d["id"]] = d["caption"]  # last write wins
                except Exception:
                    pass
    if not caps:
        print("no captions in checkpoint; nothing to apply")
        return
    import pyarrow as pa
    db = lancedb.connect(str(cfg.index_dir))
    # Read as an Arrow table so the fixed-size-list `vector` column type is preserved
    # exactly (recreating from python dicts would coerce it to a variable list and break
    # the app's image_search). We only swap the text `gemini_caption` column.
    t = db.open_table("figures").to_arrow()
    ids = t.column("id").to_pylist()
    names = list(t.schema.names)
    prev = t.column("gemini_caption").to_pylist() if "gemini_caption" in names else [""] * len(ids)
    new_caps = [caps.get(i, (p or "")) for i, p in zip(ids, prev)]
    applied = sum(1 for i, p in zip(ids, prev) if caps.get(i) and caps[i] != (p or ""))
    if "gemini_caption" in names:
        t = t.drop(["gemini_caption"])
    t = t.append_column("gemini_caption", pa.array(new_caps, type=pa.string()))
    db.create_table("figures", data=t, mode="overwrite")
    print(f"applied gemini_caption to {applied} rows; table has {t.num_rows} rows; "
          f"non-empty gemini_caption now {sum(1 for c in new_caps if c)}")


def cmd_status(args):
    cfg = load_config()
    done = _load_done()
    db = lancedb.connect(str(cfg.index_dir))
    t = db.open_table("figures").to_arrow()
    cols = set(f.name for f in t.schema)
    total = t.num_rows
    print(f"figures rows: {total}")
    print(f"checkpoint captions: {len(done)}")
    print(f"gemini_caption column present in table: {'gemini_caption' in cols}")
    if "gemini_caption" in cols:
        gc = [c for c in t.column("gemini_caption").to_pylist() if c]
        print(f"rows with non-empty gemini_caption in table: {len(gc)}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("caption")
    c.add_argument("--books", nargs="*", help="book-name substrings to caption")
    c.add_argument("--all", action="store_true", help="caption all non-diagnostic figures")
    c.add_argument("--workers", type=int, default=24)
    c.add_argument("--locations", default="us-central1,us-east4,us-west1,europe-west4",
                   help="comma-separated Vertex regions to spread (failover) load across")
    c.add_argument("--model", default=None,
                   help="Vertex model id (default: config vertex_model). gemini-2.5-flash has "
                        "far higher quota than -pro and sustains high concurrency.")
    c.set_defaults(func=cmd_caption)
    a = sub.add_parser("apply")
    a.add_argument("--corrections", default=None,
                   help="path to caption_corrections.json exported from caption_review.html")
    a.set_defaults(func=cmd_apply)
    s = sub.add_parser("status")
    s.set_defaults(func=cmd_status)
    args = ap.parse_args()
    if args.cmd == "caption" and not args.books and not args.all:
        ap.error("caption needs --books or --all")
    args.func(args)


if __name__ == "__main__":
    main()
