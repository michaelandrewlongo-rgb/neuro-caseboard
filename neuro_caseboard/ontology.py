"""Topic-agnostic clinical coverage ontology — the generalizable scaffold.

A pre-operative board is "deep" when the *case-defining dimensions* are guaranteed
present (it is exactly why the hand-written family templates score 8/10). This module
encodes, for any neurosurgical procedure, which clinical DIMENSIONS a board must cover —
as generalizable concept labels, never case-specific clinical phrases. A case is tagged
on three axes (approach × pathology × population/context); the union of the tagged
archetypes' dimensions, plus a universal floor, is the coverage checklist the Planner
hands to the Author. The model supplies the actual content for each dimension.

This is the allowed carve-out from "no hardcoded clinical content": a *dimension* like
"expected blood loss + transfusion plan" applies to any tumor; it is a coverage
requirement, not an answer.
"""

from __future__ import annotations

# tag -> (signal substrings that imply the tag)
_SIGNALS: dict[str, tuple[str, ...]] = {
    # --- approach ---
    "anterior_cervical": ("acdf", "anterior cervical", "corpectomy", "cervical discectomy"),
    "posterior_cervical": ("posterior cervical", "laminoplasty", "c1-2", "c1–2", "atlantoaxial"),
    "instrumented_spine": ("fusion", "pedicle screw", "tlif", "plif", "instrumentation",
                           "deformity", "scoliosis", "lumbar", "thoracic"),
    "retrosigmoid_cpa": ("retrosigmoid", "cerebellopontine", "cpa", "acoustic", "vestibular schwannoma"),
    "translabyrinthine": ("translabyrinthine", "translab"),
    "pterional_skullbase": ("pterional", "orbitozygomatic", "skull base", "clinoid"),
    "transsphenoidal": ("transsphenoidal", "endonasal", "pituitary", "sellar"),
    "suboccipital_pfossa": ("suboccipital", "posterior fossa", "fourth ventricle", "4th ventricle",
                            "telovelar", "midline cerebellar"),
    "convexity_crani": ("convexity", "parasagittal", "frontal craniotomy", "temporal craniotomy",
                        "parietal craniotomy"),
    "transcortical_ventricular": ("transcortical", "intraventricular", "colloid cyst", "transcallosal"),
    # --- pathology ---
    "aneurysm": ("aneurysm", "clipping", "clip ligation"),
    "avm_fistula": ("avm", "arteriovenous", "fistula", "dural av"),
    "occlusive_vascular": ("endarterectomy", "carotid stenosis", "bypass", "moyamoya", "thrombectomy"),
    "meningioma": ("meningioma",),
    "glioma": ("glioma", "astrocytoma", "glioblastoma", "gbm", "oligodendroglioma"),
    "metastasis": ("metastasis", "metastatic"),
    "pediatric_pfossa_tumor": ("medulloblastoma", "ependymoma", "pilocytic", "juvenile pilocytic"),
    "degenerative_spine": ("myelopathy", "radiculopathy", "spondylosis", "stenosis", "herniation"),
    "csf_disorder": ("hydrocephalus", "chiari", "shunt", "etv"),
    "epilepsy_functional": ("epilepsy", "seizure focus", "dbs", "deep brain"),
    # --- population / context ---
    "pediatric": ("pediatric", "child", "infant", "paediatric"),
    "eloquent_awake": ("awake", "language mapping", "motor mapping", "eloquent", "dominant"),
    "oncologic": ("tumor", "tumour", "resection", "meningioma", "glioma", "metastasis",
                  "medulloblastoma", "schwannoma"),
    "ruptured_vascular": ("ruptured", "subarachnoid", "sah"),
}

