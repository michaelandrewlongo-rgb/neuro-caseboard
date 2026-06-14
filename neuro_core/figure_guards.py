"""Guard logic for the figure-retrieval lane.

Symbols copied verbatim from neuro_caseboard/retrieve.py so that neuro_core/figure_retriever.py
can apply region / level / domain guards without depending on the caseboard package.
The public entry point is ``figure_offtarget``; ``_figure_offtarget`` is kept as a
backwards-compat alias for any external importer of the former private name.
"""
import re

_CRANIAL_SIG = ("crani", "cortex", "cortical", "cerebr", "cerebell", "ventricle", "aneurysm",
                "glioma", "meningioma", "tumor", "tumour", "skull base", "sylvian", "pterional",
                "temporal lobe", "frontal lobe", "cpa", "cerebellopontine", "vestibular",
                "pituitary", " clip", "subarachnoid", "petrous", "clivus", "sulcus", "gyrus",
                "hemisphere", "thalam", "callosum", "insula")
_SPINE_SIG = ("spine", "spinal", "vertebra", "pedicle", "cervical", "thoracic", "lumbar",
              "sacral", "disc", "laminectomy", "fusion", "acdf", "corpectomy", "odontoid",
              "atlas", " axis", "atlantoaxial", "myelopath", "radiculopath", "scoliosis",
              "kyphosis", "spondyl")
# Spine levels. Only thoracic/lumbar/sacral are *block-worthy* on a cervical/cranial case:
# a cervical figure's page incidentally naming c3-c7 must NOT block a good atlantoaxial plate,
# but a page naming lumbar/thoracic is unambiguously a different operation.
_LEVELS = {
    "cervical": ("cervical", "c1", "c2", "c3", "c4", "c5", "c6", "c7", "atlas", " axis",
                 "atlanto", "odontoid", "subaxial", "craniovertebral"),
    "thoracic": ("thoracic", "t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9", "t10",
                 "t11", "t12", "costotransverse"),
    "lumbar": ("lumbar", "l1", "l2", "l3", "l4", "l5", "cauda equina", "spondylolisthesis"),
    "sacral": ("sacral", "sacrum", " s1", "iliac"),
}
_BLOCK_LEVELS = {"thoracic", "lumbar", "sacral"}

# Cervical sub-region, read from CAPTIONS only (page context names c-levels too loosely):
# the craniovertebral junction (occiput-C2) vs the subaxial spine (C3-C7).
_CVJ_TERMS = ("c1", "c2", "atlas", " axis", "atlanto", "odontoid", "dens", "craniovertebral",
              "occipitocervical", "suboccipital")
_SUBAXIAL_TERMS = ("c3", "c4", "c5", "c6", "c7", "subaxial")
# Peripheral-nerve / brachial-plexus surgery is a different subspecialty entirely.
_PERIPHERAL_NERVE = ("nerve transfer", "nerve graft", "brachial plexus", "fascicular",
                     "neurotization", "peripheral nerve", "ulnar nerve", "median nerve",
                     "radial nerve", "brachialis", "supraclavicular")
_SELLAR = ("pituitary", "sella", "sellar", "hypophys", "transsphenoidal", "parasellar")

# Within-cranial anterior(supratentorial)<->posterior-fossa divide. A blind image judge found a
# posterior-fossa/CPA board pulling an anterior-perforated-substance / lenticulostriate (circle of
# Willis) plate, and vice-versa risk: a posterior-fossa CN plate on an anterior-circulation (MCA)
# board. The cranial<->spine and sellar guards don't catch this intra-cranial drift. A figure is
# blocked only when it is UNAMBIGUOUSLY the other compartment (its compartment terms present, the
# case's compartment terms absent), so a circle-of-Willis plate that also shows basilar/cerebellar
# vessels is NOT blocked.
_POSTERIOR_FOSSA = ("cerebellopontine", "cpa", "retrosigmoid", "suboccipital", "far lateral",
                    "aica", "pica", "internal acoustic", "internal auditory", "vestibulocochlear",
                    "vestibular schwannoma", "acoustic neuroma", "jugular foramen", "foramen magnum",
                    "petroclival", "fourth ventricle", "brainstem", "cerebellar", "cerebellum",
                    "semicircular", "labyrinth", "glossopharyngeal", "hypoglossal", "trigeminal",
                    "petrous", "clivus", "meatal", "petrosal")
_ANTERIOR_CIRC = ("middle cerebral", "lenticulostriate", "anterior perforated substance",
                  "circle of willis", "anterior communicating", "recurrent artery of heubner",
                  "sylvian", "pterional", " mca", "acom", "anterior cerebral")

