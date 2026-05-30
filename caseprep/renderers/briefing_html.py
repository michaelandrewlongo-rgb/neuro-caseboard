"""Render the Markdown briefing to a self-contained HTML page with inline figure
hovercards: salient terms get a superscript; hovering reveals the top-1 figure."""
from __future__ import annotations

import base64
import html as _html
from pathlib import Path
from typing import Callable

import markdown as _markdown

from caseprep.figure_rank import best_figure
from caseprep.figure_tags import build_vocabulary, find_marks
from caseprep.image_bank.figure_store import FigureRecord

EmbedFn = Callable[[list[str]], list[list[float]]]

_CSS = """
<style>
.fig-term{position:relative;border-bottom:1px dotted #0a66c2;cursor:help}
.fig-term sup{color:#0a66c2;font-weight:bold}
.fig-term .fig-card{display:none;position:absolute;z-index:50;left:0;top:1.4em;
  width:520px;max-width:80vw;background:#fff;border:1px solid #ccc;border-radius:8px;
  box-shadow:0 6px 24px rgba(0,0,0,.25);padding:.6rem}
.fig-term:hover .fig-card{display:block}
.fig-card img{width:100%;height:auto;border-radius:4px}
.fig-card .cap{font-size:.85rem;color:#333;margin-top:.4rem}
@media (prefers-color-scheme: dark){.fig-card{background:#1e1e1e;border-color:#444}
  .fig-card .cap{color:#ccc}}
</style>
"""


def _line_is_table_row(text: str, pos: int) -> bool:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    line = text[start:(end if end != -1 else len(text))]
    return line.lstrip().startswith("|")


def _data_uri(rec: FigureRecord) -> str | None:
    raw: bytes | None = None
    if rec.image_blob is not None:
        raw = rec.image_blob
    elif rec.image_path and Path(rec.image_path).exists():
        raw = Path(rec.image_path).read_bytes()
    if not raw:
        return None
    return "data:image/*;base64," + base64.b64encode(raw).decode("ascii")


def _source_html(rec: FigureRecord) -> str:
    ref = rec.source_ref
    pmcid = ref.get("pmcid")
    if pmcid:
        url = f"https://pmc.ncbi.nlm.nih.gov/articles/{_html.escape(pmcid)}/"
        return f'source: <a href="{url}">{_html.escape(pmcid)}</a>'
    if ref.get("heading_path"):
        return f"source: {_html.escape(str(ref['heading_path']))}"
    return ""


def _enclosing_sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    rights = [p for p in (text.find(".", end), text.find("\n", end)) if p != -1] + [len(text)]
    return text[left:min(rights)].strip()


def _card_html(term: str, rec: FigureRecord) -> str | None:
    uri = _data_uri(rec)
    if uri is None:
        return None
    cap = _html.escape(rec.caption)
    src = _source_html(rec)
    return (f'<span class="fig-term">{_html.escape(term)}<sup>&#9638;</sup>'
            f'<span class="fig-card"><img src="{uri}" alt="{cap}">'
            f'<span class="cap">{cap}{(" — " + src) if src else ""}</span>'
            f"</span></span>")


def render_briefing_html(markdown_text: str, store_records: list[FigureRecord], *,
                         embed_fn: EmbedFn | None, floor: float = 0.35) -> str:
    body_md = markdown_text
    has_cards = False
    if store_records:
        vocab = build_vocabulary(store_records)
        by_key = {f"{r.source}:{r.fig_id}": r for r in store_records}
        marks = find_marks(markdown_text, vocab)
        replacements: list[tuple[int, int, str]] = []
        for mk in marks:
            if _line_is_table_row(markdown_text, mk.start):
                continue
            cands = [by_key[k] for k in mk.candidate_keys if k in by_key]
            ctx = _enclosing_sentence(markdown_text, mk.start, mk.end)
            chosen = best_figure(ctx, cands, embed_fn=embed_fn, floor=floor)
            if chosen is None:
                continue
            card = _card_html(markdown_text[mk.start:mk.end], chosen)
            if card is None:
                continue
            replacements.append((mk.start, mk.end, card))
        if replacements:
            has_cards = True
            for start, end, card in sorted(replacements, key=lambda r: r[0], reverse=True):
                body_md = body_md[:start] + card + body_md[end:]
    body_html = _markdown.markdown(body_md, extensions=["tables", "fenced_code", "sane_lists"])
    css = _CSS if has_cards else ""
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'>{css}</head><body>{body_html}</body></html>"
