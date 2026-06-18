"""WS-4 — real-anatomy structures-at-risk figure: an annotated crop of a RETRIEVED textbook plate.

Offline + deterministic. A fake figure retriever stands in for the textbook-rag figure lane (none in
required CI). The retrieved plate is a labeled REFERENCE image (never the patient's imaging) and is
guarded against the case; a contradicting plate is rejected and we fall back to the deterministic
schematic (corridor untouched).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from caseprep.core.contracts import EvidenceRecord
from neuro_caseboard.case_context import CaseContext
from neuro_caseboard.figures_gen import generate_case_figures


@pytest.fixture(autouse=True)
def _deterministic_author(monkeypatch):
    # Force the offline deterministic figure author (no provider/network) for speed + determinism.
    monkeypatch.setenv("CASEBOARD_LLM", "0")

CRANIAL = CaseContext(laterality="left", location="MCA bifurcation", pathology="aneurysm",
                      procedure="pterional clipping", surgical_goal="clip ligation")

_REF = "Reference plate (not this patient's imaging)"


def _write_png(path, color=(190, 190, 190), size=(480, 360)):
    Image.new("RGB", size, color).save(path)
    return str(path)


class FakeFigret:
    def __init__(self, figure_path, caption, citation="Netter Atlas of Neuroanatomy, p.130"):
        self._fp, self._cap, self._cite = figure_path, caption, citation

    def retrieve(self, query, *, topic="", subdomain=None, top_n=3):
        return [EvidenceRecord(
            id="fig1", source="textbook", title=self._cap[:60], text=self._cap,
            metadata={"figure_path": self._fp, "caption": self._cap, "citation": self._cite,
                      "book": "Netter Atlas of Neuroanatomy", "page": 130})]


def test_plate_used_when_figret_available(tmp_path):
    plate = _write_png(tmp_path / "plate.png")
    figret = FakeFigret(plate, "Circle of Willis: middle cerebral artery and its branches at the "
                               "skull base, with the carotid bifurcation")
    items = generate_case_figures(CRANIAL, tmp_path, figret=figret)
    refs = [it for it in items if it.caption.startswith(_REF)]
    assert refs, f"expected a retrieved reference plate; got captions {[i.caption for i in items]}"
    r = refs[0]
    assert "Netter Atlas of Neuroanatomy, p.130" in r.citation
    assert Path(r.image_path).exists()
    Image.open(r.image_path).verify()                       # a valid PNG was written


def test_contradicting_plate_rejected_falls_back_to_schematic(tmp_path):
    plate = _write_png(tmp_path / "plate.png")
    # A lumbar-spine plate for a CRANIAL MCA aneurysm case -> off-region -> guard rejects.
    figret = FakeFigret(plate, "Lumbar spine L4-L5 intervertebral disc, lamina and exiting nerve roots")
    items = generate_case_figures(CRANIAL, tmp_path, figret=figret)
    assert not any(it.caption.startswith(_REF) for it in items), \
        "an off-region plate must be rejected by the guard"
    assert any(it.caption.startswith("Schematic") for it in items), \
        "fall back to the deterministic schematic"


def test_no_figret_is_deterministic_schematic(tmp_path):
    items = generate_case_figures(CRANIAL, tmp_path)         # figret=None (offline default)
    assert items
    assert all(it.caption.startswith("Schematic") for it in items), \
        "without a figure corpus every figure stays a deterministic schematic"
