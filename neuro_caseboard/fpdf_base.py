"""Shared fpdf2 font setup for the clinical (offline) PDF renderers.

Owns DejaVu Unicode font registration (so ✓ ⚠ — etc. render as real glyphs, never the latin-1
'?' replacement) and the deterministic ASCII transliteration used when those fonts can't be
embedded. Imported by render_pdf.py (Dossier) and briefing_pdf.py's clinical Q&A fallback.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from fpdf import FPDF

_FONT_DIR = Path(__file__).parent / "assets" / "fonts"

# Deterministic ASCII fallback, used only when the Unicode font can't be embedded.
_REPL = {
    "≥": ">=", "≤": "<=", "×": "x", "→": "->", "—": "-", "–": "-",
    "“": '"', "”": '"', "‘": "'", "’": "'", "•": "-", "·": "-",
    "✓": "[OK]", "⚠": "[!]", "…": "...",
}


def ascii_fallback(s: str) -> str:
    for k, v in _REPL.items():
        s = s.replace(k, v)
    # strip any remaining non-ascii without ever producing '?'
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def register_fonts(pdf: FPDF):
    reg = _FONT_DIR / "DejaVuSans.ttf"
    bold = _FONT_DIR / "DejaVuSans-Bold.ttf"
    obl = _FONT_DIR / "DejaVuSans-Oblique.ttf"
    if reg.exists() and bold.exists() and obl.exists():
        pdf.add_font("DejaVu", "", str(reg))
        pdf.add_font("DejaVu", "B", str(bold))
        pdf.add_font("DejaVu", "I", str(obl))
        return "DejaVu", True
    return "Helvetica", False
