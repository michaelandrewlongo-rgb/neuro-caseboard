"""PDF renderer for a Dossier (fpdf2).

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
from neuro_caseboard.model import Dossier, MARK, ASCII_MARK

_COLORS = {"supported": (0, 128, 0), "verify": (180, 95, 0)}
_BLACK = (0, 0, 0)
_GRAY = (90, 90, 90)


def render_pdf(dossier: Dossier, out_path) -> ArtifactRef:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_page()
    fam, uni = register_fonts(pdf)

    def t(s: str) -> str:
        return s if uni else ascii_fallback(s)

    def glyph(status: str) -> str:
        return (MARK if uni else ASCII_MARK).get(status, "")

    # ── title ──
    pdf.set_font(fam, "B", 18)
    pdf.set_text_color(*_BLACK)
    pdf.multi_cell(0, 9, t(dossier.title), new_x="LMARGIN", new_y="NEXT")
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
    if pdf.get_y() > pdf.h - 45:
        pdf.add_page()
    pdf.set_font(fam, "B", 13)
    pdf.set_text_color(*_BLACK)
    pdf.multi_cell(0, 7, t(sec.heading), new_x="LMARGIN", new_y="NEXT")
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

    for ref in sec.cross_refs:
        pdf.set_font(fam, "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.multi_cell(0, 5, t(ref), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_BLACK)
    pdf.ln(2)


def _render_claim(pdf, fam, t, glyph, c) -> None:
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
        pdf.set_font(fam, "I", 9)
        pdf.set_text_color(*_GRAY)
        pdf.set_x(pdf.l_margin + 6)
        pdf.multi_cell(0, 4.6, t("Why: " + c.why), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_BLACK)
    for item in c.sub_items:
        pdf.set_font(fam, "", 10)
        pdf.set_x(pdf.l_margin + 6)
        pdf.multi_cell(0, 5, t("[ ]  " + item), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)


def _render_figure(pdf, fam, t, fig) -> None:
    if pdf.get_y() + 70 > pdf.h - pdf.b_margin:
        pdf.add_page()
    if fig.image_path and os.path.exists(fig.image_path):
        try:
            pdf.image(fig.image_path, w=min(pdf.epw, 110))
        except Exception:
            pass
    pdf.set_font(fam, "I", 8)
    pdf.set_text_color(*_GRAY)
    pdf.multi_cell(0, 4, t(f"Fig {fig.fig_id} — {fig.caption}"), new_x="LMARGIN", new_y="NEXT")
    if fig.relevance:
        pdf.multi_cell(0, 4, t(fig.relevance), new_x="LMARGIN", new_y="NEXT")
    if fig.claim_ref:
        pdf.multi_cell(0, 4, t(f'supports: "{fig.claim_ref}"'), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*_BLACK)
    pdf.ln(2)


def _render_appendix(pdf, fam, t, appendix) -> None:
    pdf.add_page()
    pdf.set_font(fam, "B", 13)
    pdf.set_text_color(*_BLACK)
    pdf.multi_cell(0, 7, t("Appendix — evidence sources & off-target claims"),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    for e in appendix.entries:
        pdf.set_font(fam, "B", 11)
        pdf.multi_cell(0, 6, t(e.heading), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(fam, "", 9)
        for it in e.items:
            pdf.multi_cell(0, 4.6, t("- " + it), new_x="LMARGIN", new_y="NEXT")
        for sr in e.sources:
            pdf.multi_cell(0, 4.6, t("- " + sr), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
