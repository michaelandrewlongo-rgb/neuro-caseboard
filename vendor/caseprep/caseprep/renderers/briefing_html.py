"""Render the Markdown briefing to a self-contained operative-dossier HTML page.

Terms matching figure-bank keywords become <button class="figref"> elements;
hovering shows a preview card; clicking opens a full lightbox. All images are
embedded as data-URIs so the file is fully self-contained.
"""
from __future__ import annotations

import base64
import datetime
import html as _html
import json
from pathlib import Path
from typing import Callable

import markdown as _markdown

from caseprep.figure_rank import best_figure
from caseprep.figure_tags import build_vocabulary, find_marks
from caseprep.image_bank.figure_store import FigureRecord

EmbedFn = Callable[[list[str]], list[list[float]]]

# ---------------------------------------------------------------------------
# Helpers (preserved from the original; _card_html and _CSS are removed)
# ---------------------------------------------------------------------------

def _line_is_table_row(text: str, pos: int) -> bool:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    line = text[start:(end if end != -1 else len(text))]
    return line.lstrip().startswith("|")


def _mime_for(rec: FigureRecord, raw: bytes) -> str:
    if rec.image_path:
        ext = Path(rec.image_path).suffix.lower()
        return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp"}.get(ext, "image/jpeg")
    if raw[:8].startswith(b"\x89PNG"):
        return "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _data_uri(rec: FigureRecord) -> str | None:
    raw: bytes | None = None
    if rec.image_blob is not None:
        raw = rec.image_blob
    elif rec.image_path and Path(rec.image_path).exists():
        raw = Path(rec.image_path).read_bytes()
    if not raw:
        return None
    return f"data:{_mime_for(rec, raw)};base64," + base64.b64encode(raw).decode("ascii")



def _enclosing_sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    rights = [p for p in (text.find(".", end), text.find("\n", end)) if p != -1] + [len(text)]
    return text[left:min(rights)].strip()


# ---------------------------------------------------------------------------
# CSS — verbatim from the approved reference template
# ---------------------------------------------------------------------------

