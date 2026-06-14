"""Build the board-review `cards` LanceDB table from the parsed SANS/ABNS Anki deck.

Mirrors neuro_core/scripts/build_index.py: a zero-argument script driven entirely by
neuro_core.config (env -> .env -> DEFAULTS), using the SAME Embedder / EMBED_MODEL /
EMBED_DEVICE as the textbook build so the card vectors are drop-in compatible with
`chunks`/`figures`.

Source layout (the abns-board-review-lancedb you already parsed from the deck):
  * CARDS_SOURCE_TABLE (default "cards")  — one row per card: front_text/back_text,
    front_html/back_html, front_images/back_images (filename lists), tags, deck_name,
    deck_full, model_name.
  * CARDS_MEDIA_TABLE  (default "images") — filename -> image_bytes blob store; media is
    read straight from here, so no external collection.media folder is required.

Run:    python -m neuro_core.scripts.build_cards_index
Config (neuro_core.config, all env-overridable like the textbook build):
  CARDS_SOURCE_DB, CARDS_SOURCE_TABLE, CARDS_MEDIA_TABLE, CARDS_MEDIA_DIR,
  INDEX_DIR, EMBED_MODEL, EMBED_DEVICE, ASSETS_DIR

Writes `cards.lance` into INDEX_DIR alongside `chunks`/`figures`, and copies resolved
card images to <ASSETS_DIR>/../cards/ (a sibling of the figures assets).
"""

import hashlib
import os
import re
import shutil
import time
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import lancedb

from neuro_core.config import load_config, resolve_device
from neuro_core.embed import Embedder
from neuro_core.cards_index import build_cards_index


# ---- HTML -> text + image extraction -------------------------------------

class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.imgs = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "div", "li"):
            self.parts.append("\n")
        if tag == "img":
            for k, v in attrs:
                if k == "src" and v:
                    self.imgs.append(v)
                elif k == "alt" and v:
                    # strip_html only runs on a text-empty side, so folding alt
                    # text in here rescues cards whose content lives in the image.
                    self.parts.append(f" {v} ")


def strip_html(html):
    if not html:
        return "", []
    p = _Stripper()
    try:
        p.feed(html)
    except Exception:
        # Malformed HTML: fall back to a blunt tag strip.
        text = re.sub(r"<[^>]+>", " ", html)
        imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html)
        return unescape(re.sub(r"\s+\n", "\n", text)).strip(), imgs
    text = unescape("".join(p.parts))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text, p.imgs


# ---- source-table scan (version-tolerant) --------------------------------

def scan_table(tbl):
    for attr in ("to_arrow", "to_pandas"):
        fn = getattr(tbl, attr, None)
        if fn is None:
            continue
        try:
            obj = fn()
        except Exception:
            continue
        if attr == "to_arrow":
            return obj.to_pylist()
        return obj.to_dict("records")
    # Last resort: a wide unfiltered search.
    return tbl.search().limit(1_000_000).to_list()


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if x]
    s = str(v).strip()
    return [s] if s and s != "[]" else []


def _stable_id(row, q, a, imgs=()):
    for key in ("id", "guid", "note_id", "nid"):
        if row.get(key):
            return str(row[key])
    basis = q + "␟" + a
    if not (q or a):
        # Image-only cards share the empty q+a; key them by their images so they
        # stay distinct instead of all collapsing to one id.
        basis += "␟" + "|".join(sorted(imgs))
    h = hashlib.sha1(basis.encode("utf-8", "ignore")).hexdigest()
    return f"card-{h[:16]}"


# ---- media resolution -----------------------------------------------------

def load_media_map(db, media_table):
    """filename -> image bytes, read from the deck's blob table. {} if unavailable."""
    if not media_table:
        return {}
    try:
        rows = scan_table(db.open_table(media_table))
    except Exception:
        return {}
    out = {}
    for r in rows:
        name = os.path.basename((r.get("filename") or "").strip())
        data = r.get("image_bytes")
        if name and data:
            out[name] = data
    return out


def resolve_images(filenames, media_map, media_dir, out_dir, cache):
    """Write each referenced media file into out_dir; return absolute paths that exist.

    Prefers bytes from the deck's media table; falls back to an on-disk media folder
    (CARDS_MEDIA_DIR). `cache` (base -> abspath or "") dedupes writes across cards.
    """
    paths = []
    media_dir = Path(media_dir) if media_dir else None
    for name in filenames:
        base = os.path.basename(unescape(str(name)))
        if not base:
            continue
        if base in cache:
            if cache[base]:
                paths.append(cache[base])
            continue
        dest = out_dir / base
        ok = False
        data = media_map.get(base)
        if data is not None:
            try:
                dest.write_bytes(bytes(data))
                ok = True
            except OSError:
                ok = False
        elif media_dir is not None:
            src = media_dir / base
            if src.exists():
                try:
                    shutil.copy2(src, dest)
                    ok = True
                except OSError:
                    ok = False
        cache[base] = str(dest.resolve()) if ok else ""
        if ok:
            paths.append(cache[base])
    return paths


