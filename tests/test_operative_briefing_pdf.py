"""Offline deterministic tests for the Operative Briefing Bundle PDF renderer (Plan 2).

Pure HTML/SVG builders + the fit ladder are exercised with fakes — no Chromium, no network.
The Chromium-bound orchestrator is tested only for its honest-error path and pure assembly.
"""
import io

import pypdf

from neuro_caseboard.operative_briefing_pdf import count_pdf_pages


def _blank_pdf(n: int) -> bytes:
    w = pypdf.PdfWriter()
    for _ in range(n):
        w.add_blank_page(width=595, height=842)  # A4 points
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_count_pdf_pages_counts_rendered_pages():
    assert count_pdf_pages(_blank_pdf(1)) == 1
    assert count_pdf_pages(_blank_pdf(3)) == 3