_CSS = """\
:root{
  --paper:#f6efe1; --paper2:#efe6d3; --ink:#221c14; --ink2:#4a4030; --faint:#8a7d66;
  --rule:#d9cdb4; --rule2:#c8b994;
  --crimson:#b3361d; --crimson-d:#8f2814; --teal:#155b5b; --teal-d:#0e4444;
  --gold:#b07d2a;
  --desk:#171310;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;color:var(--ink);font-family:"Hanken Grotesk",system-ui,sans-serif;
  font-weight:400;line-height:1.6;-webkit-font-smoothing:antialiased;
  background:
    radial-gradient(900px 500px at 50% -5%,#241d16,transparent 70%),
    radial-gradient(600px 400px at 90% 100%,#1d1813,transparent 60%),
    var(--desk);
  padding:34px 22px 70px;}
/* the dossier sheet on the desk */
.sheet{position:relative;max-width:1140px;margin:0 auto;background:var(--paper);
  border-radius:4px;padding:0 0 6px;
  box-shadow:0 1px 0 1px rgba(0,0,0,.25),0 40px 90px -30px rgba(0,0,0,.8),0 2px 8px rgba(0,0,0,.4);
  background-image:radial-gradient(rgba(140,125,102,.05) 1px,transparent 1px);background-size:4px 4px;}
.sheet::before{content:"";position:absolute;inset:0;border-radius:4px;pointer-events:none;
  box-shadow:inset 0 0 0 1px rgba(120,100,70,.18),inset 0 0 60px rgba(150,130,95,.10)}
.pad{padding:0 clamp(28px,5vw,64px)}

/* ---- letterhead ---- */
.letterhead{display:flex;justify-content:space-between;align-items:center;gap:20px;
  padding:26px clamp(28px,5vw,64px) 18px;border-bottom:2px solid var(--ink)}
.mark{display:flex;align-items:center;gap:13px}
.seal{width:42px;height:42px;border-radius:50%;flex-shrink:0;display:grid;place-items:center;
  background:radial-gradient(circle at 35% 30%,#c8442a,var(--crimson-d));color:#f6efe1;
  font-size:19px;box-shadow:0 3px 10px -2px rgba(143,40,20,.6),inset 0 0 0 1px rgba(255,255,255,.2);
  font-family:"Fraunces";font-weight:600;transform:rotate(-6deg)}
.mark .n{font-family:"Fraunces",serif;font-weight:600;font-size:20px;letter-spacing:-.01em;line-height:1}
.mark .s{font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.24em;
  text-transform:uppercase;color:var(--crimson);margin-top:3px}
.stamp{text-align:right;font-family:"IBM Plex Mono",monospace;font-size:10.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--faint);line-height:1.7}
.stamp b{color:var(--ink)}

/* ---- assistant margin note ---- */
.note{margin:24px clamp(28px,5vw,64px) 0;padding:14px 20px;background:var(--paper2);
  border-left:3px solid var(--crimson);border-radius:0 8px 8px 0;position:relative}
.note p{margin:0;font-family:"Fraunces",serif;font-style:italic;font-size:16.5px;color:var(--ink2);line-height:1.5}
.note p b{font-style:normal;font-weight:600;color:var(--ink)}
.note .by{font-family:"IBM Plex Mono",monospace;font-size:9.5px;letter-spacing:.18em;
  text-transform:uppercase;color:var(--faint);margin-top:8px;display:block}

/* ---- hero ---- */
.hero{padding:30px clamp(28px,5vw,64px) 26px}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--teal);font-weight:600;margin-bottom:14px}
h1.case{font-family:"Fraunces",serif;font-weight:600;font-size:clamp(30px,4.8vw,54px);
  line-height:1.02;letter-spacing:-.018em;margin:0;color:var(--ink)}
h1.case em{font-style:italic;color:var(--crimson);font-weight:500}
.thesis{margin:16px 0 0;color:var(--ink2);max-width:740px;font-size:16px}
.tiles{display:flex;gap:0;flex-wrap:wrap;margin-top:28px;border:1px solid var(--rule2);border-radius:10px;overflow:hidden}
.tile{flex:1;min-width:150px;padding:14px 18px;border-right:1px solid var(--rule)}
.tile:last-child{border-right:0}
.tile .k{font-family:"IBM Plex Mono",monospace;font-size:9.5px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--faint)}
.tile .v{font-family:"Fraunces";font-weight:600;font-size:20px;color:var(--ink);margin-top:4px}
.tile .v small{color:var(--crimson);font-weight:500}

/* ---- body grid ---- */
.body-grid{display:grid;grid-template-columns:186px minmax(0,1fr);gap:46px;
  padding:30px clamp(28px,5vw,64px) 0;border-top:2px solid var(--ink);margin-top:6px}
nav.rail{position:sticky;top:24px;align-self:start;height:max-content}
nav.rail .t{font-family:"IBM Plex Mono",monospace;font-size:9.5px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--faint);margin-bottom:13px;padding-bottom:9px;border-bottom:1px solid var(--rule)}
nav.rail a{display:flex;align-items:center;gap:10px;padding:6px 0;color:var(--ink2);
  text-decoration:none;font-size:13px;font-weight:500;transition:color .2s}
nav.rail a .ix{font-family:"IBM Plex Mono",monospace;font-size:10px;color:var(--faint);width:16px}
nav.rail a:hover{color:var(--crimson)}
nav.rail a.active{color:var(--crimson);font-weight:600}
nav.rail a.active .ix{color:var(--crimson)}
.rail .legend{margin-top:22px;padding-top:15px;border-top:1px solid var(--rule);
  font-size:11.5px;color:var(--faint);line-height:1.55}
.rail .legend .chip{color:var(--crimson);font-weight:600}

main{padding-bottom:80px;min-width:0;counter-reset:sec}
.doc h1{counter-increment:sec;font-family:"Fraunces",serif;font-weight:600;font-size:25px;
  letter-spacing:-.012em;color:var(--ink);margin:46px 0 14px;scroll-margin-top:22px;
  display:flex;align-items:baseline;gap:14px;padding-bottom:10px;border-bottom:1px solid var(--rule)}
.doc h1::before{content:counter(sec,decimal-leading-zero);font-family:"IBM Plex Mono",monospace;
  font-size:14px;font-weight:600;color:var(--crimson);letter-spacing:.04em}
.doc h2{font-family:"IBM Plex Mono",monospace;font-weight:600;font-size:11px;text-transform:uppercase;
  letter-spacing:.15em;color:var(--teal);margin:28px 0 8px}
.doc h3{font-family:"Fraunces";font-weight:600;font-size:18px;color:var(--ink);margin:22px 0 7px}
.doc p,.doc li{color:var(--ink2);font-size:15.5px}
.doc li{margin:5px 0}.doc ul{padding-left:20px}.doc ul li::marker{color:var(--crimson)}
.doc strong{color:var(--ink);font-weight:700}
.doc a{color:var(--crimson)}
.doc table{border-collapse:collapse;width:100%;margin:16px 0;font-size:13px;
  border:1px solid var(--rule2);border-radius:8px;overflow:hidden;background:#fbf6ec}
.doc th{background:var(--ink);color:var(--paper);text-align:left;font-family:"IBM Plex Mono",monospace;
  font-weight:500;font-size:10px;letter-spacing:.07em;text-transform:uppercase;padding:11px 13px}
.doc td{border-top:1px solid var(--rule);padding:10px 13px;color:var(--ink2);vertical-align:top}
.doc tr:hover td{background:rgba(179,54,29,.04)}

footer{margin:36px clamp(28px,5vw,64px) 0;padding:18px 0 14px;border-top:1px solid var(--rule);
  font-family:"IBM Plex Mono",monospace;font-size:10.5px;letter-spacing:.1em;color:var(--faint);
  display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;text-transform:uppercase}
footer .c{color:var(--crimson);font-weight:600}

.reveal>*{opacity:0;transform:translateY(9px);animation:in .55s cubic-bezier(.2,.7,.2,1) forwards}
@keyframes in{to{opacity:1;transform:none}}

@media(max-width:880px){.body-grid{grid-template-columns:1fr;gap:0}nav.rail{display:none}
  .letterhead{flex-direction:column;align-items:flex-start;gap:12px}.stamp{text-align:left}}
"""

