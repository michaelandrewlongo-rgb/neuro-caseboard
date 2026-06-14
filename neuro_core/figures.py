import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

# Lines that begin a figure caption: "Figure 1-1: ...", "Fig. 3 ...", "Plate 5 ..."
CAPTION_RE = re.compile(r"^\s*(?:fig(?:ure)?|plate)\b[\s.:]*\S", re.IGNORECASE)


@dataclass
class FigureInfo:
    has_figure: bool
    caption: Optional[str]


@dataclass
class FigurePlate:
    """One cropped figure on a page: the saved crop, its full caption, the source
    bbox (PDF points), and reading-order index within the page."""
    figure_path: str
    caption: Optional[str]
    bbox: tuple
    order: int


def figure_area_fraction(page):
    """Fraction of the page covered by embedded raster images (0.0–~1.0)."""
    page_area = abs(page.rect.width * page.rect.height)
    if page_area == 0:
        return 0.0
    covered = 0.0
    for info in page.get_image_info():
        bbox = info.get("bbox")
        if not bbox:
            continue
        x0, y0, x1, y1 = bbox
        covered += abs((x1 - x0) * (y1 - y0))
    return covered / page_area


def detect_figure(page, area_threshold):
    return figure_area_fraction(page) >= area_threshold


def extract_caption(page):
    for line in page.get_text().splitlines():
        if CAPTION_RE.match(line):
            return line.strip()
    return None


def page_figure_info(page, area_threshold):
    if detect_figure(page, area_threshold):
        return FigureInfo(has_figure=True, caption=extract_caption(page))
    return FigureInfo(has_figure=False, caption=None)


def render_page_png(page, dpi, out_path):
    """Render a page to PNG at the given DPI. Skips if the file already exists
    (so a re-run does not re-render — the rendering pass is crash-resumable)."""
    out_path = Path(out_path)
    if out_path.exists():
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(dpi=dpi)
    pix.save(str(out_path))
    return out_path


# --- per-figure plate cropping ---------------------------------------------
#
# A textbook page is text-dominated, so embedding the whole-page render gives BiomedCLIP a
# noisy, mostly-text image and semantic figure retrieval underperforms. Cropping each
# embedded raster region to its own plate (and tagging it with its own full caption) is the
# upstream lever that makes text<->figure semantic retrieval work.


def _merge_bboxes(boxes, gap):
    """Union image bboxes whose `gap`-expanded rects touch, into connected groups —
    so a multi-panel figure becomes one plate but two separated figures stay distinct."""
    rects = [fitz.Rect(b) for b in boxes]
    i = 0
    while i < len(rects):
        grew = True
        while grew:
            grew = False
            expanded = fitz.Rect(rects[i]) + (-gap, -gap, gap, gap)
            j = i + 1
            while j < len(rects):
                if expanded.intersects(rects[j]):
                    rects[i] = fitz.Rect(rects[i]) | rects[j]
                    expanded = fitz.Rect(rects[i]) + (-gap, -gap, gap, gap)
                    del rects[j]
                    grew = True
                else:
                    j += 1
        i += 1
    return rects


def figure_plate_bboxes(page, area_threshold, *, gap=24.0, min_frac=0.03):
    """Distinct figure-plate rects on the page, grouped from its embedded raster images.
    Returns [] when no raster region is large enough to be a real plate (the caller then
    falls back to a whole-page render for vector-only figures). `area_threshold` is unused
    here — the per-plate `min_frac` is the gate; it is accepted for call-site symmetry."""
    page_area = abs(page.rect.width * page.rect.height) or 1.0
    raw = []
    for info in page.get_image_info():
        bbox = info.get("bbox")
        if not bbox:
            continue
        r = fitz.Rect(bbox) & page.rect    # clamp to page; off-page images -> empty
        if r.is_empty or r.x1 <= r.x0 or r.y1 <= r.y0:
            continue                       # entirely off-page / inverted -> not a plate
        if abs(r.width * r.height) / page_area < (min_frac / 4.0):
            continue                       # drop rules/logos before merging
        raw.append(r)
    if not raw:
        return []
    plates = [r for r in _merge_bboxes(raw, gap)
              if abs(r.width * r.height) / page_area >= min_frac]
    plates.sort(key=lambda r: (round(r.y0 / 20.0), r.x0))   # top-to-bottom, left-to-right
    return plates


