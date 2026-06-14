"""Build a self-contained HTML review page pairing each Gemini figure caption with its
image, so a human can sign off or correct them.

Reads the Gemini captions from the live checkpoint (``index/_gemini_captions.jsonl`` — so it
reflects everything captioned so far, pro + flash), and the source caption / book / page /
image path from the ``figures`` LanceDB table. Images are referenced by repo-relative URL,
so serve the repo root over HTTP to view:

    python -m scripts.caption_review_html            # writes caption_review.html
    python -m http.server 8000                       # then open http://localhost:8000/caption_review.html

Each figure is one card: image, source caption (gray), an editable Gemini-caption box, and
an "incorrect" checkbox. "Export corrections" downloads a JSON of only the edited/flagged
rows ([{id, caption, flag}]) which ``recaption_figures.py apply --corrections FILE`` can
merge back into the table.
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
from urllib.parse import quote

import lancedb

from neuro_core.config import load_config

REPO = Path(__file__).resolve().parent.parent
CKPT = REPO / "index" / "_gemini_captions.jsonl"
OUT = REPO / "caption_review.html"


def _load_ckpt():
    caps: dict[str, dict] = {}
    if CKPT.exists():
        with CKPT.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("caption"):
                    caps[d["id"]] = {"caption": d["caption"], "model": d.get("model", "gemini-2.5-pro")}
    return caps


def main() -> int:
    cfg = load_config()
    caps = _load_ckpt()
    t = lancedb.connect(str(cfg.index_dir)).open_table("figures").to_arrow()
    col = {c: t.column(c).to_pylist() for c in ("id", "book", "page", "figure_path", "caption")}

    # group captioned rows by book
    by_book: dict[str, list] = {}
    n = 0
    for _id, book, page, fp, src in zip(col["id"], col["book"], col["page"],
                                        col["figure_path"], col["caption"]):
        if _id not in caps or not (fp and os.path.isfile(fp)):
            continue
        try:
            rel = os.path.relpath(fp, REPO)
        except ValueError:
            continue
        url = quote(rel)
        by_book.setdefault(book, []).append(
            {"id": _id, "page": page, "url": url, "src": src or "",
             "gem": caps[_id]["caption"], "model": caps[_id]["model"]})
        n += 1
    for b in by_book:
        by_book[b].sort(key=lambda r: r["page"])

    css = """
    body{font-family:system-ui,Arial,sans-serif;margin:0;background:#f4f5f7;color:#1a1a1a}
    header{position:sticky;top:0;background:#fff;border-bottom:1px solid #ddd;padding:10px 16px;z-index:10;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
    header h1{font-size:16px;margin:0}
    header .stat{color:#555;font-size:13px}
    button{background:#1463ff;color:#fff;border:0;border-radius:6px;padding:8px 14px;font-size:13px;cursor:pointer}
    details{margin:10px;background:#fff;border:1px solid #e3e3e3;border-radius:8px}
    summary{cursor:pointer;padding:10px 14px;font-weight:600;font-size:14px}
    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(440px,1fr));gap:14px;padding:12px}
    .card{border:1px solid #e6e6e6;border-radius:8px;padding:10px;background:#fafafa;display:flex;flex-direction:column;gap:6px}
    .card.flagged{outline:2px solid #e23;background:#fff5f5}
    .card img{width:100%;max-height:520px;object-fit:contain;background:#fff;border:1px solid #eee;border-radius:4px}
    .meta{font-size:12px;color:#444;display:flex;justify-content:space-between;align-items:center}
    .badge{font-size:11px;padding:1px 6px;border-radius:10px;background:#eee;color:#333}
    .badge.flash{background:#fde9c8}.badge.pro{background:#d7ecff}
    .src{font-size:11px;color:#888;white-space:pre-wrap}
    textarea{width:100%;min-height:84px;font-size:13px;font-family:inherit;border:1px solid #cfcfcf;border-radius:4px;padding:6px;box-sizing:border-box;resize:vertical}
    textarea.edited{border-color:#1463ff;background:#f3f8ff}
    label.flag{font-size:12px;color:#a00;user-select:none;cursor:pointer}
    """

    js = """
    function mark(t){const c=t.closest('.card');t.classList.toggle('edited',t.value!==t.dataset.orig);}
    function flag(cb){cb.closest('.card').classList.toggle('flagged',cb.checked);}
    function exportCorrections(){
      const out=[];
      document.querySelectorAll('.card').forEach(c=>{
        const t=c.querySelector('textarea'), cb=c.querySelector('input[type=checkbox]');
        const edited=t.value!==t.dataset.orig, flagged=cb.checked;
        if(edited||flagged) out.push({id:c.dataset.id, caption:t.value.trim(), flag:flagged, edited:edited});
      });
      if(!out.length){alert('No edits or flags to export.');return;}
      const blob=new Blob([JSON.stringify(out,null,2)],{type:'application/json'});
      const a=document.createElement('a');a.href=URL.createObjectURL(blob);
      a.download='caption_corrections.json';a.click();
      document.getElementById('expstat').textContent=out.length+' correction(s) exported';
    }
    """

    parts = [f"<!doctype html><html><head><meta charset='utf-8'><title>Caption review</title>",
             f"<style>{css}</style></head><body>",
             "<header><h1>Gemini caption review</h1>",
             f"<span class='stat'>{n} captioned figures · {len(by_book)} books</span>",
             "<button onclick='exportCorrections()'>Export corrections</button>",
             "<span id='expstat' class='stat'></span>",
             "<span class='stat'>edit a box or tick “incorrect”, then Export</span>",
             "</header>"]

    # Rhoton (pro, eval-critical) first, then the rest alphabetically
    order = sorted(by_book, key=lambda b: (0 if "Rhoton" in b else 1, b))
    for book in order:
        rows = by_book[book]
        opened = "open" if "Rhoton" in book else ""
        parts.append(f"<details {opened}><summary>{html.escape(book)} — {len(rows)} figures</summary><div class='grid'>")
        for r in rows:
            mb = "flash" if "flash" in r["model"] else "pro"
            parts.append(
                f"<div class='card' data-id=\"{html.escape(r['id'])}\">"
                f"<img loading='lazy' src='{r['url']}' alt='p{r['page']}'>"
                f"<div class='meta'><span>p.{r['page']}</span>"
                f"<span class='badge {mb}'>{html.escape(r['model'])}</span></div>"
                f"<div class='src'>source: {html.escape(r['src'][:240]) or '(none)'}</div>"
                f"<textarea oninput='mark(this)' data-orig=\"{html.escape(r['gem'])}\">{html.escape(r['gem'])}</textarea>"
                f"<label class='flag'><input type='checkbox' onchange='flag(this)'> mark incorrect</label>"
                f"</div>")
        parts.append("</div></details>")

    parts.append(f"<script>{js}</script></body></html>")
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"wrote {OUT} ({n} figures across {len(by_book)} books)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
