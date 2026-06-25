"""Operative Briefing Bundle PDF — render an OperativeBriefingBundle (Plan 1) to A4.

Three surfaces, hard-separated: page 1 is a citation-free, figure-free operative briefing
held to <=2 pages by a fit ladder; then a figure atlas; then a references/evidence page.
Signal print identity via exec_navy tokens. Pure HTML/SVG builders test offline; the
Chromium orchestrator supplies the authoritative page-count measure (render -> pypdf).
"""
from __future__ import annotations

import html
import io
import os
from dataclasses import dataclass, field

import pypdf

from neuro_caseboard.exec_navy import PRINT_TOKENS, SIGNAL_TOKENS


def count_pdf_pages(data: bytes) -> int:
    """Authoritative page count of a rendered PDF (what pagination actually produced)."""
    return len(pypdf.PdfReader(io.BytesIO(data)).pages)


def _tokens(theme: str) -> str:
    return PRINT_TOKENS if theme == "print" else SIGNAL_TOKENS
