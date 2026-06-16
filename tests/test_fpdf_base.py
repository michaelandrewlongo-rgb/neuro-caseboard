"""The shared fpdf2 font setup: register the Unicode font when present, and a deterministic
ASCII transliteration that never emits '?'."""
from fpdf import FPDF

from neuro_caseboard.fpdf_base import register_fonts, ascii_fallback


def test_register_fonts_returns_family_and_unicode_flag():
    fam, uni = register_fonts(FPDF(format="A4"))
    # The repo ships DejaVu under neuro_caseboard/assets/fonts, so this resolves to Unicode.
    assert fam == "DejaVu" and uni is True


def test_ascii_fallback_transliterates_known_glyphs_without_question_marks():
    out = ascii_fallback("≥ 5 ✓ ⚠ — “x”")
    assert ">=" in out and "[OK]" in out and "[!]" in out
    assert "?" not in out and "✓" not in out
