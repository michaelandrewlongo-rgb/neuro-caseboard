"""Deterministic schematic renderer (LOOP_PROMPT §2): a `FigureSpec` -> a labeled PNG.

Pure Python drawing with PIL (`pillow`, a core dep — no new dependency, no text-to-image). The
output is a deterministic function of the spec (no timestamps, fixed layout/colors), so the same
spec yields byte-identical PNGs and CI can diff renders. Every figure carries a mandatory
"SCHEMATIC — NOT A RADIOGRAPH" banner; it is a labeled diagram, never an image of the patient.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Palette (fixed -> deterministic). Neo Brutalism: black ink/lines, red primary, blue/yellow
# accents — matches the web GUI + PDF theme.
_BG = (255, 255, 255)
_INK = (0, 0, 0)
_MUTED = (51, 51, 51)
_LINE = (0, 0, 0)
_ACCENT = (255, 51, 51)            # red primary (Neo Brutalism)
_TARGET = (0, 102, 255)            # the target/lesion (blue, distinct from the red corridor)
_BANNER_BG = (255, 255, 0)         # yellow caution
_KIND_COLOR = {"target": _TARGET, "corridor": _ACCENT, "vessel": (153, 0, 153),
               "level": _ACCENT, "callout": _MUTED, "structure": _INK}


def _font(size: int, bold: bool = False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    p = _FONT_DIR / name
    try:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    except Exception:
        pass
    return ImageFont.load_default()


def _xy(node, w: int, h: int, pad: int) -> tuple[int, int]:
    return (int(pad + node.x * (w - 2 * pad)), int(pad + node.y * (h - 2 * pad)))


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    """Greedy word-wrap to a pixel width (deterministic). A lone over-long word is kept on its
    own line rather than dropped, so no label is ever silently truncated/clipped."""
    words = (text or "").split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for wd in words[1:]:
        if draw.textlength(cur + " " + wd, font=font) <= max_w:
            cur += " " + wd
        else:
            lines.append(cur)
            cur = wd
    lines.append(cur)
    return lines


def _collides(box, placed) -> bool:
    for p in placed:
        if not (box[2] < p[0] or box[0] > p[2] or box[3] < p[1] or box[1] > p[3]):
            return True
    return False


def _fit(draw, text: str, font, max_w: int) -> str:
    """Single-line ellipsis truncation to a pixel width (for the caption/callout footers)."""
    text = text or ""
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def _arrow(draw, p0, p1, color, dashed: bool = False):
    import math
    x0, y0 = p0
    x1, y1 = p1
    if dashed:
        n = 18
        for i in range(n):
            if i % 2:
                continue
            ax = x0 + (x1 - x0) * i / n
            ay = y0 + (y1 - y0) * i / n
            bx = x0 + (x1 - x0) * (i + 1) / n
            by = y0 + (y1 - y0) * (i + 1) / n
            draw.line([(ax, ay), (bx, by)], fill=color, width=3)
    else:
        draw.line([p0, p1], fill=color, width=3)
    # arrowhead
    ang = math.atan2(y1 - y0, x1 - x0)
    size = 11
    left = (x1 - size * math.cos(ang - 0.5), y1 - size * math.sin(ang - 0.5))
    right = (x1 - size * math.cos(ang + 0.5), y1 - size * math.sin(ang + 0.5))
    draw.polygon([(x1, y1), left, right], fill=color)


def _backdrop(draw, archetype: str, w: int, h: int, pad: int):
    """A light archetype-specific backdrop so the diagram reads as the right kind of schematic."""
    cx, cy = w // 2, h // 2
    if archetype == "corridor":                       # head outline
        draw.ellipse([cx - 230, cy - 150, cx + 230, cy + 170], outline=_LINE, width=2)
    elif archetype == "spine_level":                  # a short vertebral stack
        bx = pad + 40
        for i in range(5):
            top = pad + 60 + i * 70
            draw.rounded_rectangle([bx, top, bx + 120, top + 50], radius=8,
                                   outline=_LINE, width=2)
    elif archetype == "vessel_config":                # a parent vessel baseline + bifurcation
        draw.line([(pad + 40, cy + 120), (cx, cy)], fill=_LINE, width=4)
        draw.line([(cx, cy), (w - pad - 60, cy - 90)], fill=_LINE, width=4)
        draw.line([(cx, cy), (w - pad - 60, cy + 40)], fill=_LINE, width=4)


def render_spec(spec, *, width: int = 900, height: int = 640) -> bytes:
    """Render a FigureSpec to deterministic PNG bytes."""
    pad = 48
    img = Image.new("RGB", (width, height), _BG)
    d = ImageDraw.Draw(img)
    f_title = _font(22, bold=True)
    f_label = _font(15)
    f_small = _font(13)
    f_banner = _font(13, bold=True)

    # frame (thick black brutalist border)
    d.rectangle([6, 6, width - 7, height - 7], outline=_LINE, width=4)

    # mandatory banner: this is a schematic, not a radiograph (top-right)
    banner = "SCHEMATIC — NOT A RADIOGRAPH"
    bw = d.textlength(banner, font=f_banner)
    banner_x = width - pad - bw - 16
    d.rectangle([banner_x, 16, width - pad + 2, 40], fill=_BANNER_BG, outline=_INK, width=2)
    d.text((banner_x + 8, 19), banner, font=f_banner, fill=_INK)

    # title, truncated so it never runs under the banner
    title = spec.title or "Case schematic"
    max_w = banner_x - pad - 16
    if d.textlength(title, font=f_title) > max_w:
        while title and d.textlength(title + "…", font=f_title) > max_w:
            title = title[:-1]
        title = title.rstrip() + "…"
    d.text((pad, 16), title, font=f_title, fill=_INK)

    # side / level chip
    chips = " · ".join(p for p in (spec.side and f"side: {spec.side}",
                                   spec.level and f"level: {spec.level}",
                                   spec.region and f"region: {spec.region}") if p)
    if chips:
        d.text((pad, 48), chips, font=f_small, fill=_MUTED)

    _backdrop(d, spec.archetype, width, height, pad)

    # edges first (so node markers sit on top)
    pos = {n.id: _xy(n, width, height, pad + 30) for n in spec.nodes}
    for e in spec.edges:
        if e.src in pos and e.dst in pos:
            color = _ACCENT if e.kind in ("trajectory", "approach") else _LINE
            _arrow(d, pos[e.src], pos[e.dst], color, dashed=(e.kind == "trajectory"))

    # nodes + labels — edge-aware placement with collision avoidance + a white halo so labels never
    # overlap one another, the node markers, or run off the canvas (image-judge legibility defects:
    # overlapping/clipped labels). Deterministic: spec order + a fixed nudge sequence.
    n_call = len(spec.callouts)
    callouts_y = height - pad - 18 * (n_call + 1) if n_call else height - 36
    bottom_top = callouts_y - 6
    lh, max_label_w, top_lo = 18, 190, pad + 58
    placed = [(0, 0, width, 74), (0, bottom_top, width, height)]   # reserve title + footer strips
    for n in spec.nodes:
        x, y = pos[n.id]
        color = _KIND_COLOR.get(n.kind, _INK)
        r = 9
        d.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=_INK, width=2)
        lines = _wrap(d, n.label, f_label, max_label_w)
        bw = int(max(d.textlength(ln, font=f_label) for ln in lines))
        bh = lh * len(lines)
        lx = x + 16 if x + 16 + bw <= width - pad else max(pad, x - 16 - bw)
        hi = max(bottom_top - 4 - bh, top_lo)
        base_ly = min(max(y - bh // 2, top_lo), hi)
        ly = base_ly
        for k in range(40):                       # deterministic down/up nudge until clear
            cand = min(max(base_ly + ((k + 1) // 2) * lh * (1 if k % 2 == 0 else -1), top_lo), hi)
            if not _collides((lx, cand, lx + bw, cand + bh), placed):
                ly = cand
                break
        placed.append((lx, ly, lx + bw, ly + bh))
        d.rectangle([lx - 3, ly - 2, lx + bw + 3, ly + bh + 1], fill=_BG)        # legibility halo
        for i, ln in enumerate(lines):
            d.text((lx, ly + i * lh), ln, font=f_label, fill=_INK)
        anchor_x = lx if lx >= x else lx + bw
        if abs(anchor_x - x) > 56 or abs(ly + bh // 2 - y) > 36:                  # leader line
            d.line([(x, y), (anchor_x, ly + bh // 2)], fill=_LINE, width=1)

    # callouts legend (truncated per line so nothing clips at the right edge)
    if spec.callouts:
        d.text((pad, callouts_y), "Callouts:", font=f_small, fill=_MUTED)
        for i, c in enumerate(spec.callouts, 1):
            d.text((pad + 12, callouts_y + 18 * i),
                   f"• {_fit(d, c, f_small, width - 2 * pad - 12)}", font=f_small, fill=_INK)

    # caption footer (single line, truncated to fit so it never clips at the right edge)
    if spec.caption:
        d.text((pad, height - 30), _fit(d, spec.caption, f_small, width - 2 * pad),
               font=f_small, fill=_MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")        # deterministic: no timestamp chunk by default
    return buf.getvalue()


def render_spec_to_file(spec, path, **kw) -> str:
    data = render_spec(spec, **kw)
    Path(path).write_bytes(data)
    return str(path)


# --------------------------------------------------------------------------- WS-4 retrieved plate

_REF_BANNER = "REFERENCE PLATE — NOT THIS PATIENT'S IMAGING"


def render_plate(src_path, out_path, *, citation: str = "", labels=(), width: int = 900) -> str:
    """Annotate a RETRIEVED textbook plate: scale it to a standard width and draw a mandatory
    reference banner (so neither the reader nor the image judge mistakes it for the patient's own
    imaging), the corpus citation, and optional structure labels. PIL only — no new dependency.
    Deterministic given the same source image + arguments.

    Distinct from `render_spec` (the schematic renderer, frozen): this overlays a real plate; it
    never synthesizes anatomy."""
    plate = Image.open(src_path).convert("RGB")
    scale = width / plate.width
    body_h = max(1, int(plate.height * scale))
    plate = plate.resize((width, body_h))

    band = 34          # top reference banner
    foot = 26 if citation else 0
    img = Image.new("RGB", (width, band + body_h + foot), _BG)
    d = ImageDraw.Draw(img)
    # top reference banner (yellow caution, like the schematic banner) — honesty about the source
    d.rectangle([0, 0, width, band], fill=_BANNER_BG)
    d.rectangle([0, band - 2, width, band], fill=_INK)   # thick black rule under the banner
    f_band = _font(15, bold=True)
    d.text((10, 8), _REF_BANNER, font=f_band, fill=_INK)
    img.paste(plate, (0, band))
    # optional structure labels along the top of the plate body
    f_small = _font(13)
    for i, lab in enumerate(labels or ()):
        d.text((10, band + 6 + 18 * i), f"• {_fit(d, str(lab), f_small, width - 20)}",
               font=f_small, fill=_INK)
    if citation:
        d.text((10, band + body_h + 5), _fit(d, f"Reference: {citation}", f_small, width - 20),
               font=f_small, fill=_MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    Path(out_path).write_bytes(buf.getvalue())
    return str(out_path)