# Angiographic/fluoroscopic positioning & technique figures (projection setup, frame rate) are not
# operative anatomy — they diluted an MCA board with a "view positioning" plate.
_NONOP_ANGIO = ("view positioning", "haughton", "angiographic projection", "fluoroscopic projection",
                "radiographic projection", "frames per second", "frame rate", "projection view",
                "c-arm angulation", "tube angulation")

# Diagnostic-imaging / ICU books are radiographs and tracings, not operative anatomy — a
# figure lane for a surgical board should not draw from them.
_DIAGNOSTIC_BOOKS = ("neuroradiology core requisites", "neuroicu", "neurocritical")

# Cross-sectional diagnostic imaging (CT/MRI/CT-angiogram) is a patient scan, not operative
# atlas anatomy. The larger cropped index surfaces these; a surgical-anatomy board should not
# show them. Plain X-ray / fluoroscopy is intentionally NOT here — it is often intra-op
# construct imaging that IS wanted (e.g. a lateral film confirming a C1-C2 construct).
_DIAGNOSTIC_IMAGE = ("ct angiogram", "ct scan", "axial ct", "coronal ct", "sagittal ct",
                     "3d ct", "3-d ct", "ct images", "ct image", "mri", "magnetic resonance",
                     "t1-weighted", "t2-weighted", "t2 weighted", "computed tomography",
                     "angiogram showing", "angiogram demonstrating", "3d reconstruction",
                     "diffusion-weighted", "flair")

_VIGNETTE = re.compile(r"\b\d{1,3}[\s-]?year[\s-]?old\b|\bpresented with\b|\ba \d{1,2}[- ]year",
                       re.IGNORECASE)

# Decision-making / management-pathway flowcharts are text diagrams, not operative anatomy. A blind
# generalization test had a cerebral-venous-thrombosis management algorithm leak onto a vasospasm
# board. These are DEMOTED, not blocked: a genuinely on-topic algorithm (a strong lexical match for
# the case's own subject) can still surface when it is the best candidate, but a tangential one
# loses to real anatomy plates.
_FLOWCHART = ("algorithm", "flowchart", "flow chart", "flow-chart", "decision tree",
              "management pathway", "treatment pathway", "management algorithm",
              "treatment algorithm", "decision-making algorithm", "schematic algorithm")


def _cap_toks(s: str):
    return [t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2]


