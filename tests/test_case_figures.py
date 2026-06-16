"""generate_case_figures: author -> guard -> render -> FigureItems (schematic, never radiograph)."""

import json
from pathlib import Path

from neuro_caseboard.case_context import CaseContext
from neuro_caseboard.figures_gen import generate_case_figures

SPINE = CaseContext(laterality="left", level="C5-6",
                    pathology="cervical spondylotic myelopathy", procedure="ACDF",
                    surgical_goal="decompression")


def test_generate_writes_pngs_and_schematic_captions(tmp_path, monkeypatch):
    monkeypatch.setenv("CASEBOARD_LLM", "0")     # hermetic: force the deterministic author
    items = generate_case_figures(SPINE, tmp_path)
    assert items
    for it in items:
        assert it.caption.startswith("Schematic (not a radiograph)")
        assert it.citation == "generated schematic"
        assert Path(it.image_path).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_contradictory_spec_is_excluded(tmp_path):
    # one aligned (left) + one contradictory (right) spec -> the guard drops the right one.
    payload = json.dumps({"figures": [
        {"archetype": "spine_level", "title": "left approach", "side": "left", "level": "C5-6",
         "nodes": [{"id": "a", "label": "approach", "x": 0.2, "y": 0.5}]},
        {"archetype": "spine_level", "title": "right approach", "side": "right", "level": "C5-6",
         "nodes": [{"id": "b", "label": "wrong side", "x": 0.2, "y": 0.5}]},
    ]})
    items = generate_case_figures(SPINE, tmp_path, complete_fn=lambda s, u: payload)
    assert len(items) == 1                      # only the aligned (left) spec survived the guard
    assert "right" not in items[0].relevance.lower() or "left" in items[0].relevance.lower()
