"""Tests for neuro_core.figure_guards (region/level/domain guard logic) and
neuro_core.figure_retriever._row_caption. Moved from tests/test_retrieve.py as part of
the caseboard-to-neuro_core migration."""

from neuro_core.figure_guards import figure_offtarget as _figure_offtarget
from neuro_core.figure_retriever import _row_caption


def test_figure_guard_blocks_diagnostic_cross_sectional_imaging():
    # CT / MRI / CT-angiogram are diagnostic scans, not operative atlas anatomy — the
    # bigger cropped index surfaces these and they must be dropped from a surgical board.
    assert _figure_offtarget("Fig 28.1 CT angiogram showing the right MCA aneurysm",
                             "pterional craniotomy for MCA bifurcation clipping")
    assert _figure_offtarget("Axial temporal bone CT images, profound sensorineural hearing loss",
                             "left retrosigmoid CPA vestibular schwannoma")
    assert _figure_offtarget("Sagittal T2-weighted MRI of the cervical spine",
                             "C1-C2 Goel-Harms atlantoaxial fixation")
    # but an intra-op fluoroscopy / plain lateral X-ray of a construct is KEPT (useful)
    assert not _figure_offtarget("Lateral plain X-ray used to identify the correct surgical level",
                                 "C1-C2 Goel-Harms atlantoaxial fixation",
                                 book="Spine Surgery Tricks of the Trade Vaccaro")


def test_figure_guard_recognizes_new_spine_atlas_as_spine_book():
    bk = "Surgical Anatomy and Techniques to the Spine"
    # the new spine atlas must NOT leak onto cranial cases (observed: p.669 post-op MRI)
    assert _figure_offtarget("Figure 66-12 MRI after posterior approach for schwannoma",
                             "left retrosigmoid CPA vestibular schwannoma", book=bk)
    assert _figure_offtarget("Figure 12-1 instrumentation construct",
                             "pterional MCA bifurcation aneurysm clipping", book=bk)
    # but it is welcome on a spine case (it supplies the C1-C2 bullseyes)
    assert not _figure_offtarget("C1 lateral mass and C2 pars screw construct",
                                 "C1-C2 Goel-Harms atlantoaxial fixation", book=bk)


def test_figure_region_guard_rejects_cross_region_and_level():
    # cranial case must reject a spine plate
    assert _figure_offtarget("Lumbar pedicle screw entry point",
                             "pterional craniotomy for MCA aneurysm")
    # spine case must reject a cranial plate
    assert _figure_offtarget("Sylvian fissure and middle cerebral artery branches",
                             "C1-C2 posterior fusion for atlantoaxial instability")
    # cervical case rejects a lumbar figure (level conflict)
    assert _figure_offtarget("Lumbar pedicle angles and dimensions",
                             "Posterior C1 lateral mass and C2 pedicle screw, atlantoaxial")
    # on-target figures are kept
    assert not _figure_offtarget(
        "Left cerebellopontine angle: AICA between the facial and vestibulocochlear nerves",
        "retrosigmoid craniotomy for vestibular schwannoma")
    assert not _figure_offtarget("C1 lateral mass and C2 pedicle screw trajectory",
                                 "C1-C2 atlantoaxial fixation")


def test_figure_region_guard_uses_source_book():
    # spine-book figure with a generic (no region term) caption on a cranial case -> blocked
    assert _figure_offtarget("An attempt to correct shoulder asymmetry",
                             "retrosigmoid craniotomy for vestibular schwannoma",
                             book="Textbook of Spinal Surgery Bridwell")
    # cranial-book figure on a spine case -> blocked
    assert _figure_offtarget("Stepwise dissection of the cavernous sinus",
                             "C1-C2 posterior atlantoaxial fixation", book="Rhoton Cranial Anatomy")
    # same-region book stays
    assert not _figure_offtarget("C1 lateral mass screw entry point",
                                 "C1-C2 atlantoaxial fixation", book="Benzel Spine")


def test_figure_level_guard_uses_page_context_for_truncated_caption():
    # caption only says "Pedicle screw placement" but the page is lumbar -> blocked on a C1-C2 case
    assert _figure_offtarget(
        "Pedicle screw placement, entrance point", "Posterior C1 lateral mass and C2 pedicle screw, atlantoaxial",
        book="Benzel Spine", context="Lumbar pedicle screw placement at L4 and L5 with the entrance point")
    # a thoracic plate is off-target for a cervical/CVJ case
    assert _figure_offtarget("Pedicle screws at T8 and T9 for deformity",
                             "C1-C2 Goel-Harms atlantoaxial fixation", book="Bridwell")
    # the atlantoaxial construct stays even though its page mentions c3-c7 in passing
    assert not _figure_offtarget(
        "Atlantoaxial bony anatomy after C1 lateral mass and C2 pedicle screw",
        "C1-C2 Goel-Harms atlantoaxial", book="Schmidek and Sweet",
        context="cervical spine C2 C3 C4 lateral mass screw technique")
    # ACDF (cervical) must still reject a lumbar plate seen only in the page context
    assert _figure_offtarget("Interbody graft placement",
                             "C5-6 ACDF for cervical myelopathy with interbody graft",
                             context="lumbar interbody fusion at L4-L5")