def _norm_caption_text(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def _caption_head(text, max_chars=320):
    """Cap a caption block to caption length: keep the panel detail ("A, the AICA passes
    between VII/VIII") the lexical lane needs, but drop the multi-paragraph legend that
    ``get_text('blocks')`` glues on, whose stray words (e.g. 'disc dissector') otherwise
    poison downstream region guards. Trim to the last sentence boundary in the window."""
    text = _norm_caption_text(text)
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    cut = head.rfind(". ")
    return head[:cut + 1] if cut >= 60 else head.rsplit(" ", 1)[0]


def extract_caption_for_bbox(page, bbox, blocks=None):
    """The full (multi-line) caption belonging to the figure at `bbox`: the nearest text
    block beginning with a figure label that shares the figure's column; else the nearest
    text block just below it. Block text is whitespace-joined, so the caption is NOT
    truncated at its first physical line (the source of the old column-truncation bug)."""
    if blocks is None:
        blocks = page.get_text("blocks")
    fx0, fy0, fx1, fy1 = bbox
    labeled, below = [], []
    for b in blocks:
        if len(b) > 6 and b[6] == 1:        # skip image blocks
            continue
        bx0, by0, bx1, by1 = b[0], b[1], b[2], b[3]
        text = _norm_caption_text(b[4])
        if not text:
            continue
        if min(fx1, bx1) - max(fx0, bx0) <= 0:
            continue                        # different column — not this figure's caption
        vgap = by0 - fy1                     # > 0 means the block sits below the figure
        if CAPTION_RE.match(text):
            labeled.append((abs(vgap), text))
        elif vgap >= -2:
            below.append((vgap, text))
    if labeled:
        return _caption_head(min(labeled, key=lambda t: t[0])[1])
    if below:
        return _caption_head(min(below, key=lambda t: t[0])[1])
    return None


def crop_plate_png(page, bbox, dpi, out_path, margin=4.0):
    """Render only the figure region (bbox + small margin) to PNG. Idempotent — skips an
    existing file so the crop pass is crash-resumable like the page render. Returns None
    (without raising) for a degenerate region: an off-page bbox clamps to an inverted /
    sub-pixel rect whose 0-dimension pixmap crashes PNG save (e.g. Fukushima p22, an image
    placed at negative x)."""
    out_path = Path(out_path)
    if out_path.exists():
        return out_path
    clip = (fitz.Rect(bbox) + (-margin, -margin, margin, margin)) & page.rect
    min_pt = max(2.0, 72.0 / float(dpi))          # need at least ~1 px at this dpi
    if clip.is_empty or clip.x1 - clip.x0 < min_pt or clip.y1 - clip.y0 < min_pt:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        pix = page.get_pixmap(dpi=dpi, clip=clip)
        if pix.width < 1 or pix.height < 1:
            return None
        pix.save(str(out_path))
    except Exception:
        return None
    return out_path


def extract_figure_plates(page, area_threshold, *, dpi, assets_dir, book, pageno,
                          gap=24.0, min_frac=0.03, margin=4.0):
    """One cropped plate per distinct figure on the page, each with its own caption.
    Returns [] when the page has no qualifying raster figure (caller may fall back to a
    whole-page render for vector-only figures). Crops are saved as
    ``<assets>/<book>/p<NNNN>_f<II>.png`` and skipped if already present."""
    if not detect_figure(page, area_threshold):
        return []
    plates = figure_plate_bboxes(page, area_threshold, gap=gap, min_frac=min_frac)
    if not plates:
        return []
    blocks = page.get_text("blocks")
    out = []
    for i, rect in enumerate(plates, 1):
        out_path = Path(assets_dir) / book / f"p{pageno:04d}_f{i:02d}.png"
        saved = crop_plate_png(page, rect, dpi, out_path, margin=margin)
        if saved is None:
            continue                        # degenerate/off-page region — skip this plate
        cap = extract_caption_for_bbox(page, tuple(rect), blocks)
        out.append(FigurePlate(figure_path=str(saved), caption=cap,
                               bbox=(rect.x0, rect.y0, rect.x1, rect.y1), order=i))
    return out