# CSS only included when figures are present (contains the string "figref")
_CSS_FIGS = """\
/* ---- figure reference ---- */
.figref{font:inherit;color:var(--crimson);background:none;border:0;cursor:pointer;position:relative;
  font-weight:600;padding:0;border-bottom:1.5px solid rgba(179,54,29,.35);transition:color .18s,border-color .18s,background .18s}
.figref:hover{color:var(--crimson-d);border-color:var(--crimson);background:rgba(179,54,29,.07)}
.figref .dot{font-size:.6em;vertical-align:.5em;margin-left:2px}

/* ---- hover preview (a little photo card) ---- */
#hover{position:fixed;z-index:60;width:326px;max-width:74vw;pointer-events:none;
  background:var(--paper);border:1px solid var(--rule2);border-radius:10px;overflow:hidden;
  box-shadow:0 24px 60px -18px rgba(0,0,0,.7);opacity:0;transform:translateY(7px) scale(.98) rotate(-.6deg);
  transition:opacity .16s,transform .16s;padding:7px 7px 0}
#hover.show{opacity:1;transform:rotate(-.6deg)}
#hover .frame{position:relative;border-radius:6px;overflow:hidden}
#hover img{display:block;width:100%;max-height:222px;object-fit:cover;background:#1a1510}
#hover .tag{position:absolute;top:8px;left:8px;font-family:"IBM Plex Mono",monospace;font-size:9px;
  letter-spacing:.12em;text-transform:uppercase;color:var(--paper);background:var(--crimson);
  padding:3px 7px;border-radius:5px}
#hover .cap{padding:9px 6px 4px;font-size:11.5px;color:var(--ink2);line-height:1.45}
#hover .src{display:block;margin-top:5px;color:var(--crimson);font-family:"IBM Plex Mono",monospace;font-size:10px}
#hover .hint{padding:5px 6px 9px;font-size:9px;color:var(--faint);letter-spacing:.06em;
  font-family:"IBM Plex Mono",monospace;border-top:1px solid var(--rule);margin-top:4px}

/* ---- lightbox ---- */
#lb{position:fixed;inset:0;z-index:90;display:none;place-items:center;padding:44px;
  background:rgba(15,11,8,.86);backdrop-filter:blur(6px)}
#lb.open{display:grid;animation:fade .22s ease}
@keyframes fade{from{opacity:0}to{opacity:1}}
#lb .card{max-width:1000px;width:100%;max-height:90vh;background:var(--paper);
  border-radius:12px;overflow:hidden;display:flex;flex-direction:column;
  box-shadow:0 50px 120px -30px #000;animation:rise .3s cubic-bezier(.2,.8,.2,1)}
@keyframes rise{from{opacity:0;transform:translateY(20px) scale(.97)}to{opacity:1;transform:none}}
#lb img{width:100%;max-height:72vh;object-fit:contain;background:#120d09}
#lb .foot{padding:17px 24px;border-top:2px solid var(--ink);display:flex;
  justify-content:space-between;align-items:flex-start;gap:22px}
#lb .foot .cap{font-size:14px;color:var(--ink);line-height:1.5;font-family:"Fraunces";font-weight:500}
#lb .foot .src a{color:var(--crimson);text-decoration:none;font-family:"IBM Plex Mono",monospace;font-size:11.5px;font-weight:600}
#lb .x{position:absolute;top:24px;right:28px;color:var(--paper);background:rgba(34,28,20,.7);
  border:1px solid rgba(255,255,255,.2);width:42px;height:42px;border-radius:50%;cursor:pointer;font-size:16px;z-index:2}
#lb .x:hover{background:var(--crimson)}
#lb .counter{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--paper);
  position:absolute;top:32px;left:32px;letter-spacing:.12em;z-index:2}
#lb .nav{position:absolute;top:50%;transform:translateY(-50%);width:46px;height:46px;border-radius:50%;
  background:rgba(34,28,20,.7);border:1px solid rgba(255,255,255,.2);color:var(--paper);cursor:pointer;font-size:18px;z-index:2}
#lb .nav:hover{background:var(--crimson)}#lb .prev{left:30px}#lb .next{right:30px}
@media(max-width:880px){#lb .nav{display:none}}
"""


