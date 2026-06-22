"""PDF renderer for a Dossier (fpdf2) — the offline fallback when the HTML→PDF (Playwright)
path is unavailable. Styled to match the web GUI / HTML PDFs: "Neo Brutalism" — white ground,
black 2px borders, red/yellow accents, square corners, hard offset shadows, green/amber status.

Owns defects #1 (broken glyphs) and #4 (legend), and lays out the structured fixes:
- Embeds DejaVuSans (regular/bold/oblique) so ✓ ⚠ — etc. render as real glyphs, never
  the latin-1 '?' replacement. If the fonts are unavailable it falls back to Helvetica
  with a deterministic ASCII transliteration (so we still never emit '?').
- Colour-coded markers + a one-line legend (#4).
- Claim on its own line, an indented italic "Why:" line (#5), checkbox sub-items (#6).
- Figures rendered inline after the claim they support, with a complete caption,
  relevance line, and a bidirectional cross-link (#7).
- A real, rendered appendix (#8).
"""

from __future__ import annotations

import os
from pathlib import Path

from fpdf import FPDF

from caseprep.core.contracts import ArtifactRef
from neuro_caseboard.fpdf_base import register_fonts, ascii_fallback
from neuro_caseboard.model import Dossier, MARK, ASCII_MARK, fallback_notice

# Neo Brutalism palette.
_COLORS = {"supported": (26, 161, 26), "verify": (217, 119, 6)}   # green / amber
_BLACK = (0, 0, 0)
_GRAY = (51, 51, 51)
_RED = (255, 51, 51)
_YELLOW = (255, 255, 0)

# Standing confidentiality / clinician-verify banner on every page (LOOP_PROMPT §6).
VERIFY_BANNER = ("Confidential — clinical decision support only; "
                 "the surgeon verifies every recommendation.")


class _CaseboardPDF(FPDF):
    """fpdf2 with a standing per-page confidentiality/verify footer banner (yellow, brutalist)."""

    fam = "Helvetica"
    uni = False

    def footer(self):
        self.set_y(-14)
        x0, y0, w = self.l_margin, self.get_y(), self.w - self.l_margin - self.r_margin
        self.set_fill_color(*_YELLOW)
        self.set_draw_color(*_BLACK)
        self.set_line_width(0.5)
        self.rect(x0, y0, w, 7, style="DF")
        self.set_font(self.fam, "B", 7)
        self.set_text_color(*_BLACK)
        self.set_xy(x0, y0 + 1.3)
        msg = VERIFY_BANNER if self.uni else ascii_fallback(VERIFY_BANNER)
        self.cell(w, 4.4, msg, align="C")


def _rule(pdf, width=0.7):
    """A thick black brutalist horizontal rule at the current y."""
    pdf.set_draw_color(*_BLACK)
    pdf.set_line_width(width)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)