def main():
    cfg = load_config()

    source_db = str(cfg.cards_source_db)
    source_table = cfg.cards_source_table
    out_media = Path(cfg.assets_dir).parent / "cards"
    out_media.mkdir(parents=True, exist_ok=True)

    print(f"Reading deck: table '{source_table}' in {source_db}", flush=True)
    db = lancedb.connect(source_db)
    rows = scan_table(db.open_table(source_table))
    print(f"  {len(rows)} source rows", flush=True)

    media_map = load_media_map(db, cfg.cards_media_table)
    if media_map:
        print(f"  media: {len(media_map)} images in table "
              f"'{cfg.cards_media_table}' -> {out_media}", flush=True)
    elif cfg.cards_media_dir:
        print(f"  media: resolving from folder {cfg.cards_media_dir} -> {out_media}",
              flush=True)
    else:
        print("  media: none available — building text-only (no image paths)",
              flush=True)

    cards = []
    img_cache = {}
    skipped = 0
    for row in rows:
        q = (row.get("front_text") or "").strip()
        q_imgs = _as_list(row.get("front_images"))
        if not q:
            q, extra = strip_html(row.get("front_html") or "")
            q_imgs += extra
        a = (row.get("back_text") or "").strip()
        a_imgs = _as_list(row.get("back_images"))
        if not a:
            a, extra = strip_html(row.get("back_html") or "")
            a_imgs += extra

        # Resolve media BEFORE the empty-text skip so image-only cards (and their
        # unique images) aren't silently dropped.
        img_paths = resolve_images(q_imgs + a_imgs, media_map, cfg.cards_media_dir,
                                   out_media, img_cache)
        if not (q or a or img_paths):
            skipped += 1
            continue

        deck_name = (row.get("deck_name") or "").strip()
        deck_full = (row.get("deck_full") or "").strip()
        tags = (row.get("tags") or "").strip()
        text = f"Q: {q}\nA: {a}".strip()
        if not (q or a):
            # Image-only card: give retrieval something textual to match on.
            text = " ".join(t for t in (tags, deck_name) if t) or "image card"
        cards.append({
            "id": _stable_id(row, q, a, img_paths),
            "question_text": q,
            "answer_text": a,
            "deck_name": deck_name,
            "deck_full": deck_full,
            "tags": tags,
            "model_name": (row.get("model_name") or "").strip(),
            "question_html": row.get("front_html") or "",
            "answer_html": row.get("back_html") or "",
            "image_paths": img_paths,
            "text": text,
        })

    # De-dup on id (Anki exports can repeat a note across decks/cards). When two
    # rows collapse to the same id, union their images and tags rather than
    # letting the last one win — otherwise a card's unique image variants are lost.
    merged = {}
    for c in cards:
        prev = merged.get(c["id"])
        if prev is None:
            merged[c["id"]] = c
            continue
        seen = set(prev["image_paths"])
        for p in c["image_paths"]:
            if p not in seen:
                prev["image_paths"].append(p)
                seen.add(p)
        prev["tags"] = " ".join(dict.fromkeys((prev["tags"] + " " + c["tags"]).split()))
    cards = list(merged.values())

    resolved = sum(1 for v in img_cache.values() if v)
    unresolved = [b for b, v in img_cache.items() if not v]
    print(f"  prepared {len(cards)} unique cards ({skipped} empty rows skipped); "
          f"{resolved} distinct images resolved", flush=True)
    if unresolved:
        print(f"  WARNING: {len(unresolved)} referenced image(s) had no bytes and "
              f"were skipped (e.g. {', '.join(unresolved[:5])})", flush=True)

    device = resolve_device(cfg.embed_device)
    print(f"Loading embedding model '{cfg.embed_model}' on '{device}' "
          f"(requested '{cfg.embed_device}') ...", flush=True)
    if device == "cpu":
        print("  NOTE: CPU embedding of a few thousand cards takes a few minutes; "
              "set EMBED_DEVICE=cuda (or 'auto' with a GPU) for the GPU.", flush=True)
    embedder = Embedder(cfg.embed_model, device=device)

    def progress(done, total):
        print(f"    embedded {done}/{total} cards", flush=True)

    t0 = time.time()
    build_cards_index(cards, embedder, cfg.index_dir, on_progress=progress)
    print(f"\n`cards` table written to {cfg.index_dir} "
          f"({time.time() - t0:.0f}s). Media in {out_media}.", flush=True)


if __name__ == "__main__":
    main()
