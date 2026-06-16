"""The deterministic schematic renderer: a FigureSpec -> labeled PNG, byte-stable (LOOP_PROMPT §2).

No text-to-image: the pixels are a pure function of the spec. Same spec -> identical bytes (in
process), so CI can diff renders.
"""

from neuro_caseboard.figures_gen.spec import FigureSpec
from neuro_caseboard.figures_gen.render import render_spec

_PNG = b"\x89PNG\r\n\x1a\n"


def _spec(archetype="spine_level"):
    return FigureSpec.from_dict({
        "archetype": archetype, "title": "C5-6 ACDF — operative corridor",
        "side": "left", "level": "C5-6", "region": "cervical spine",
        "nodes": [
            {"id": "skin", "label": "anterior approach", "x": 0.15, "y": 0.5, "kind": "corridor"},
            {"id": "disc", "label": "C5-6 disc", "x": 0.6, "y": 0.5, "kind": "target"},
            {"id": "cord", "label": "spinal cord", "x": 0.78, "y": 0.5, "kind": "structure"},
        ],
        "edges": [{"src": "skin", "dst": "disc", "kind": "approach"},
                  {"src": "disc", "dst": "cord", "kind": "relation"}],
        "callouts": ["retract trachea/esophagus medially", "carotid sheath lateral limit"],
        "caption": "Schematic of the anterior cervical corridor to C5-6.",
    })


def test_render_returns_png_bytes():
    data = render_spec(_spec())
    assert data[:8] == _PNG
    assert len(data) > 2000


def test_render_is_byte_stable():
    a = render_spec(_spec())
    b = render_spec(_spec())
    assert a == b                  # same spec -> identical bytes (deterministic, no timestamps)


def test_render_all_archetypes_without_error():
    for arch in ("corridor", "spine_level", "vessel_config", "anatomy_map"):
        data = render_spec(_spec(arch))
        assert data[:8] == _PNG


def test_render_handles_empty_nodes():
    data = render_spec(FigureSpec.from_dict({"archetype": "anatomy_map", "title": "bare"}))
    assert data[:8] == _PNG
