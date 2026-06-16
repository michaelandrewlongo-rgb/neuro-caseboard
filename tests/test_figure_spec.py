"""FigureSpec: the structured, LLM-authorable figure spec (the deterministic renderer's input).

Pure data + tolerant coercion of messy model JSON — clamps coordinates, drops malformed nodes,
defaults the archetype.
"""

from neuro_caseboard.figures_gen.spec import FigureSpec, FigureNode, ARCHETYPES


def test_from_dict_coerces_and_clamps():
    spec = FigureSpec.from_dict({
        "archetype": "spine_level", "title": "C5-6 ACDF corridor",
        "side": "Right", "level": "c5-6", "region": "cervical spine",
        "nodes": [
            {"id": "t", "label": "C5-6 disc", "x": 0.5, "y": 0.4, "kind": "target"},
            {"id": "o", "label": "off", "x": 1.8, "y": -3, "kind": "structure"},  # clamp to [0,1]
            {"label": "no id -> dropped", "x": 0.1, "y": 0.1},
        ],
        "edges": [{"src": "t", "dst": "o", "kind": "approach"}],
        "callouts": ["retract trachea medially", 42],
        "caption": "schematic",
    })
    assert spec.archetype == "spine_level"
    assert spec.level == "c5-6" and spec.side == "Right"
    ids = [n.id for n in spec.nodes]
    assert ids == ["t", "o"]                          # the id-less node dropped
    off = next(n for n in spec.nodes if n.id == "o")
    assert 0.0 <= off.x <= 1.0 and 0.0 <= off.y <= 1.0   # clamped
    assert spec.callouts == ["retract trachea medially", "42"]
    assert len(spec.edges) == 1


def test_from_dict_defaults_unknown_archetype():
    spec = FigureSpec.from_dict({"archetype": "not-a-thing", "title": "x"})
    assert spec.archetype == "anatomy_map"            # safe default
    assert spec.archetype in ARCHETYPES
    assert spec.nodes == [] and spec.edges == []