def _caption_head(text: str, max_chars: int = 320) -> str:
    """Cap a (possibly legend-bloated) figure caption to caption length: keep the panel
    detail the lexical lane needs but drop the trailing legend that ``get_text('blocks')``
    glues on. Trim to the last sentence boundary in the window, else the last word."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    cut = head.rfind(". ")
    return head[:cut + 1] if cut >= 60 else head.rsplit(" ", 1)[0]


# Medical abbreviations / synonyms so a claim saying "MCA" / "lenticulostriate" matches an
# atlas caption that spells out "middle cerebral artery" / "perforated substance".
_SYNONYMS = {
    "mca": ("middle", "cerebral"), "m1": ("middle", "cerebral"), "m2": ("middle", "cerebral"),
    "aca": ("anterior", "cerebral"), "a1": ("anterior", "cerebral"),
    "pca": ("posterior", "cerebral"), "ica": ("internal", "carotid"),
    "acom": ("anterior", "communicating"), "acoa": ("anterior", "communicating"),
    "pcom": ("posterior", "communicating"), "pcoa": ("posterior", "communicating"),
    "lenticulostriate": ("perforating", "perforator", "perforators", "perforated"),
    "perforators": ("perforating", "perforated"), "perforator": ("perforating", "perforated"),
    "aica": ("anterior", "inferior", "cerebellar"),
    "pica": ("posterior", "inferior", "cerebellar"),
    "sca": ("superior", "cerebellar"),
}


def _expand_terms(qterms: set) -> set:
    extra: set = set()
    for t in qterms:
        extra.update(_SYNONYMS.get(t, ()))
    return qterms | extra


def _levels_in(text: str):
    low = (text or "").lower()
    return {lv for lv, terms in _LEVELS.items() if any(t in low for t in terms)}


_SPINE_BOOKS = ("benzel spine", "bridwell", "spinal surgery", "vaccaro", "spine surgery",
                "techniques to the spine")   # "Surgical Anatomy and Techniques to the Spine"
_CRANIAL_BOOKS = ("rhoton", "fukushima", "greenberg")  # Schmidek/NeuroICU/Neuroradiology: mixed
# "Brain Anatomy and Neurosurgical Approaches" is deliberately NOT book-classified cranial:
# its far-lateral/suboccipital approach plates are legitimately wanted on CVJ (C1-C2) cases,
# so it is left to the per-figure caption/region guards rather than a blanket book block.


def figure_offtarget(caption: str, topic: str, book: str = "", context: str = "",
                     *, guards: str = "full") -> bool:
    """True when a figure is from a clearly different region than the case — by the
    cranial<->spine divide (caption OR source book), or a conflicting spine level. Level is
    read from the figure's PAGE CONTEXT (not just the column-truncated caption), so a lumbar
    plate whose caption is merely "Pedicle screw placement" is still caught on a C1-C2 case.

    ``guards="full"`` (default, boards) runs every guard. ``guards="strict"`` (Q&A free-text)
    runs ONLY the high-precision subset — cranial<->spine + non-operative-angio — and skips the
    guards that need a precise case sub-region a free-text question doesn't supply
    (diagnostic-image, peripheral-nerve, sellar, anterior<->posterior-fossa, spine level/CVJ).
    diagnostic-image is deliberately full-only: angiographic Q&A figures name their modality
    ("computed tomography", "ct angiogram"), so applying it on Q&A would over-block them."""
    cap = (caption or "").lower()
    top = (topic or "").lower()
    bk = (book or "").lower()
    if guards == "full" and any(x in cap for x in _DIAGNOSTIC_IMAGE):
        return True                          # diagnostic scan, not operative atlas anatomy
    if any(x in cap for x in _NONOP_ANGIO):
        return True                          # angio/fluoro positioning setup, not operative anatomy
    t_spine = any(s in top for s in _SPINE_SIG)
    t_cran = any(s in top for s in _CRANIAL_SIG)
    c_spine = any(s in cap for s in _SPINE_SIG)
    c_cran = any(s in cap for s in _CRANIAL_SIG)
    b_spine = any(x in bk for x in _SPINE_BOOKS)
    b_cran = any(x in bk for x in _CRANIAL_BOOKS)
    if t_spine and not t_cran and ((c_cran and not c_spine) or b_cran):
        return True
    if t_cran and not t_spine and ((c_spine and not c_cran) or b_spine):
        return True
    if guards != "full":
        return False                         # strict (Q&A): cranial<->spine + non-op-angio only
    # peripheral-nerve/brachial-plexus figures don't belong on a cranial or spinal board
    if any(x in cap for x in _PERIPHERAL_NERVE) and not any(x in top for x in _PERIPHERAL_NERVE):
        return True
    # a sellar/pituitary plate doesn't belong on a non-sellar cranial case (e.g. an MCA clip)
    if t_cran:
        t_sellar = any(x in top for x in _SELLAR)
        f_sellar = any(x in cap for x in _SELLAR)
        if f_sellar and not t_sellar:
            return True
        # within-cranial anterior<->posterior-fossa divide: block a figure that is unambiguously
        # the OTHER compartment from the case (its terms present, the case's terms absent).
        t_post = any(x in top for x in _POSTERIOR_FOSSA)
        t_ant = any(x in top for x in _ANTERIOR_CIRC)
        f_post = any(x in cap for x in _POSTERIOR_FOSSA)
        f_ant = any(x in cap for x in _ANTERIOR_CIRC)
        if t_ant and not t_post and f_post and not f_ant:
            return True                      # posterior-fossa plate on an anterior-circulation case
        if t_post and not t_ant and f_ant and not f_post:
            return True                      # anterior-circulation plate on a posterior-fossa case
    if t_spine:
        # block a clearly different region (thoracolumbar/sacral) the case isn't about,
        # read from caption + full page context.
        t_lv = _levels_in(top)
        f_lv = _levels_in(f"{caption} {context}".lower())
        if (f_lv & _BLOCK_LEVELS) - t_lv:
            return True
        # cervical sub-region (CAPTIONS only): a CVJ case rejects a subaxial-only plate and
        # vice versa (context names c-levels too loosely to use here).
        t_cvj = any(x in top for x in _CVJ_TERMS)
        t_sub = any(x in top for x in _SUBAXIAL_TERMS)
        f_cvj = any(x in cap for x in _CVJ_TERMS)
        f_sub = any(x in cap for x in _SUBAXIAL_TERMS)
        if t_cvj and not t_sub and f_sub and not f_cvj:
            return True
        if t_sub and not t_cvj and f_cvj and not f_sub:
            return True
    return False


# Backwards-compat alias so any code that imported _figure_offtarget continues to work.
_figure_offtarget = figure_offtarget
