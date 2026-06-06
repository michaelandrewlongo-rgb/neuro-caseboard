import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Lines that begin a figure caption: "Figure 1-1: ...", "Fig. 3 ...", "Plate 5 ..."
CAPTION_RE = re.compile(r"^\s*(?:fig(?:ure)?|plate)\b[\s.:]*\S", re.IGNORECASE)


@dataclass
class FigureInfo:
    has_figure: bool
    caption: Optional[str]


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