# ---------------------------------------------------------------------------
# JS — adapted from the reference; rail is auto-generated from h1 headings
# ---------------------------------------------------------------------------

# Base JS — always included (rail builder + scrollspy + reveal; no "figref" in this block)
_JS_BASE = """\
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

// Assign sec-N ids to each h1 and build the rail
(function(){
  let n=0;
  const railItems = document.getElementById('railItems');
  document.querySelectorAll('#doc h1').forEach(h=>{
    n++;
    h.id='sec-'+n;
    if(railItems){
      const nn=String(n).padStart(2,'0');
      let label=h.textContent.trim();
      if(label.indexOf(' - ')!==-1)label=label.split(' - ')[0].trim();
      const a=document.createElement('a');
      a.href='#sec-'+n;
      a.innerHTML='<span class="ix">'+nn+'</span>'+esc(label);
      railItems.appendChild(a);
    }
  });
})();

document.querySelectorAll('.reveal>*').forEach((el,i)=>el.style.animationDelay=Math.min(i*26,520)+'ms');
const links=[...document.querySelectorAll('#rail a')];
const secs=links.map(a=>document.querySelector(a.getAttribute('href'))).filter(Boolean);
const spy=new IntersectionObserver(es=>es.forEach(en=>{
  if(en.isIntersecting){const id='#'+en.target.id;
    links.forEach(a=>a.classList.toggle('active',a.getAttribute('href')===id));}}),
  {rootMargin:'-12% 0px -76% 0px'});
secs.forEach(s=>spy.observe(s));
"""

# JS only included when figures are present (contains "figref")
_JS_FIGS_TEMPLATE = """\
const FIGS = {figs_json};
const refs = [...document.querySelectorAll('.figref')];

const hov=document.getElementById('hover'),hImg=hov.querySelector('img'),hCap=hov.querySelector('.cap');
let hideT;
function place(e){{const pad=16,w=hov.offsetWidth,h=hov.offsetHeight;
  let x=e.clientX+pad,y=e.clientY+pad;
  if(x+w>innerWidth-10)x=e.clientX-w-pad; if(y+h>innerHeight-10)y=e.clientY-h-pad;
  hov.style.left=Math.max(8,x)+'px';hov.style.top=Math.max(8,y)+'px';}}
refs.forEach(r=>{{const f=FIGS[r.dataset.fig];if(!f)return;
  r.addEventListener('mouseenter',e=>{{clearTimeout(hideT);hImg.src=f.img;
    hCap.innerHTML=esc(f.cap)+(f.src?`<span class="src">&#9635; ${{esc(f.src)}}</span>`:'');
    hov.classList.add('show');place(e);}});
  r.addEventListener('mousemove',place);
  r.addEventListener('mouseleave',()=>{{hideT=setTimeout(()=>hov.classList.remove('show'),60);}});
  r.addEventListener('click',()=>openLB(r.dataset.fig));}});

const lb=document.getElementById('lb'),lbImg=lb.querySelector('.card img'),
  lbCap=lb.querySelector('.cap'),lbSrc=lb.querySelector('.src'),lbCount=lb.querySelector('.counter');
const order=[...new Set(refs.map(r=>r.dataset.fig).filter(k=>FIGS[k]))];
let cur=0;
function openLB(k){{cur=order.indexOf(k);render();lb.classList.add('open');hov.classList.remove('show');}}
function render(){{const f=FIGS[order[cur]];lbImg.src=f.img;lbCap.textContent=f.cap;
  lbSrc.innerHTML=f.url?`<a href="${{f.url}}" target="_blank">&#9635; ${{esc(f.src)}} &#8599;</a>`:(f.src?'&#9635; '+esc(f.src):'');
  lbCount.textContent=`${{String(cur+1).padStart(2,'0')}} / ${{String(order.length).padStart(2,'0')}}`;}}
function close(){{lb.classList.remove('open');}}
function step(d){{cur=(cur+d+order.length)%order.length;render();}}
lb.querySelector('.x').onclick=close;lb.querySelector('.prev').onclick=()=>step(-1);lb.querySelector('.next').onclick=()=>step(1);
lb.onclick=e=>{{if(e.target===lb)close();}};
addEventListener('keydown',e=>{{if(!lb.classList.contains('open'))return;
  if(e.key==='Escape')close();if(e.key==='ArrowRight')step(1);if(e.key==='ArrowLeft')step(-1);}});
"""


