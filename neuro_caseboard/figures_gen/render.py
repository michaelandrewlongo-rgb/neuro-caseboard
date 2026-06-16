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

# Palette (fixed -> deterministic).
_BG = (255, 255, 255)
_INK = (22, 32, 44)
_MUTED = (88, 102, 118)
_LINE = (150, 162, 174)
_ACCENT = (14, 116, 144)          # deep teal (Executive-Navy accent)
_TARGET = (180, 73, 59)           # the target/lesion
_BANNER_BG = (169, 120, 27)       # amber caution
_KIND_COLOR = {"target": _TARGET, "corridor": _ACCENT, "vessel": (140, 60, 90),
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

    # frame
    d.rectangle([6, 6, width - 7, height - 7], outline=_LINE, width=2)

    # mandatory banner: this is a schematic, not a radiograph (top-right)
    banner = "SCHEMATIC — NOT A RADIOGRAPH"
    bw = d.textlength(banner, font=f_banner)
    banner_x = width - pad - bw - 16
    d.rectangle([banner_x, 16, width - pad + 2, 40], fill=_BANNER_BG)
    d.text((banner_x + 8, 19), banner, font=f_banner, fill=(255, 255, 255))

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

    # nodes + labels
    for n in spec.nodes:
        x, y = pos[n.id]
        color = _KIND_COLOR.get(n.kind, _INK)
        r = 9
        d.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=_BG, width=2)
        d.text((x + 14, y - 8), n.label, font=f_label, fill=_INK)

    # callouts legend
    y = height - pad - 18 * (len(spec.callouts) + 1)
    if spec.callouts:
        d.text((pad, y), "Callouts:", font=f_small, fill=_MUTED)
        for i, c in enumerate(spec.callouts, 1):
            d.text((pad + 12, y + 18 * i), f"• {c}", font=f_small, fill=_INK)

    # caption footer
    if spec.caption:
        d.text((pad, height - 30), spec.caption, font=f_small, fill=_MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG")        # deterministic: no timestamp chunk by default
    return buf.getvalue()


def render_spec_to_file(spec, path, **kw) -> str:
    data = render_spec(spec, **kw)
    Path(path).write_bytes(data)
    return str(path)
