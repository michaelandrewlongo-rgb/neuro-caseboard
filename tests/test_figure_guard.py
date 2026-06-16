"""The schematic guard: reject any figure spec whose side / level / region contradicts the
CaseContext (LOOP_PROMPT §6 — schematics must be grounded, never cross-region)."""

from neuro_caseboard.case_context import CaseContext
from neuro_caseboard.figures_gen.spec import FigureSpec
from neuro_caseboard.figures_gen.guard import guard_spec, filter_specs

SPINE = CaseContext(laterality="left", level="C5-6",
                    pathology="cervical spondylotic myelopathy", procedure="ACDF")
CRANIAL = CaseContext(laterality="left", location="left frontal",
                      pathology="glioma", procedure="awake craniotomy")


def _spec(**kw):
    base = dict(archetype="spine_level", title="t", side="left", level="C5-6",
                region="cervical spine")
    base.update(kw)
    return FigureSpec.from_dict(base)


def test_aligned_spec_passes():
    ok, reason = guard_spec(_spec(), SPINE)
    assert ok, reason


def test_contradictory_side_rejected():
    ok, reason = guard_spec(_spec(side="right"), SPINE)
    assert not ok and "side" in reason.lower()


def test_contradictory_level_rejected():
    ok, reason = guard_spec(_spec(level="L4-5"), SPINE)
    assert not ok and "level" in reason.lower()


def test_cross_region_rejected():
    # a cervical-spine schematic for a cranial frontal case is off-region
    ok, reason = guard_spec(
        FigureSpec.from_dict(dict(archetype="spine_level", title="t", side="left",
                                  region="cervical spine vertebral body")),
        CRANIAL)
    assert not ok and "region" in reason.lower()


def test_filter_keeps_only_passing():
    good = _spec()
    bad = _spec(side="right")
    kept = filter_specs([good, bad], SPINE)
    assert good in kept and bad not in kept
