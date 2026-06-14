"""Pure presenter: turn an in-memory Dossier into what the Streamlit Build view needs —
the board body as markdown, a de-duped figure list, and the evidence summary — with no disk
access. Keeping this out of the Streamlit script makes the Build logic unit-testable.

render_md embeds figures as ``![Fig](local/path)`` lines, which Streamlit's ``st.markdown``
cannot resolve from the local filesystem; the view shows figures via ``st.image`` instead, so
this presenter strips those inline image-embed lines from the markdown body."""
from __future__ import annotations

import re
from dataclasses import dataclass

from neuro_caseboard.model import Dossier, EvidenceSummary, FigureItem
from neuro_caseboard.render_md import render_markdown

# a dedicated image-embed bullet line, e.g. "  - ![F1](/abs/p1.png)"
_IMG_LINE = re.compile(r"^\s*-?\s*!\[[^\]]*\]\([^)]*\)\s*$")


@dataclass
class BoardView:
    title: str
    markdown: str                 # board body, inline image-embed lines removed
    figures: list[FigureItem]     # de-duped by image_path, first-seen order
    summary: EvidenceSummary


def board_view(dossier: Dossier) -> BoardView:
    body = "\n".join(ln for ln in render_markdown(dossier).splitlines()
                     if not _IMG_LINE.match(ln))
    seen: set[str] = set()
    figures: list[FigureItem] = []
    for sec in dossier.sections:
        for fig in sec.figures:
            if fig.image_path in seen:
                continue
            seen.add(fig.image_path)
            figures.append(fig)
    return BoardView(title=dossier.title, markdown=body,
                     figures=figures, summary=dossier.summary)