# tag -> required clinical dimensions (generalizable concept labels)
_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "anterior_cervical": (
        "recurrent laryngeal nerve and approach-side choice",
        "carotid sheath / esophagus / trachea retraction limits",
        "vertebral artery as the lateral limit of safe dissection",
        "durotomy / CSF leak plan (patch, lumbar drain), higher with OPLL",
        "interbody graft / cage sizing, plating, segmental lordosis",
        "C5 (or level-adjacent) nerve root palsy",
        "expanding neck hematoma -> airway compromise bedside rescue",
    ),
    "instrumented_spine": (
        "screw/hardware trajectory and neurovascular structures at risk",
        "neuromonitoring (SSEP/MEP/EMG) thresholds and response to signal loss",
        "durotomy / CSF leak repair plan",
        "construct alignment / sagittal balance",
        "blood loss, transfusion trigger, and hemostasis plan",
    ),
    "retrosigmoid_cpa": (
        "CN VII identification + facial EMG / direct stimulation thresholds",
        "CN VIII / cochlear nerve and hearing-preservation monitoring (ABR/BAER)",
        "CN V at the superior pole and lower CN IX-XI at the caudal pole",
        "AICA loop and branches adherent to the capsule",
        "internal auditory canal drilling with labyrinth / semicircular canal preservation",
        "brainstem compression and cerebellar retraction injury",
        "CSF leak via petrous/mastoid air cells (bone wax, fat, watertight closure)",
        "positioning (lateral/park-bench vs sitting) and venous air embolism precautions",
    ),
    "pterional_skullbase": (
        "Sylvian fissure split and frontal/temporal lobe protection",
        "optic nerve / chiasm and carotid proximity at the skull base",
        "named perforators and parent-vessel preservation",
    ),
    "transsphenoidal": (
        "internal carotid arteries flanking the sella",
        "optic chiasm and cavernous sinus / cranial nerves III-VI",
        "CSF leak and sellar floor reconstruction",
        "post-op diabetes insipidus / endocrine and visual monitoring",
    ),
    "suboccipital_pfossa": (
        "hydrocephalus: pre-op EVD/ETV and post-op CSF diversion plan",
        "fourth-ventricle floor / brainstem and facial colliculus",
        "lower cranial nerves (IX, X, XII) and swallow/airway / bulbar function",
        "PICA and tonsillar/brainstem perforator preservation",
        "approach choice (telovelar vs transvermian) to reduce cerebellar mutism",
        "watertight dural closure and pseudomeningocele prevention",
        "prone positioning and venous air embolism risk",
    ),
    "convexity_crani": (
        "cortical draining veins and dural venous sinus preservation",
        "eloquent cortex proximity and need for mapping/monitoring",
        "dural opening, reconstruction, and watertight closure",
    ),
    "aneurysm": (
        "proximal control before final neck dissection; temporary clips ready",
        "named perforator (e.g. lenticulostriate) and parent-vessel preservation",
        "intra-operative rupture algorithm (proximal clip, suction, clip the neck)",
        "clip-position / patency confirmation (ICG videoangiography, micro-Doppler)",
        "adenosine-induced flow arrest / rapid pacing as a rescue",
        "brain relaxation (basal cistern / lamina terminalis CSF drainage, mannitol, EVD)",
        "post-SAH vasospasm window and nimodipine",
    ),
    "avm_fistula": (
        "angioarchitecture: feeders, nidus, and draining veins",
        "pre-operative embolization decision",
        "normal-perfusion-pressure breakthrough / staged management",
    ),
    "occlusive_vascular": (
        "shunt vs no-shunt decision and cerebral monitoring",
        "plaque endpoint, tacking sutures, and closure/patch",
        "hyperperfusion and embolic-stroke risk",
    ),
    "meningioma": (
        "circumferential dural devascularization and resection grade (Simpson)",
        "feeding vessels (e.g. middle meningeal) and pre-operative embolization decision",
        "cortical draining vein / venous sinus preservation",
        "expected blood loss, type-and-cross, large-bore venous access",
        "peritumoral edema management (dexamethasone) and gentle brain handling",
        "internal debulking then capsule dissection off the pial plane",
        "dural reconstruction / cranioplasty of involved bone, watertight closure",
    ),
    "glioma": (
        "extent-of-resection goal vs eloquent-structure preservation",
        "intra-operative adjuncts (neuronavigation with brain-shift awareness, ultrasound, 5-ALA)",
        "named white-matter tracts and vascular structures at the margin",
        "post-operative MRI timing for residual and molecular/IDH status",
    ),
    "pediatric_pfossa_tumor": (
        "oncologic staging: post-op MRI <48h, neuraxis MRI, CSF cytology",
        "molecular subgrouping and tumor-board / adjuvant pathway",
    ),
    "csf_disorder": (
        "CSF diversion strategy (EVD/ETV/shunt) and ICP control",
        "ventricular access and catheter trajectory",
    ),
    "eloquent_awake": (
        "cortical language/motor mapping with stimulation thresholds",
        "subcortical white-matter tract mapping (arcuate/SLF/IFOF, corticospinal)",
        "asleep-awake-asleep anesthesia, scalp block, airway/LMA contingency",
        "stimulation-induced seizure rescue (iced saline) with after-discharge monitoring",
        "negative-mapping functional resection margins",
        "patient cooperation/anxiety and SMA-syndrome counseling",
    ),
    "oncologic": (
        "expected blood loss, type-and-cross, and transfusion plan",
        "seizure prophylaxis and early post-operative imaging",
    ),
    "pediatric": (
        "weight-based allowable blood loss (% estimated blood volume) and transfusion trigger",
        "thermoregulation and pediatric positioning/airway considerations",
    ),
    "ruptured_vascular": (
        "re-rupture precautions and blood-pressure control before securing the lesion",
        "external ventricular drain for acute hydrocephalus",
    ),
}

# applied to every board regardless of tags (the attending-prep floor the must_cover lists under-weight)
_UNIVERSAL: tuple[str, ...] = (
    "positioning, pressure points, and venous air embolism risk where applicable",
    "anesthesia / team brief: what to have ready (blood, drugs, monitoring, devices)",
    "hemostasis strategy and named complication-specific rescue sequences",
    "immediate post-operative watch: what to monitor, for how long, and the bail-out",
)


def tag_archetypes(topic: str) -> list[str]:
    """Return the archetype tags implied by *topic* (multi-axis; order-stable)."""
    t = (topic or "").lower()
    return [tag for tag, sigs in _SIGNALS.items() if any(s in t for s in sigs)]


def required_dimensions(topic: str) -> list[str]:
    """Ordered, de-duplicated list of clinical dimensions a board for *topic* must cover."""
    dims: list[str] = []
    seen: set[str] = set()
    for tag in tag_archetypes(topic):
        for d in _DIMENSIONS.get(tag, ()):
            if d not in seen:
                seen.add(d)
                dims.append(d)
    for d in _UNIVERSAL:
        if d not in seen:
            seen.add(d)
            dims.append(d)
    return dims