def render_pdf(dossier: Dossier, out_path) -> ArtifactRef:
    pdf = _CaseboardPDF(format="A4")
    pdf.set_auto_page_break(True, margin=22)   # room for the footer banner
    pdf.add_page()
    fam, uni = register_fonts(pdf)
    pdf.fam, pdf.uni = fam, uni                 # the footer uses these

    def t(s: str) -> str:
        return s if uni else ascii_fallback(s)

    def glyph(status: str) -> str:
        return (MARK if uni else ASCII_MARK).get(status, "")

    # ── masthead ──
    pdf.set_fill_color(*_RED)
    pdf.set_draw_color(*_BLACK)
    pdf.set_line_width(0.4)
    pdf.rect(pdf.l_margin, pdf.get_y() + 0.5, 4.5, 4.5, style="DF")   # red square mark
    pdf.set_xy(pdf.l_margin + 6.5, pdf.get_y())
    pdf.set_font(fam, "B", 12)
    pdf.set_text_color(*_BLACK)
    pdf.cell(0, 5.5, t("NEURO·CASEBOARD"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font(fam, "B", 8)
    pdf.set_text_color(*_RED)
    pdf.cell(0, 4, t("BUILD · PRE-OP DOSSIER"), new_x="LMARGIN", new_y="NEXT")

    # ── title ──
    pdf.set_font(fam, "B", 18)
    pdf.set_text_color(*_BLACK)
    pdf.multi_cell(0, 9, t(dossier.title), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    _rule(pdf, 0.8)
    pdf.ln(4)

    notice = fallback_notice(dossier.provenance)
    if notice:
        pdf.set_font(fam, "B", 9)
        pdf.set_text_color(180, 95, 0)            # amber, matches the verify marker
        pdf.multi_cell(0, 4.8, t("FALLBACK — " + notice), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_BLACK)
        pdf.ln(1)

    # ── legend (#4) ──
    pdf.set_font(fam, "B", 10)
    pdf.write(6, t("Markers:  "))
    for i, (status, label) in enumerate((("supported", "corpus-supported"),
                                         ("verify", "needs clinician verification"))):
        if i:
            pdf.set_text_color(*_BLACK)
            pdf.write(6, "      ")
        pdf.set_text_color(*_COLORS[status])
        pdf.set_font(fam, "B", 10)
        pdf.write(6, t(glyph(status) + " "))
        pdf.set_text_color(*_BLACK)
        pdf.set_font(fam, "", 10)
        pdf.write(6, t(label))
    pdf.ln(9)

    # ── evidence summary (#2: single axis) ──
    s = dossier.summary
    pdf.set_font(fam, "", 10)
    summ = (f"Evidence:   {glyph('supported')} {s.supported} corpus-supported    "
            f"{glyph('verify')} {s.to_verify} to verify    "
            f"{s.quarantined} quarantined (appendix)")
    pdf.multi_cell(0, 5, t(summ), new_x="LMARGIN", new_y="NEXT")

    has_appendix = not dossier.appendix.is_empty()
    if has_appendix:
        pdf.set_font(fam, "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.multi_cell(0, 5, t("See the appendix for evidence sources and off-target claims."),
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_BLACK)
    pdf.ln(2)

    for sec in dossier.sections:
        _render_section(pdf, fam, t, glyph, sec)

    if has_appendix:
        _render_appendix(pdf, fam, t, dossier.appendix)

    out_path = Path(out_path)
    pdf.output(str(out_path))
    return ArtifactRef(path=out_path, kind="pdf", media_type="application/pdf",
                       label=dossier.title, metadata={"sections": len(dossier.sections)})


def _render_section(pdf, fam, t, glyph, sec) -> None:
    if pdf.get_y() > pdf.h - 50:
        pdf.add_page()
    pdf.set_font(fam, "B", 13)
    pdf.set_text_color(*_BLACK)
    pdf.multi_cell(0, 7, t(sec.heading), new_x="LMARGIN", new_y="NEXT")
    _rule(pdf, 0.6)
    pdf.ln(2)
    if sec.intro:
        pdf.set_font(fam, "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.multi_cell(0, 5, t(sec.intro), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_BLACK)
    pdf.ln(1)

    linked_ids = set()
    for c in sec.claims:
        _render_claim(pdf, fam, t, glyph, c)
        for fig in sec.figures:
            if fig.fig_id in c.figure_ids:
                linked_ids.add(fig.fig_id)
                _render_figure(pdf, fam, t, fig)
    # figures not linked to a specific claim go at section end
    for fig in sec.figures:
        if fig.fig_id not in linked_ids:
            _render_figure(pdf, fam, t, fig)

    _render_literature(pdf, fam, t, getattr(sec, "literature", None))

    for ref in sec.cross_refs:
        pdf.set_font(fam, "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.multi_cell(0, 5, t(ref), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_BLACK)
    pdf.ln(2)


def _render_claim(pdf, fam, t, glyph, c) -> None:
    # Brutalist claim card: black border + hard offset shadow + status-colored left bar.
    if pdf.get_y() > pdf.h - 55:
        pdf.add_page()
    base = pdf.l_margin
    w = pdf.w - pdf.r_margin - base
    y0 = pdf.get_y()

    pdf.set_left_margin(base + 6)
    pdf.set_x(base + 6)
    pdf.ln(1.6)                                   # top padding

    pdf.set_font(fam, "B", 10)
    pdf.set_text_color(*_COLORS.get(c.status, _BLACK))
    pdf.write(5.5, t(glyph(c.status) + " "))
    pdf.set_text_color(*_BLACK)
    pdf.set_font(fam, "", 10)
    figref = ""
    if c.figure_ids:
        figref = "  (see " + ", ".join(f"Fig {fid}" for fid in c.figure_ids) + ")"
    pdf.write(5.5, t(c.text + figref))
    pdf.ln(6)
    if c.why:
        pdf.set_font(fam, "B", 7)
        pdf.set_text_color(*_RED)
        pdf.set_x(base + 10)
        pdf.write(4.6, t("WHY  "))
        pdf.set_font(fam, "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.multi_cell(0, 4.6, t(c.why), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_BLACK)
    for item in c.sub_items:
        pdf.set_font(fam, "", 10)
        pdf.set_x(base + 10)
        pdf.multi_cell(0, 5, t("[ ]  " + item), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.6)                                   # bottom padding
    pdf.set_left_margin(base)

    y1 = pdf.get_y()
    if y1 > y0:                                   # only box when it didn't page-break
        h = y1 - y0
        pdf.set_draw_color(*_BLACK)
        pdf.set_line_width(0.7)                   # hard offset shadow (L)
        pdf.line(base + w + 0.9, y0 + 0.9, base + w + 0.9, y1 + 0.9)
        pdf.line(base + 0.9, y1 + 0.9, base + w + 0.9, y1 + 0.9)
        pdf.set_line_width(0.4)                   # border
        pdf.rect(base, y0, w, h, style="D")
        pdf.set_fill_color(*_COLORS.get(c.status, _BLACK))
        pdf.rect(base, y0, 2.2, h, style="F")     # status left bar
    pdf.set_y(y1)
    pdf.ln(3)


def _render_figure(pdf, fam, t, fig) -> None:
    if pdf.get_y() + 70 > pdf.h - pdf.b_margin:
        pdf.add_page()
    # Resolve the stored build-time path to the runtime ASSETS_DIR before embedding, so a
    # container that mounts figures at /data/figures still renders them in the exported PDF.
    from neuro_core.asset_paths import resolve_asset_path
    from neuro_core.config import load_config
    resolved = resolve_asset_path(fig.image_path, load_config().assets_dir) if fig.image_path else None
    if resolved and resolved.is_file():
        try:
            pdf.image(str(resolved), w=min(pdf.epw, 110))
        except Exception:
            pass
    pdf.set_font(fam, "B", 8)
    pdf.set_text_color(*_RED)
    pdf.write(4, t(f"Fig {fig.fig_id} "))
    pdf.set_font(fam, "I", 8)
    pdf.set_text_color(*_GRAY)
    pdf.multi_cell(0, 4, t(f"— {fig.caption}"), new_x="LMARGIN", new_y="NEXT")
    if fig.relevance:
        pdf.multi_cell(0, 4, t(fig.relevance), new_x="LMARGIN", new_y="NEXT")
    if fig.claim_ref:
        pdf.multi_cell(0, 4, t(f'supports: "{fig.claim_ref}"'), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*_BLACK)
    pdf.ln(2)


def _render_literature(pdf, fam, t, lit) -> None:
    """Contemporary-literature block ([L#] axis), separate from corpus markers (WS-3)."""
    if not lit or not getattr(lit, "narrative", ""):
        return
    if pdf.get_y() > pdf.h - 40:
        pdf.add_page()
    pdf.set_font(fam, "B", 10)
    pdf.set_text_color(*_BLACK)
    pdf.multi_cell(0, 5.5, t("Contemporary Literature"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(fam, "", 9)
    pdf.multi_cell(0, 4.6, t(lit.narrative), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(fam, "", 8)
    for c in getattr(lit, "citations", []) or []:
        link = f"https://doi.org/{c.doi}" if getattr(c, "doi", "") else getattr(c, "url", "")
        meta = " ".join(p for p in (c.journal, str(c.year or "")) if p)
        tail = (f" — {meta}" if meta else "") + (f" · {link}" if link else "")
        pdf.set_text_color(*_RED)
        pdf.write(4.2, t(f"[L{c.n}] "))
        pdf.set_text_color(*_GRAY)
        pdf.multi_cell(0, 4.2, t(f"{c.title}{tail}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*_BLACK)
    pdf.ln(1.5)


def _render_appendix(pdf, fam, t, appendix) -> None:
    pdf.add_page()
    pdf.set_font(fam, "B", 13)
    pdf.set_text_color(*_BLACK)
    pdf.multi_cell(0, 7, t("Appendix — evidence sources & off-target claims"),
                   new_x="LMARGIN", new_y="NEXT")
    _rule(pdf, 0.6)
    pdf.ln(2)
    for e in appendix.entries:
        pdf.set_font(fam, "B", 11)
        pdf.multi_cell(0, 6, t(e.heading), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(fam, "", 9)
        for it in e.items:
            pdf.multi_cell(0, 4.6, t("- " + it), new_x="LMARGIN", new_y="NEXT")
        for sr in e.sources:
            pdf.multi_cell(0, 4.6, t("- " + sr), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