# ---------------------------------------------------------------------------
# Hero builder
# ---------------------------------------------------------------------------

def _truncate(val: str) -> str:
    """Keep only text up to the first '.', ' after ', or ' then '."""
    for sep in (".", " after ", " then "):
        idx = val.find(sep)
        if idx != -1:
            return val[:idx].strip()
    return val.strip()


def _build_hero(schema: dict | None, nfig: int) -> tuple[str, str, list[tuple[str, str]]]:
    """Return (title, thesis, tiles) derived from schema. Falls back gracefully."""
    title = "Operative Briefing"
    thesis = ""
    tiles: list[tuple[str, str]] = []
    if schema is None:
        return title, thesis, tiles
    try:
        title = schema.get("topic", "Operative Briefing") or "Operative Briefing"
        snap = schema["case"]["case_snapshot"]
        thesis = snap.get("one_line_thesis", "") or ""
        label_keys = [
            ("Diagnosis", "diagnosis"),
            ("Procedure", "planned_procedure"),
            ("Laterality", "laterality"),
            ("Disposition", "anticipated_disposition"),
        ]
        for label, key in label_keys:
            val = snap.get(key, "") or ""
            if val:
                tiles.append((label, _truncate(str(val))))
    except Exception:
        pass
    return title, thesis, tiles


# ---------------------------------------------------------------------------
# HTML assembly helpers
# ---------------------------------------------------------------------------

