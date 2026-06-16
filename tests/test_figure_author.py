"""Figure-spec author: CaseContext -> FigureSpecs. LLM-first (injected complete_fn, deterministic),
with a topic-agnostic deterministic fallback whose archetype + side/level track the case.
"""

import json

import pytest

from neuro_caseboard.case_context import CaseContext
from neuro_caseboard.figures_gen.author import build_figure_specs, deterministic_figure_specs

SPINE = CaseContext(laterality="left", level="C5-6",
                    pathology="cervical spondylotic myelopathy", procedure="ACDF",
                    surgical_goal="decompression")
CRANIAL = CaseContext(laterality="left", location="left frontal", pathology="glioma",
                      procedure="awake craniotomy", surgical_goal="maximal safe resection")
VASCULAR = CaseContext(laterality="left", location="MCA bifurcation",
                       pathology="ruptured MCA aneurysm", procedure="pterional clipping",
                       surgical_goal="clip ligation")


def _fake(payload):
    return lambda system, user: payload


def test_llm_author_parses_specs():
    out = json.dumps({"figures": [
        {"archetype": "corridor", "title": "Approach", "side": "left",
         "nodes": [{"id": "a", "label": "approach", "x": 0.2, "y": 0.5}]},
        {"archetype": "not-real", "title": "Map", "nodes": []},   # archetype defaults, still kept
    ]})
    specs = build_figure_specs(SPINE, complete_fn=_fake(out))
    assert len(specs) == 2
    assert specs[0].archetype == "corridor"
    assert specs[1].archetype == "anatomy_map"     # defaulted


def test_llm_author_falls_back_on_failure():
    def boom(s, u):
        raise RuntimeError("down")
    specs = build_figure_specs(SPINE, complete_fn=boom)
    assert specs and all(s.nodes for s in specs)    # deterministic fallback produced usable specs


@pytest.mark.parametrize("case,arch", [
    (SPINE, "spine_level"), (CRANIAL, "corridor"), (VASCULAR, "vessel_config")])
def test_deterministic_archetype_and_geometry_track_the_case(case, arch):
    specs = deterministic_figure_specs(case)
    assert len(specs) >= 2
    assert any(s.archetype == arch for s in specs)
    # the case side/level propagate so the guard can verify grounding
    primary = specs[0]
    assert primary.side == case.laterality
    if case.level:
        assert primary.level == case.level
    assert all(s.nodes for s in specs)


def test_deterministic_specs_are_topic_agnostic():
    text = " ".join(n.label.lower() for s in deterministic_figure_specs(SPINE) for n in s.nodes)
    text += " " + " ".join(c.lower() for s in deterministic_figure_specs(SPINE) for c in s.callouts)
    for foreign in ("aneurysm", "glioma", "vestibular", "facial nerve"):
        assert foreign not in text