def test_figure_guard_blocks_peripheral_nerve_and_cervical_subregion():
    # peripheral-nerve / brachial-plexus surgery figure on a C1-C2 case
    assert _figure_offtarget("Double fascicular nerve transfer; the nerve to brachialis",
                             "Posterior C1-C2 Goel-Harms atlantoaxial fixation")
    # subaxial (C4-C5) plate on a CVJ (C1-C2) case
    assert _figure_offtarget("Lateral mass fixation at C4 and C5 and pedicle screw",
                             "Posterior C1 lateral mass and C2 pedicle Goel-Harms atlantoaxial")
    # CVJ plate on a subaxial (ACDF) case
    assert _figure_offtarget("Atlantoaxial C1-C2 transarticular screw and odontoid",
                             "C5-6 ACDF subaxial cervical myelopathy")
    # same sub-region stays
    assert not _figure_offtarget("Atlantoaxial C1 lateral mass and C2 pedicle screw",
                                 "C1-C2 Goel-Harms atlantoaxial")


def test_figure_guard_anterior_posterior_fossa_divide():
    cpa = "retrosigmoid craniotomy for a cerebellopontine angle vestibular schwannoma"
    mca = "pterional craniotomy for clipping an MCA bifurcation aneurysm"
    lenticulostriate = ("Perforating arteries of the anterior perforated substance, including the "
                        "medial, intermediate, and lateral lenticulostriate arteries")
    aica_cpa = "The AICA passes between the facial and vestibulocochlear nerves in the CPA"
    # anterior-circulation plate is off-target on a posterior-fossa (CPA) case
    assert _figure_offtarget(lenticulostriate, cpa) is True
    # ...but on-target on the MCA case
    assert _figure_offtarget(lenticulostriate, mca) is False
    # posterior-fossa plate is off-target on the anterior-circulation (MCA) case
    assert _figure_offtarget(aica_cpa, mca) is True
    # ...but on-target on the CPA case
    assert _figure_offtarget(aica_cpa, cpa) is False


def test_figure_guard_blocks_nonoperative_angio_positioning():
    mca = "pterional craniotomy for clipping an MCA bifurcation aneurysm"
    pos = "Haughton view positioning for the ICA carotid siphon and MCA on angiography"
    assert _figure_offtarget(pos, mca) is True


def test_row_caption_prefers_gemini_then_falls_back_to_source():
    # Gemini caption (names the specific anatomy) wins over the generic source first-line.
    cap = _row_caption({
        "caption": "FIGURE 2.3. Pterional exposure of the circle of Willis.",
        "gemini_caption": ("Pterional exposure: MCA (middle cerebral artery) M1 segment "
                           "bifurcating into superior and inferior M2 trunks with "
                           "lenticulostriate perforators.")})
    assert "middle cerebral" in cap.lower() and "m2" in cap.lower()
    # Falls back to the source caption when the Gemini caption is empty or absent.
    assert _row_caption({"caption": "FIGURE 1. Source.", "gemini_caption": ""}) == "FIGURE 1. Source."
    assert _row_caption({"caption": "FIGURE 1. Source."}) == "FIGURE 1. Source."
    # The Gemini caption keeps a larger cap (it is pure signal, no legend bloat to trim),
    # so a >320-char anatomy caption is not truncated like a source caption would be.
    long_gem = "MCA (middle cerebral artery) M1 bifurcation with lenticulostriate. " * 10
    assert len(_row_caption({"caption": "x", "gemini_caption": long_gem})) > 320


# --- strict guard subset (Q&A path): cranial<->spine + non-op-angio only ----------------

def test_strict_blocks_cranial_spine_but_not_diagnostic_or_sellar():
    cranial_q = "middle cerebral artery aneurysm clipping"
    # spine plate on a cranial question -> blocked in BOTH modes (cranial<->spine is in strict)
    spine_cap = "Lumbar pedicle screw entry point and trajectory"
    assert _figure_offtarget(spine_cap, cranial_q, book="Benzel Spine", guards="strict") is True
    assert _figure_offtarget(spine_cap, cranial_q, book="Benzel Spine", guards="full") is True

    # angiographic figure whose caption names the modality -> NOT blocked in strict
    # (diagnostic-image is full-only); IS blocked in full. This is the key endovascular regression.
    angio_cap = ("CT (computed tomography) angiography and DSA demonstrate the ICA "
                 "and middle cerebral artery aneurysm")
    assert _figure_offtarget(angio_cap, cranial_q, book="Video Atlas", guards="strict") is False
    assert _figure_offtarget(angio_cap, cranial_q, book="Video Atlas", guards="full") is True

    # sellar plate on a non-sellar cranial question -> full-only guard (kept off Q&A)
    sellar_cap = "Transsphenoidal view of the pituitary gland and sella"
    assert _figure_offtarget(sellar_cap, cranial_q, book="Rhoton", guards="strict") is False
    assert _figure_offtarget(sellar_cap, cranial_q, book="Rhoton", guards="full") is True


def test_strict_blocks_nonop_angio_positioning():
    cap = "View positioning for the Haughton angiographic projection at 30 frames per second"
    assert _figure_offtarget(cap, "carotid stenting", guards="strict") is True


def test_full_is_the_default_guards():
    assert _figure_offtarget("Lumbar pedicle screw", "mca aneurysm", book="Benzel Spine") is True