def _tiles_html(tiles: list[tuple[str, str]]) -> str:
    if not tiles:
        return ""
    parts = []
    for label, val in tiles:
        parts.append(
            f'<div class="tile">'
            f'<div class="k">{_html.escape(label)}</div>'
            f'<div class="v">{_html.escape(val)}</div>'
            f'</div>'
        )
    return '<div class="tiles">' + "".join(parts) + "</div>"


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_briefing_html(
    markdown_text: str,
    store_records: list[FigureRecord],
    *,
    schema: dict | None = None,
    embed_fn: EmbedFn | None,
    floor: float = 0.35,
) -> str:
    """Return a fully self-contained operative-dossier HTML string."""

    # ------------------------------------------------------------------
    # 1. Mark terms → figref buttons; build FIGS dict
    # ------------------------------------------------------------------
    body_md = markdown_text
    figs: dict[str, dict] = {}

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

            uri = _data_uri(chosen)
            if uri is None:
                continue

            key = f"{chosen.source}:{chosen.fig_id}"
            term = markdown_text[mk.start:mk.end]
            button = (
                f'<button class="figref" data-fig="{_html.escape(key)}">'
                f'{_html.escape(term)}'
                f'<span class="dot">&#9677;</span>'
                f'</button>'
            )
            replacements.append((mk.start, mk.end, button))

            # Build FIGS entry (first encounter wins)
            if key not in figs:
                ref = chosen.source_ref
                pmcid = ref.get("pmcid", "")
                src = pmcid if pmcid else ref.get("heading_path", "")
                url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else ""
                figs[key] = {
                    "img": uri,
                    "cap": chosen.caption,
                    "src": str(src),
                    "url": url,
                }

        # Apply replacements right-to-left
        for start, end, html_frag in sorted(replacements, key=lambda r: r[0], reverse=True):
            body_md = body_md[:start] + html_frag + body_md[end:]

    # ------------------------------------------------------------------
    # 2. Render body markdown → HTML
    # ------------------------------------------------------------------
    body_html = _markdown.markdown(
        body_md,
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
    )

    # ------------------------------------------------------------------
    # 3. Hero from schema
    # ------------------------------------------------------------------
    nfig = len(figs)
    title, thesis, tiles = _build_hero(schema, nfig)

    date_str = datetime.date.today().strftime("%d %b %Y")
    fig_label = f"{nfig} figure{'s' if nfig != 1 else ''} linked"

    # Note message
    if nfig:
        note_text = (
            f"I’ve prepared your briefing for this case — anatomy, evidence, danger "
            f"zones and outcome predictors — and linked <b>{nfig} reference "
            f"figure{'s' if nfig != 1 else ''}</b> from the literature. "
            f"<b>Hover any highlighted term</b> to preview it; click to study it full-size."
        )
    else:
        note_text = (
            "I’ve prepared your briefing for this case — anatomy, evidence, danger "
            "zones and outcome predictors. No figure references were matched for this briefing."
        )

    # ------------------------------------------------------------------
    # 4. Tiles HTML (only when there are tiles)
    # ------------------------------------------------------------------
    tiles_html = _tiles_html(tiles)

    # ------------------------------------------------------------------
    # 5. Assemble full HTML
    # ------------------------------------------------------------------
    # Conditional blocks: only include figref CSS/JS/elements when figs exist
    css_figs_block = f"\n<style>\n{_CSS_FIGS}\n</style>" if nfig else ""
    if nfig:
        figs_json = json.dumps(figs).replace("</", "<\\/")
        js_figs_block = _JS_FIGS_TEMPLATE.format(figs_json=figs_json)
        hover_html = (
            '<div id="hover"><div class="frame"><img alt=""><span class="tag">Reference</span></div>'
            '<div class="cap"></div><div class="hint">click to expand &crarr;</div></div>\n\n'
            '<div id="lb">\n'
            '  <div class="counter"></div>\n'
            '  <button class="x" aria-label="close">&#10005;</button>\n'
            '  <button class="nav prev" aria-label="previous">&#8249;</button>\n'
            '  <button class="nav next" aria-label="next">&#8250;</button>\n'
            '  <div class="card"><img alt=""><div class="foot"><div class="cap"></div>'
            '<div class="src"></div></div></div>\n'
            '</div>'
        )
    else:
        js_figs_block = ""
        hover_html = ""

    thesis_html = f'<p class="thesis">{_html.escape(thesis)}</p>' if thesis else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CasePrep AI — {_html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700;1,9..144,400;1,9..144,500&family=Hanken+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
{_CSS}
</style>{css_figs_block}
</head>
<body>
<div class="sheet">

  <div class="letterhead">
    <div class="mark">
      <div class="seal">&#10022;</div>
      <div><div class="n">CasePrep AI</div><div class="s">Operative Briefing</div></div>
    </div>
    <div class="stamp">Prepared <b>{_html.escape(date_str)}</b><br>{_html.escape(fig_label)} &middot; draft</div>
  </div>

  <div class="note reveal">
    <p>{note_text}</p>
    <span class="by">&mdash; CasePrep AI &middot; for clinician review</span>
  </div>

  <section class="hero reveal">
    <div class="eyebrow">Operative Case Briefing</div>
    <h1 class="case">{_html.escape(title)}</h1>
    {thesis_html}
    {tiles_html}
  </section>

  <div class="body-grid">
    <nav class="rail" id="rail">
      <div class="t">Briefing Index</div>
      <div id="railItems"></div>
      {'<div class="legend">Highlighted terms link to reference figures &mdash; hover to preview, click to expand.</div>' if nfig else ''}
    </nav>
    <main><div class="doc reveal" id="doc">{body_html}</div></main>
  </div>

  <footer>
    <span>CasePrep AI &middot; <span class="c">Draft for clinician review</span></span>
    <span>Figures sourced from peer-reviewed literature</span>
  </footer>
</div>

{hover_html}

<script>
{_JS_BASE}{js_figs_block}
</script>
</body>
</html>"""

    return html
