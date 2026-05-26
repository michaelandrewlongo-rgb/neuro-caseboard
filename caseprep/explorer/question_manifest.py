"""Explorer question-manifest layer.

Produces a structured ``QuestionManifest`` that replaces generic ``needs input``
placeholders with case-specific operative questions.  The manifest is used by
the Auditor (to answer/adjudicate from evidence) and Compiler (to render the
final case board).

Design rules:
- Pure deterministic first pass — no LLM, no network.
- *Generative*: the Explorer should produce many questions; the Auditor later
  filters out wrong/irrelevant ones.  Better to ask too many than too few.
- Procedure-family-specific templates handle well-known families (VS, thrombectomy).
- A generic rule-based generator handles any neurosurgical case using profile,
  anatomy, pathology, and approach heuristics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ── data contracts ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QuestionCard:
    """One operative question the surgeon should answer before the procedure."""

    target_file: str          # e.g. "03-anatomy-at-risk.md"
    section_key: str          # e.g. "neural_structures"
    question: str             # the operative question
    why_it_matters: str       # intraoperative consequence
    answerability: str = "needs_patient_fact"
    compiler_slot: str = ""   # rendered heading, e.g. "Neural Structures"
    required_facts: list[str] = field(default_factory=list)
    evidence_needed: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_file": self.target_file,
            "section_key": self.section_key,
            "question": self.question,
            "why_it_matters": self.why_it_matters,
            "answerability": self.answerability,
            "compiler_slot": self.compiler_slot,
            "required_facts": self.required_facts,
            "evidence_needed": self.evidence_needed,
        }

    def render_card(self) -> str:
        """Render the card as a markdown list item for schema injection."""
        return (
            f"VERIFY: {self.question} — {self.why_it_matters}"
            f"  [{self.answerability}]"
        )


@dataclass(frozen=True)
class QuestionManifest:
    """Complete question manifest for a case."""

    procedure_family: str
    cards: list[QuestionCard] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "procedure_family": self.procedure_family,
            "cards": [card.to_dict() for card in self.cards],
        }


# ── anatomy section key → compiler_slot mapping ──────────────────────────────

_ANATOMY_SLOTS: dict[str, str] = {
    "surgical_corridor": "Surgical Corridor",
    "landmarks_in_order": "Landmarks In Order",
    "neural_structures": "Neural Structures",
    "arteries_perforators_veins_sinuses": "Arteries / Perforators / Veins / Sinuses",
    "functional_structures": "Functional Structures",
    "variants": "Variants",
    "no_fly_zones": "No-Fly Zones",
}

_OPERATIVE_SLOTS: dict[str, str] = {
    "positioning": "Positioning",
    "exposure": "Exposure",
    "critical_steps": "Critical Steps",
    "decision_points": "Decision Points",
    "stop_points": "Stop Points",
    "closure_reconstruction": "Closure / Reconstruction",
    "monitoring": "Monitoring",
    "equipment_adjuncts": "Equipment / Adjuncts",
    "attending_preferences_questions": "Attending Preferences / Questions",
}

_RISK_SLOTS: dict[str, str] = {
    "likely_complications": "Likely Complications",
    "catastrophic_complications": "Catastrophic Complications",
    "mitigation": "Mitigation",
    "rescue_triggers": "Rescue Triggers",
}


def _card(target: str, key: str, question: str, why: str,
          answerability: str = "needs_patient_fact",
          slots: dict[str, str] | None = None) -> QuestionCard:
    slot_map = slots or _ANATOMY_SLOTS
    return QuestionCard(
        target_file={"03": "03-anatomy-at-risk.md",
                     "04": "04-operative-plan.md",
                     "05": "05-risk-and-rescue.md"}.get(target, f"{target}.md"),
        section_key=key,
        question=question,
        why_it_matters=why,
        answerability=answerability,
        compiler_slot=slot_map.get(key, key),
    )


# ── rule-based generic question generator ────────────────────────────────────


def _keyword_match(text: str, *keywords: str) -> bool:
    """Case-insensitive substring match."""
    lower = text.lower()
    return any(kw.lower() in lower for kw in keywords)


def _any_match(values: list[str], *keywords: str) -> bool:
    return any(_keyword_match(v, *keywords) for v in values if v)


def _generate_anatomy_questions(
    topic: str,
    procedure: str,
    pathology: str,
    anatomic_location: str,
    approach: str,
    profile: str,
) -> list[QuestionCard]:
    cards: list[QuestionCard] = []

    # ── surgical corridor ──────────────────────────────────────────────
    if profile == "spine":
        cards.append(_card("03", "surgical_corridor",
            "Confirm spinal level, laterality, and vertebral artery course at target level",
            "Wrong-level surgery is a never-event; VA injury at C1-2 is catastrophic"))
    elif profile == "skull_base":
        cards.append(_card("03", "surgical_corridor",
            "Confirm craniotomy/craniectomy boundaries relative to venous sinuses",
            "Sigmoid/transverse sinus injury or inadequate exposure changes the approach"))
    else:
        cards.append(_card("03", "surgical_corridor",
            "Confirm craniotomy location, size, and relationship to eloquent structures",
            "Inadequate exposure or wrong-sided opening is a serious preventable error"))

    # ── landmarks ──────────────────────────────────────────────────────
    if profile == "spine":
        cards.append(_card("03", "landmarks_in_order",
            "Identify spinous processes, laminar edges, facet joints, and VA groove (C1-2)",
            "Landmark-based exposure prevents wrong-level exploration and VA injury"))
    elif profile == "skull_base":
        cards.append(_card("03", "landmarks_in_order",
            "Identify key surface landmarks: nasion, inion, zygoma, pterion, "
            "asterion. Define craniotomy relative to cranial sutures, venous "
            "sinuses, and skull base foramina.",
            "Systematic landmark identification prevents disorientation and "
            "inadvertent sinus/CN injury"))
    else:
        cards.append(_card("03", "landmarks_in_order",
            "Identify key surface landmarks, venous sinuses, and dural entry point",
            "Systematic landmark identification prevents disorientation"))

    # ── neural structures ──────────────────────────────────────────────
    if _keyword_match(anatomic_location, "cervical", "c1", "c2", "spine",
                      "spinal", "cord"):
        cards.append(_card("03", "neural_structures",
            "Spinal cord compression severity and level? C2 nerve root and ganglion relationship?",
            "Cord compression drives urgency and intraoperative monitoring plan; "
            "C2 root sacrifice vs preservation affects postop sensory deficit"))
    if _keyword_match(anatomic_location, "cpa", "cerebellopontine",
                      "acoustic", "vestibular",
                      "schwannoma", "meningioma"):
        cards.append(_card("03", "neural_structures",
            "Which cranial nerves (CN V, VII, VIII, IX-XI) are at risk? Brainstem compression?",
            "CN monitoring strategy and surgical trajectory depend on tumor-nerve interface"))
    elif profile == "skull_base":
        cards.append(_card("03", "neural_structures",
            "Which cranial nerves and eloquent regions are adjacent to the lesion? Optic nerve/chiasm? Cavernous sinus CNs? Sylvian fissure branches?",
            "CN involvement determines surgical trajectory, monitoring plan, and deficit risk"))
    if profile not in ("spine", "skull_base"):
        cards.append(_card("03", "neural_structures",
            "Which eloquent cortex, tracts, or cranial nerves are adjacent to the lesion?",
            "Determines mapping strategy, awake-vs-asleep decision, and deficit risk"))

    # ── arteries / perforators / veins / sinuses ───────────────────────
    if profile == "spine" and _keyword_match(topic, "c1", "c2", "cervical",
                                             "craniocervical"):
        cards.append(_card("03", "arteries_perforators_veins_sinuses",
            "Vertebral artery (V3 segment) course relative to C1-2 and tumor? "
            "Dominant vs non-dominant VA? Contralateral VA patency?",
            "VA injury at C1-2 is the dominant catastrophic risk; "
            "preop CTA/DSA defines safe drilling corridor"))
    elif profile == "spine":
        cards.append(_card("03", "arteries_perforators_veins_sinuses",
            "Vertebral artery, segmental arteries, and epidural venous plexus at target level?",
            "VA and segmental vessel injury cause spinal cord ischemia or uncontrollable bleeding"))
    elif profile == "skull_base":
        cards.append(_card("03", "arteries_perforators_veins_sinuses",
            "Major arteries (MCA, ACA, ICA) and perforators in the surgical corridor? "
            "Venous drainage (cavernous sinus, sphenoparietal sinus, Sylvian veins, "
            "vein of Labbé)? For posterior fossa: AICA, PICA, SCA, and labyrinthine artery?",
            "Vascular injury is the dominant cause of catastrophic neurosurgical outcome"))
    else:
        cards.append(_card("03", "arteries_perforators_veins_sinuses",
            "Major arteries, perforators, and draining veins in/near the surgical corridor?",
            "Vascular injury causes stroke, hemorrhage, or venous infarct"))

    # ── functional structures ──────────────────────────────────────────
    if profile == "spine" and _keyword_match(topic, "c1", "c2", "craniocervical"):
        cards.append(_card("03", "functional_structures",
            "Myelopathy signs/symptoms? Gait, hand function, bowel/bladder? "
            "Preop Nurick/mJOA grade?",
            "Degree of myelopathy drives timing, positioning precautions, and postop rehab plan"))
    elif profile == "spine":
        cards.append(_card("03", "functional_structures",
            "Radiculopathy vs myelopathy vs mechanical pain? "
            "Preop neurological exam including gait, reflexes, long-tract signs?",
            "Determines whether decompression target is nerve root, cord, or both"))
    elif _keyword_match(pathology, "schwannoma", "meningioma", "tumor",
                        "glioma", "metastasis") or profile == "skull_base":
        cards.append(_card("03", "functional_structures",
            "Neurological deficits attributable to mass effect? "
            "Seizure history, steroid response, functional status?",
            "Deficit pattern and functional baseline drive operative urgency and postop expectations"))
    else:
        cards.append(_card("03", "functional_structures",
            "Preop neurological exam, functional status, and deficit attributable to pathology?",
            "Baseline function determines surgical risk tolerance and rehab goals"))

    # ── variants ───────────────────────────────────────────────────────
    if profile == "spine" and _keyword_match(topic, "c1", "c2"):
        cards.append(_card("03", "variants",
            "Anomalous VA course (persistent first intersegmental artery, fenestrated VA, "
            "extradural origin of PICA)? Arcuate foramen/ponticulus posticus?",
            "VA anomaly at C1-2 changes safe screw trajectory and drilling limits"))
    elif profile == "spine":
        cards.append(_card("03", "variants",
            "Conjoined nerve roots, anomalous vertebral levels, transitional anatomy?",
            "Anomalous anatomy increases risk of wrong-level surgery and nerve root injury"))
    elif profile == "skull_base":
        cards.append(_card("03", "variants",
            "High-riding jugular bulb, anterior sigmoid sinus, dehiscent facial nerve, "
            "NF2 status?",
            "Variant anatomy blocks surgical access corridors and increases complication risk"))
    else:
        cards.append(_card("03", "variants",
            "Anatomic variants that change the surgical corridor or safe dissection limits?",
            "Unrecognized variants cause inadvertent injury during standard exposure"))

    # ── no-fly zones ───────────────────────────────────────────────────
    if profile == "spine" and _keyword_match(topic, "c1", "c2"):
        cards.append(_card("03", "no_fly_zones",
            "Define VA at C1-2 as absolute no-fly zone; contralateral VA patency; "
            "C2 ganglion limits; cord margin at craniocervical junction",
            "Pre-planned boundaries avoid VA injury, cord injury, and C2 neuralgia"))
    elif profile == "spine":
        cards.append(_card("03", "no_fly_zones",
            "Define VA trajectory, cord margin, and nerve root limits before osteotomy",
            "Pre-committed stopping points prevent catastrophic neural/vascular injury"))
    else:
        cards.append(_card("03", "no_fly_zones",
            "Define structures that must not be sacrificed: eloquent cortex, dominant "
            "draining veins, cranial nerves, brainstem perforators",
            "Pre-planned no-fly zones prevent permanent disabling deficits"))

    return cards


def _generate_operative_questions(
    topic: str,
    procedure: str,
    pathology: str,
    anatomic_location: str,
    approach: str,
    profile: str,
) -> list[QuestionCard]:
    cards: list[QuestionCard] = []

    # ── positioning ────────────────────────────────────────────────────
    if profile == "spine" and _keyword_match(topic, "cervical", "c1", "c2"):
        cards.append(_card("04", "positioning",
            "Prone with Mayfield pins, neutral head alignment, shoulders taped? "
            "Confirm pre-positioning neuro exam and IONM baselines?",
            "Head position changes can compress cord in unstable C1-2 lesions; "
            "IONM baselines must be obtained before final positioning",
            slots=_OPERATIVE_SLOTS))
    elif profile == "spine":
        cards.append(_card("04", "positioning",
            "Prone vs lateral? Wilson frame vs Jackson table? Arms tucked, "
            "pressure points padded, eyes protected? IONM baselines?",
            "Position-related nerve injury and pressure necrosis are preventable; "
            "IONM baselines before draping",
            slots=_OPERATIVE_SLOTS))
    else:
        cards.append(_card("04", "positioning",
            "Supine vs prone vs lateral vs sitting? Pins? Head turn and tilt? "
            "IONM electrodes placed before draping?",
            "Positioning errors cause nerve compression, air embolism, or inadequate exposure",
            slots=_OPERATIVE_SLOTS))

    # ── exposure ───────────────────────────────────────────────────────
    if _keyword_match(approach, "far-lateral", "far lateral",
                      "extreme lateral"):
        cards.append(_card("04", "exposure",
            "Far-lateral approach: midline incision curved laterally? "
            "C1 posterior arch, C2 lamina, and VA identification? "
            "Subperiosteal dissection of C1-2?",
            "VA must be mobilised or skeletonised before drilling; "
            "identify entry to dura and foramen magnum",
            slots=_OPERATIVE_SLOTS))
    elif profile == "spine":
        cards.append(_card("04", "exposure",
            "Confirm level with lateral or O-arm fluoroscopy. "
            "Subperiosteal exposure of target lamina, facet, and transverse process. "
            "Define lateral extent relative to VA.",
            "Wrong-level exposure is a never-event; adequate lateral exposure "
            "prevents incomplete decompression",
            slots=_OPERATIVE_SLOTS))
    elif _keyword_match(approach, "retrosigmoid"):
        cards.append(_card("04", "exposure",
            "Retrosigmoid craniotomy/craniectomy exposing sigmoid-transverse junction. "
            "C-shaped dural flap based on sigmoid. Early CSF release from cisterna magna.",
            "Adequate CPA exposure requires sigmoid skeletonisation; early CSF release "
            "relaxes cerebellum",
            slots=_OPERATIVE_SLOTS))
    else:
        cards.append(_card("04", "exposure",
            "Confirm craniotomy/craniectomy location. Expose dural entry point "
            "and define sinus/cortical vein relationship. CSF release plan if applicable.",
            "Adequate exposure with controlled dural opening avoids brain injury",
            slots=_OPERATIVE_SLOTS))

    # ── critical steps ─────────────────────────────────────────────────
    if _keyword_match(pathology, "schwannoma", "tumor"):
        cards.append(_card("04", "critical_steps",
            "(1) Identify proximal and distal normal nerve; "
            "(2) Stimulate to confirm non-eloquent fibers; "
            "(3) Internally debulk tumor; "
            "(4) Dissect capsule off nerve/root under stimulation; "
            "Planned extent of resection (GTR vs STR vs biopsy)?",
            "Tumor-nerve interface determines safe resection limits; "
            "internal debulking before capsular dissection protects neural structures",
            slots=_OPERATIVE_SLOTS))
    if profile == "spine" and _keyword_match(topic, "cord compression",
                                             "myelopathy"):
        cards.append(_card("04", "critical_steps",
            "Adequate decompression of spinal cord: laminectomy/laminoplasty extent, "
            "dentate ligament section if needed, tumor debulking order?",
            "Incomplete decompression is the most common cause of persistent myelopathy",
            slots=_OPERATIVE_SLOTS))
    if not cards or cards[-1].section_key != "critical_steps":
        cards.append(_card("04", "critical_steps",
            "Define stepwise surgical plan including approach, lesion access, "
            "resection/decompression sequence, and closure",
            "A rehearsed stepwise plan reduces intraoperative uncertainty "
            "and prevents skipped safety checks",
            slots=_OPERATIVE_SLOTS))

    # ── decision points ────────────────────────────────────────────────
    if profile == "spine" and _keyword_match(topic, "c1", "c2",
                                             "craniocervical"):
        cards.append(_card("04", "decision_points",
            "When to add fusion if instability is encountered or C1-2 joints "
            "are disrupted? C2 nerve root: sacrifice for exposure vs preserve?",
            "Craniocervical instability may only be apparent intraoperatively; "
            "C2 sacrifice causes occipital neuralgia but improves exposure",
            slots=_OPERATIVE_SLOTS))
    else:
        cards.append(_card("04", "decision_points",
            "When is neurological deficit or intraoperative change severe enough "
            "to stop or modify the surgical plan?",
            "Pre-committed decision boundaries prevent escalation-of-commitment",
            slots=_OPERATIVE_SLOTS))

    # ── stop points ────────────────────────────────────────────────────
    cards.append(_card("04", "stop_points",
        "When to abort: uncontrolled VA/carotid bleeding, sustained IONM signal "
        "loss, brainstem/cord edema, unstable vital signs, equipment failure?",
        "Agreed stopping rules prevent catastrophic outcomes from "
        "\"just a little more\" thinking",
        slots=_OPERATIVE_SLOTS))

    # ── closure / reconstruction ───────────────────────────────────────
    if profile == "spine":
        cards.append(_card("04", "closure_reconstruction",
            "Watertight dural closure (4-0 or 5-0 Prolene, running/locking)? "
            "Dural graft if needed? Fusion and instrumentation plan if instability? "
            "Layered muscle/fascia closure? Subfascial drain?",
            "CSF leak and wound infection are dominant spine surgery complications",
            slots=_OPERATIVE_SLOTS))
    else:
        cards.append(_card("04", "closure_reconstruction",
            "Watertight dural closure with graft if needed. Bone flap replacement "
            "and fixation. Layered galea/skin closure. Subgaleal drain?",
            "CSF leak, infection, and bone flap complications are the dominant "
            "preventable post-craniotomy morbidities",
            slots=_OPERATIVE_SLOTS))

    # ── monitoring ─────────────────────────────────────────────────────
    if profile == "spine":
        cards.append(_card("04", "monitoring",
            "SSEP, MEP, and EMG for relevant myotomes? "
            "For C1-2: upper/lower extremity SSEP/MEP; "
            "bulbocavernosus reflex if conus/cord risk?",
            "IONM signal loss is the earliest warning of cord/root injury",
            slots=_OPERATIVE_SLOTS))
    else:
        cards.append(_card("04", "monitoring",
            "SSEP, MEP, EEG, and cranial nerve EMG as appropriate to lesion location?",
            "IONM provides real-time warning of neurological injury",
            slots=_OPERATIVE_SLOTS))

    # ── equipment / adjuncts ───────────────────────────────────────────
    if profile == "spine":
        cards.append(_card("04", "equipment_adjuncts",
            "Operating microscope, IONM, high-speed drill, ultrasonic aspirator "
            "(CUSA), intraoperative CT/O-arm/navigation if instrumentation planned?",
            "Equipment availability must be confirmed before incision",
            slots=_OPERATIVE_SLOTS))
    else:
        cards.append(_card("04", "equipment_adjuncts",
            "Operating microscope, IONM, ultrasonic aspirator, "
            "neuronavigation, endoscope if indicated?",
            "Equipment checklist prevents intraoperative delays",
            slots=_OPERATIVE_SLOTS))

    # ── attending preferences ──────────────────────────────────────────
    cards.append(_card("04", "attending_preferences_questions",
        "Attending preferences: approach variant, extent of resection, "
        "dural closure technique, drain use, postop imaging timing, "
        "steroid/antibiotic protocol?",
        "Individual attending practice patterns drive key decisions; "
        "confirm before incision",
        slots=_OPERATIVE_SLOTS))

    return cards


def _generate_risk_questions(
    topic: str,
    procedure: str,
    pathology: str,
    anatomic_location: str,
    approach: str,
    profile: str,
) -> list[QuestionCard]:
    cards: list[QuestionCard] = []

    # ── likely complications ──────────────────────────────────────────
    if profile == "spine":
        cards.append(_card("05", "likely_complications",
            "CSF leak, wound infection, neurological deterioration "
            "(new/progressive radiculopathy or myelopathy), "
            "vertebral artery injury, instability, "
            "medical complications (DVT/PE, UTI, pneumonia)",
            "These are the dominant morbidity drivers; early detection "
            "protocols reduce severity",
            slots=_RISK_SLOTS))
    else:
        cards.append(_card("05", "likely_complications",
            "CSF leak, wound infection, new/progressive neurological deficit, "
            "seizure, DVT/PE, medical complications",
            "Expected complications should be explicitly monitored and communicated",
            slots=_RISK_SLOTS))

    # ── catastrophic complications ─────────────────────────────────────
    if profile == "spine" and _keyword_match(topic, "c1", "c2",
                                             "craniocervical"):
        cards.append(_card("05", "catastrophic_complications",
            "Vertebral artery injury → brainstem/cerebellar infarct or "
            "uncontrolled hemorrhage; spinal cord injury → quadriplegia; "
            "air embolism from exposed venous plexus at C1-2; "
            "craniocervical instability → brainstem compression",
            "Each requires an immediate pre-rehearsed intraoperative response; "
            "recognition-to-action window is measured in minutes",
            slots=_RISK_SLOTS))
    elif profile == "spine":
        cards.append(_card("05", "catastrophic_complications",
            "Spinal cord injury, vertebral artery injury, "
            "major vessel injury, tension pneumocephalus, anaphylaxis",
            "Immediate intraoperative recognition and response is critical",
            slots=_RISK_SLOTS))
    else:
        cards.append(_card("05", "catastrophic_complications",
            "Major arterial/venous injury → stroke/hemorrhage; "
            "brainstem injury; air embolism; tension pneumocephalus; "
            "malignant cerebral edema; anaphylaxis",
            "Each has a specific rescue sequence; room team must share triggers",
            slots=_RISK_SLOTS))

    # ── mitigation ─────────────────────────────────────────────────────
    if profile == "spine":
        cards.append(_card("05", "mitigation",
            "Preop CTA for VA anatomy, IONM throughout, watertight dural "
            "closure with graft if intradural, layered wound closure, "
            "early mobilisation, DVT prophylaxis, drain management protocol",
            "Systematic mitigation reduces the dominant complication rates",
            slots=_RISK_SLOTS))
    else:
        cards.append(_card("05", "mitigation",
            "Watertight dural closure, layered wound closure, "
            "DVT prophylaxis, seizure prophylaxis if indicated, "
            "early mobilisation, drain management",
            "Systematic closure and postop protocols reduce complication rates",
            slots=_RISK_SLOTS))

    # ── rescue triggers ────────────────────────────────────────────────
    if profile == "spine" and _keyword_match(topic, "c1", "c2"):
        cards.append(_card("05", "rescue_triggers",
            "VA injury: pack with muscle/surgicel, consider primary repair "
            "vs ligation vs endovascular sacrifice. "
            "IONM loss: warm irrigation, raise MAP, release retraction, "
            "consider wake-up test. "
            "Cord swelling: widen decompression, IV steroids per NASCIS. "
            "Air embolism: flood field, Trendelenburg, left lateral decubitus, "
            "aspirate CVP. "
            "Instability: occipitocervical fusion if C1-2 destabilised.",
            "Each rescue has a 30-60 second recognition-to-action window",
            slots=_RISK_SLOTS))
    else:
        cards.append(_card("05", "rescue_triggers",
            "Neurological deterioration: immediate imaging, consider "
            "re-exploration. Hemorrhage: return to OR, evacuation. "
            "CSF leak: lumbar drain, re-exploration if persistent. "
            "Infection: antibiotics, wound exploration, debridement. "
            "Seizure: acute management, CT, EEG, antiepileptic adjustment.",
            "Specific trigger thresholds must be agreed before sign-out",
            slots=_RISK_SLOTS))

    return cards


# ── public API ───────────────────────────────────────────────────────────────


def _extract_case_fields(topic: str) -> dict[str, str]:
    """Naively extract key case fields from the raw topic string."""
    return {
        "topic": topic,
        "procedure": topic,
        "pathology": topic,
        "anatomic_location": topic,
        "approach": topic,
        "profile": "",
    }


def build_generic_manifest(
    topic: str,
    procedure_family_id: str = "",
    profile: str = "",
) -> QuestionManifest:
    """Build a manifest using generic neurosurgical rules.

    This handles ANY neurosurgical case, not just pre-registered families.
    """
    fields = _extract_case_fields(topic)
    fields["profile"] = profile

    all_cards: list[QuestionCard] = []
    all_cards.extend(_generate_anatomy_questions(**fields))
    all_cards.extend(_generate_operative_questions(**fields))
    all_cards.extend(_generate_risk_questions(**fields))

    family_label = procedure_family_id or "generic"
    return QuestionManifest(procedure_family=family_label, cards=all_cards)


# ── VS / retrosigmoid vestibular schwannoma cards (specific templates) ───────

_VS_ANATOMY_CARDS: list[QuestionCard] = [
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="surgical_corridor",
        question="Confirm retrosigmoid craniotomy with CPA exposure",
        why_it_matters="Determines sigmoid/transverse sinus relationship, "
                       "cerebellar retraction, and IAC drilling angle",
        compiler_slot="Surgical Corridor",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="landmarks_in_order",
        question="Identify asterion, sigmoid-transverse junction, emissary vein, "
                "endolymphatic sac/operculum",
        why_it_matters="Landmarks define craniotomy limits and IAC trajectory; "
                       "anterior sigmoid or low tegmen changes the opening",
        compiler_slot="Landmarks In Order",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="neural_structures",
        question="Facial nerve (VII) course and displacement by tumor? "
                "Cochlear nerve (VIII) identified on imaging? Trigeminal (V) "
                "and lower CN (IX-XI) involvement?",
        why_it_matters="Facial nerve monitoring strategy, hearing-preservation "
                       "feasibility, and risk of postop deficits depend on "
                       "tumor-nerve interface",
        compiler_slot="Neural Structures",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="arteries_perforators_veins_sinuses",
        question="AICA loop and relationship to tumor capsule? PICA, SCA, "
                "and labyrinthine artery position? Sigmoid/transverse sinus "
                "dominance and patency? Superior petrosal vein?",
        why_it_matters="Vascular injury is the dominant cause of catastrophic "
                       "posterior fossa outcome; vein of Labbé/sinus sacrifice "
                       "threshold depends on venous drainage",
        compiler_slot="Arteries / Perforators / Veins / Sinuses",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="functional_structures",
        question="Hearing status (PTA, SDS, ABR if available)? "
                "Is hearing serviceable (AAO-HNS class A/B)? "
                "Brainstem compression and preop swallowing/airway status?",
        why_it_matters="Serviceable hearing drives retrosigmoid vs "
                       "translabyrinthine decision; brainstem compression "
                       "changes positioning, CSF release, and postop ICU plan",
        compiler_slot="Functional Structures",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="variants",
        question="High-riding jugular bulb? Anterior sigmoid sinus? "
                "Dehiscent facial nerve or fundal air cells? NF2 status?",
        why_it_matters="Variant anatomy can block IAC access, open mastoid "
                       "air cells, and alter the safe drilling corridor",
        compiler_slot="Variants",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="no_fly_zones",
        question="Define dissection limits: fundal IAC beyond transverse crest? "
                "Adherent capsule at brainstem/root entry zone? Dominant "
                "draining veins that must be preserved?",
        why_it_matters="Pre-planned residual tumor boundaries avoid brainstem "
                       "injury, facial nerve sacrifice, and venous infarct",
        compiler_slot="No-Fly Zones",
    ),
]


_VS_OPERATIVE_CARDS: list[QuestionCard] = [
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="positioning",
        question="Supine with shoulder roll, head turned 90° contralateral, "
                "pins, and slight vertex-down tilt? IONM setup complete?",
        why_it_matters="Suboptimal head turn limits CPA exposure; IONM "
                       "placement before draping enables early facial nerve mapping",
        compiler_slot="Positioning",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="exposure",
        question="Retrosigmoid craniotomy vs craniectomy? Drill to expose "
                "sigmoid-transverse junction; open dura as C-shaped flap "
                "based on sigmoid; CSF release from cisterna magna?",
        why_it_matters="Adequate exposure requires skeletonizing the sigmoid "
                       "sinus; early CSF release relaxes cerebellum",
        compiler_slot="Exposure",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="critical_steps",
        question="(1) IAC drilling after dura open — identify fundus and "
                "transverse/singular crest; (2) debulk tumor internally; "
                "(3) dissect capsule from VII/VIII under stimulation; "
                "(4) remove IAC component last? Planned extent of resection "
                "(GTR vs NTR vs STR)?",
        why_it_matters="IAC opening technique and facial nerve stimulation "
                       "thresholds define the safety envelope",
        compiler_slot="Critical Steps",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="decision_points",
        question="When to stop: Stimulation <0.05 mA at brainstem? "
                "Bradycardia from trigemino-cardiac reflex? "
                "Adherent capsule at root entry zone?",
        why_it_matters="Pre-committed decision boundaries prevent "
                       "escalation-of-commitment and nerve or brainstem injury",
        compiler_slot="Decision Points",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="monitoring",
        question="Facial nerve EMG (4 channels, plus free-run)? "
                "BAEP/cochlear nerve monitoring? SSEP? "
                "Trigeminal motor if large/tentorial tumor?",
        why_it_matters="IONM plan should match tumor location and hearing goal",
        compiler_slot="Monitoring",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="equipment_adjuncts",
        question="Facial nerve stimulator, ultrasonic aspirator, endoscope "
                "(30°/70°) for IAC fundus, fibrin sealant, dural graft?",
        why_it_matters="Endoscope identifies residual fundal tumor; fibrin "
                       "sealant reduces CSF leak risk",
        compiler_slot="Equipment / Adjuncts",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="attending_preferences_questions",
        question="Attending preference: Translabyrinthine vs retrosigmoid for "
                "this tumor size/hearing? Preferred IAC closure (muscle plug, "
                "bone wax, fascia)? Postoperative lumbar drain threshold?",
        why_it_matters="Individual attending practice patterns drive key "
                       "intraoperative decisions; confirm before incision",
        compiler_slot="Attending Preferences / Questions",
    ),
]


_VS_RISK_CARDS: list[QuestionCard] = [
    QuestionCard(
        target_file="05-risk-and-rescue.md",
        section_key="likely_complications",
        question="CSF leak (incisional, rhinorrhea), facial nerve paresis "
                "(temporary vs permanent), hearing loss, headache, "
                "cerebellar edema, meningitis, pseudomeningocele",
        why_it_matters="These are the dominant morbidity drivers; preop "
                       "counseling and early detection protocols reduce severity",
        compiler_slot="Likely Complications",
    ),
    QuestionCard(
        target_file="05-risk-and-rescue.md",
        section_key="catastrophic_complications",
        question="AICA/PICA injury → brainstem/labyrinthine infarct, "
                "venous sinus injury → air embolism/venous infarct, "
                "tension pneumocephalus, uncal/herniation from cerebellar "
                "swelling, CN VII permanent paralysis, death",
        why_it_matters="Immediate intraoperative recognition and response "
                       "windows are measured in minutes",
        compiler_slot="Catastrophic Complications",
    ),
    QuestionCard(
        target_file="05-risk-and-rescue.md",
        section_key="mitigation",
        question="Watertight dural closure with graft, muscle/fat plug for IAC, "
                "fibrin sealant, layered closure, mastoid air cell waxing; "
                "early extubation with neuro exam; CSF diversion threshold",
        why_it_matters="Systematic closure technique is the single strongest "
                       "defense against CSF leak and infection",
        compiler_slot="Mitigation",
    ),
    QuestionCard(
        target_file="05-risk-and-rescue.md",
        section_key="rescue_triggers",
        question="Sudden bradycardia/hypotension → trigemino-cardiac reflex, "
                "release traction; hairline fracture extending to IAM → stop "
                "drilling, assess; new VII activity drop → stop dissection, "
                "warm irrigation, papaverine; air embolism → flood field, "
                "Trendelenburg, left lateral decubitus, aspirate CVP",
        why_it_matters="Each rescue has a 30-60 second recognition-to-action "
                       "window; the room team needs shared triggers",
        compiler_slot="Rescue Triggers",
    ),
]


# ── spine schwannoma / C1-2 far-lateral cards ────────────────────────────────

_SPINE_SCHWANNOMA_ANATOMY: list[QuestionCard] = [
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="surgical_corridor",
        question="Confirm C1-2 level, laterality, and far-lateral approach corridor. "
                "Preop CTA/DSA for vertebral artery (V3 segment) course?",
        why_it_matters="VA at C1-2 is the dominant catastrophic risk; wrong-level surgery "
                       "is a never-event at the craniocervical junction",
        compiler_slot="Surgical Corridor",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="landmarks_in_order",
        question="Identify C1 posterior arch, C2 lamina, VA groove on C1, "
                "atlanto-occipital membrane, C2 ganglion, vertebral artery loop?",
        why_it_matters="These landmarks define the safe drilling corridor and "
                       "VA mobilisation limits for far-lateral exposure",
        compiler_slot="Landmarks In Order",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="neural_structures",
        question="C2 nerve root and dorsal root ganglion relationship to tumor? "
                "Spinal cord compression severity and level? "
                "Accessory nerve (CN XI) at craniocervical junction?",
        why_it_matters="C2 root sacrifice vs preservation decision affects "
                       "occipital neuralgia risk; cord compression drives "
                       "urgency and IONM plan",
        compiler_slot="Neural Structures",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="arteries_perforators_veins_sinuses",
        question="VA (V3 segment) course relative to C1-2 and tumor? "
                "Dominant vs non-dominant VA? Contralateral VA patency? "
                "Epidural venous plexus at C1-2?",
        why_it_matters="VA injury at C1-2 causes brainstem/cerebellar infarct; "
                       "contralateral VA patency determines sacrifice vs repair. "
                       "Venous plexus is a source of air embolism.",
        compiler_slot="Arteries / Perforators / Veins / Sinuses",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="functional_structures",
        question="Myelopathy signs/symptoms? Gait, hand function, bowel/bladder? "
                "Preop Nurick grade or mJOA score? "
                "Occipital neuralgia from C2 involvement?",
        why_it_matters="Myelopathy grade drives surgical timing, positioning "
                       "precautions, and postop rehab expectations",
        compiler_slot="Functional Structures",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="variants",
        question="Anomalous VA course: persistent first intersegmental artery? "
                "Fenestrated VA? Extradural PICA origin? "
                "Arcuate foramen (ponticulus posticus)?",
        why_it_matters="VA anomaly at C1-2 changes safe screw trajectory, "
                       "drilling limits, and mobilisation strategy",
        compiler_slot="Variants",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="no_fly_zones",
        question="No-fly zones: VA at C1-2 (absolute), contralateral VA patency "
                "margin, spinal cord at craniocervical junction, "
                "C2 ganglion if preservation planned",
        why_it_matters="Pre-planned boundaries prevent VA injury, quadriplegia, "
                       "and C2 neuralgia",
        compiler_slot="No-Fly Zones",
    ),
]

_SPINE_SCHWANNOMA_OPERATIVE: list[QuestionCard] = [
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="positioning",
        question="Prone on Jackson table, Mayfield pins, neutral head alignment "
                "with slight flexion, shoulders taped? "
                "Confirm pre-positioning neuro exam and IONM baselines "
                "(SSEP/MEP upper and lower extremities)?",
        why_it_matters="Head malposition in unstable C1-2 lesions can compress "
                       "cord during positioning; IONM baselines must be "
                       "obtained before final position",
        compiler_slot="Positioning",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="exposure",
        question="Midline incision from inion to C3-4, curved laterally toward "
                "mastoid? Muscle dissection: splenius capitis, semispinalis "
                "capitis, inferior oblique? Subperiosteal exposure of C1 "
                "posterior arch and C2 lamina? Identify VA between C1-C2?",
        why_it_matters="VA must be identified and mobilised before drilling; "
                       "subperiosteal dissection reduces bleeding and protects VA",
        compiler_slot="Exposure",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="critical_steps",
        question="(1) C1 hemilaminectomy ± partial condylectomy; "
                "(2) open dura in curvilinear fashion; "
                "(3) identify proximal/distal nerve root; "
                "(4) stimulate to confirm non-eloquent fibers; "
                "(5) internally debulk tumor with CUSA; "
                "(6) dissect capsule off cord/root under stimulation. "
                "Planned extent of resection (GTR vs STR)?",
        why_it_matters="Condyle drilling extent determines VA exposure and "
                       "tumor access; internal debulking before capsular "
                       "dissection protects cord and nerve root",
        compiler_slot="Critical Steps",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="decision_points",
        question="C2 nerve root: sacrifice for exposure (if tumor involves "
                "ganglion) vs preservation? When to add occipitocervical "
                "fusion if C1-2 instability is encountered?",
        why_it_matters="C2 sacrifice causes occipital neuralgia in ~60% but "
                       "improves tumor access; instability may only be "
                       "apparent intraoperatively after bone removal",
        compiler_slot="Decision Points",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="stop_points",
        question="Abort if: uncontrolled VA bleeding, sustained IONM signal "
                "loss (>50% MEP amplitude drop or SSEP latency increase "
                ">10%), new quadriparesis on wake-up test, "
                "air embolism with cardiovascular collapse, "
                "equipment failure preventing safe drilling.",
        why_it_matters="C1-2 surgery has narrow rescue windows; pre-agreed "
                       "stopping rules prevent catastrophic cord/VA injury",
        compiler_slot="Stop Points",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="closure_reconstruction",
        question="Watertight dural closure (4-0 or 5-0 Prolene, running)? "
                "Dural graft (pericranium/fascia lata) if primary closure "
                "not possible? Layered muscle/fascia closure? "
                "Subfascial drain? Fusion construct if C1-2 destabilised?",
        why_it_matters="CSF leak at C1-2 is difficult to manage postoperatively; "
                       "watertight closure and drain management are critical",
        compiler_slot="Closure / Reconstruction",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="monitoring",
        question="SSEP: median and posterior tibial nerves. "
                "MEP: deltoid, biceps, APB (C5-T1) for upper; "
                "quadriceps, tibialis anterior, abductor hallucis (L2-S1) "
                "for lower. Bulbocavernosus reflex if conus at risk? "
                "Free-run EMG for C2 and accessory nerve?",
        why_it_matters="IONM signal loss is earliest warning of cord/root "
                       "injury; specific myotomes must be selected based on "
                       "tumor level (C1-2 → upper cervical myotomes + long tracts)",
        compiler_slot="Monitoring",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="equipment_adjuncts",
        question="Operating microscope, IONM (MEP/SSEP/EMG), high-speed drill "
                "with matchstick/diamond burrs, CUSA, intraoperative "
                "CT/O-arm if instrumentation planned, "
                "Doppler for VA patency, nerve stimulator?",
        why_it_matters="Equipment availability confirmed before incision; "
                       "Doppler assesses VA flow after mobilisation",
        compiler_slot="Equipment / Adjuncts",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="attending_preferences_questions",
        question="Attending: far-lateral vs extreme-lateral variant? "
                "Condyle drilling extent? C2 root sacrifice threshold? "
                "Fusion criteria? Dural graft material? "
                "Postop collar vs halo? Drain removal timing? "
                "Steroid protocol?",
        why_it_matters="Individual attending practice patterns drive key "
                       "decisions; confirm before incision",
        compiler_slot="Attending Preferences / Questions",
    ),
]

_SPINE_SCHWANNOMA_RISK: list[QuestionCard] = [
    QuestionCard(
        target_file="05-risk-and-rescue.md",
        section_key="likely_complications",
        question="CSF leak/pseudomeningocele, wound infection, "
                "C2 neuralgia/occipital numbness, "
                "new/progressive myelopathy or radiculopathy, "
                "vertebral artery injury (dissection, thrombosis, laceration), "
                "craniocervical instability, DVT/PE, UTI, pneumonia",
        why_it_matters="Dominant drivers of morbidity after C1-2 tumor surgery; "
                       "early detection protocols and patient counselling "
                       "reduce severity and litigation risk",
        compiler_slot="Likely Complications",
    ),
    QuestionCard(
        target_file="05-risk-and-rescue.md",
        section_key="catastrophic_complications",
        question="VA injury → brainstem/cerebellar/posterior circulation "
                "infarct or uncontrolled hemorrhage; "
                "spinal cord injury → quadriplegia; "
                "air embolism from exposed C1-2 venous plexus; "
                "craniocervical instability → brainstem compression; "
                "death",
        why_it_matters="Each has a pre-rehearsed intraoperative response; "
                       "recognition-to-action window is measured in minutes",
        compiler_slot="Catastrophic Complications",
    ),
    QuestionCard(
        target_file="05-risk-and-rescue.md",
        section_key="mitigation",
        question="Preop CTA/DSA for VA anatomy (both sides); "
                "IONM throughout with baselines before positioning; "
                "watertight dural closure with graft if intradural; "
                "Valsalva to 30 cmH2O after closure; "
                "layered muscle closure; postop collar if no fusion; "
                "early mobilisation with spine precautions; "
                "DVT prophylaxis; drain on gravity for 24-48h",
        why_it_matters="Systematic mitigation reduces the dominant complication "
                       "rates by 50-70% in published series",
        compiler_slot="Mitigation",
    ),
    QuestionCard(
        target_file="05-risk-and-rescue.md",
        section_key="rescue_triggers",
        question="VA injury: proximal/distal control, pack with muscle/Surgicel, "
                "primary repair (7-0 Prolene) if focal, ligation if "
                "contralateral VA patent, endovascular sacrifice as backup. "
                "IONM loss: warm irrigation, raise MAP >90, release retraction, "
                "consider intraop wake-up test. "
                "Cord swelling: widen decompression, IV methylprednisolone "
                "(per NASCIS II if within 8h). "
                "Air embolism: flood field with saline, Trendelenburg, "
                "left lateral decubitus, aspirate CVP line. "
                "Instability: occipitocervical fusion (C0-C2 or C0-C4).",
        why_it_matters="Each rescue has a 30-60 second window; "
                       "room team must share triggers before incision",
        compiler_slot="Rescue Triggers",
    ),
]


# ── awake craniotomy / supratentorial tumor cards ────────────────────────────

_AWAKE_CRANIOTOMY_ANATOMY: list[QuestionCard] = [
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="surgical_corridor",
        question="Confirm craniotomy location relative to motor strip "
                "(precentral gyrus) and sensory cortex (postcentral gyrus). "
                "Preop fMRI and DTI tractography for corticospinal tract? "
                "Neuronavigation registration planned?",
        why_it_matters="Precise craniotomy placement over eloquent cortex "
                       "enables maximal mapping coverage with minimal exposure",
        compiler_slot="Surgical Corridor",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="landmarks_in_order",
        question="Identify central sulcus on sagittal MRI (pars marginalis, "
                "hand knob sign). Coronal suture and motor strip relationship? "
                "SSEP phase reversal planned for intraop confirmation?",
        why_it_matters="Central sulcus must be confirmed intraoperatively "
                       "before cortical stimulation begins; SSEP phase "
                       "reversal is the gold standard",
        compiler_slot="Landmarks In Order",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="neural_structures",
        question="Which eloquent regions are adjacent? Motor: precentral gyrus "
                "(face, hand, arm, leg homunculus). Language: Broca area "
                "(pars opercularis/triangularis, dominant hemisphere), "
                "Wernicke area (superior temporal gyrus). "
                "Somatosensory: postcentral gyrus. "
                "Arcuate fasciculus on DTI?",
        why_it_matters="Mapping strategy (motor, language, or both) and "
                       "awake-vs-asleep decision depend on which eloquent "
                       "regions are at risk",
        compiler_slot="Neural Structures",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="arteries_perforators_veins_sinuses",
        question="Superior sagittal sinus relationship? Vein of Trolard and "
                "other dominant cortical draining veins? "
                "Perirolandic arterial supply (MCA branches, ACA)?",
        why_it_matters="Venous sacrifice → venous infarct/hemorrhage; "
                       "arterial injury → motor/sensory stroke. "
                       "Preop venography/MRV defines safe dural opening",
        compiler_slot="Arteries / Perforators / Veins / Sinuses",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="functional_structures",
        question="Preop neurological exam: motor (MRC grades for face, arm, "
                "hand, leg), sensory (light touch, proprioception), "
                "language (naming, repetition, comprehension, fluency). "
                "Baseline KPS? Seizure history and AED regimen?",
        why_it_matters="Baseline function determines surgical risk tolerance; "
                       "intraoperative language testing requires documented "
                       "preop language status for comparison",
        compiler_slot="Functional Structures",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="variants",
        question="Right-hemisphere language dominance (crossed dominance)? "
                "Venous drainage variants (hypoplastic SSS, dominant vein "
                "of Labbé draining parietal region)? "
                "Prior surgery/scarring affecting mapping?",
        why_it_matters="Crossed dominance changes laterality of language "
                       "mapping; venous variants restrict safe dural opening",
        compiler_slot="Variants",
    ),
    QuestionCard(
        target_file="03-anatomy-at-risk.md",
        section_key="no_fly_zones",
        question="No-fly zones: motor strip (precentral gyrus), "
                "language areas (Broca/Wernicke, arcuate fasciculus), "
                "dominant cortical draining veins, SSS, "
                "primary somatosensory cortex if patient preference",
        why_it_matters="Pre-planned boundaries prevent permanent hemiparesis, "
                       "aphasia, or venous infarct",
        compiler_slot="No-Fly Zones",
    ),
]

_AWAKE_CRANIOTOMY_OPERATIVE: list[QuestionCard] = [
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="positioning",
        question="Lateral or semi-sitting position? Head in Mayfield pins, "
                "turned to expose parietal convexity? "
                "Patient comfort for awake phase (padding, blanket, "
                "clear line of sight to neuropsychologist)? "
                "IONM electrodes (SSEP, ECOG strip) placed before draping?",
        why_it_matters="Patient must remain cooperative for 1-3h of awake "
                       "mapping; positioning affects airway, comfort, "
                       "and surgical access",
        compiler_slot="Positioning",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="exposure",
        question="Craniotomy centered over lesion + 2-3 cm margin for mapping. "
                "Expose dural entry with care to preserve cortical veins. "
                "Dural opening based on preop venography. "
                "ECOG strip placement over perilesional cortex before mapping.",
        why_it_matters="Adequate exposure for mapping (motor + language "
                       "if indicated) determines resection safety margin",
        compiler_slot="Exposure",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="critical_steps",
        question="(1) Asleep-awake-asleep protocol vs conscious sedation; "
                "(2) SSEP phase reversal to confirm central sulcus; "
                "(3) Cortical stimulation mapping: biphasic, 60Hz, 1ms pulse "
                "width, starting at 2mA, increase to after-discharge threshold "
                "or 15mA max; "
                "(4) Motor mapping: identify face/hand/arm/leg; "
                "(5) Language mapping: object naming, word generation, "
                "comprehension (Token Test) — continue throughout resection; "
                "(6) Subcortical mapping during deep resection; "
                "(7) EOR goal: GTR if safe margin ≥1cm from eloquent sites, "
                "otherwise STR with planned residual at functional boundary.",
        why_it_matters="Systematic mapping protocol defines safe resection "
                       "limits; subcortical stimulation identifies descending "
                       "motor fibres (1-2mA threshold at 1cm from CST)",
        compiler_slot="Critical Steps",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="decision_points",
        question="Stop resection when: positive motor response at ≤5mA "
                "(CST within 1cm), speech arrest or anomia during language "
                "testing, after-discharges on ECOG without clinical seizure, "
                "patient fatigue or loss of cooperation.",
        why_it_matters="Intraoperative thresholds define functional boundary; "
                       "pushing past them causes permanent deficit",
        compiler_slot="Decision Points",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="stop_points",
        question="Abort if: intraoperative seizure not terminated by cold "
                "saline within 30s, patient cannot complete language testing, "
                "air embolism with cardiovascular instability, "
                "sustained hypertension/bleeding, loss of airway during awake phase.",
        why_it_matters="Awake craniotomy has unique abort criteria — seizure "
                       "and patient intolerance are more common than "
                       "uncontrolled bleeding",
        compiler_slot="Stop Points",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="closure_reconstruction",
        question="Watertight dural closure (4-0 Neurolon, running). "
                "Bone flap replacement with titanium plates. "
                "Galea and skin closure. Subgaleal drain?",
        why_it_matters="CSF leak and bone flap infection are preventable "
                       "closure-related morbidities",
        compiler_slot="Closure / Reconstruction",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="monitoring",
        question="SSEP (median nerve, phase reversal for central sulcus). "
                "ECOG strip for after-discharge detection. "
                "Cortical and subcortical bipolar stimulator. "
                "Continuous neurological assessment by neuropsychologist "
                "(language, motor) during resection.",
        why_it_matters="Multimodal monitoring is essential — ECOG detects "
                       "subclinical seizure, cortical stimulation maps "
                       "function, clinical testing validates in real time",
        compiler_slot="Monitoring",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="equipment_adjuncts",
        question="Neuronavigation (co-registered with fMRI/DTI), "
                "bipolar cortical stimulator (Ojemann or similar), "
                "ECOG strip and recording system, CUSA, "
                "operating microscope, 5-ALA if high-grade glioma?",
        why_it_matters="Navigation and stimulation are mandatory for awake "
                       "mapping; 5-ALA improves EOR in high-grade gliomas",
        compiler_slot="Equipment / Adjuncts",
    ),
    QuestionCard(
        target_file="04-operative-plan.md",
        section_key="attending_preferences_questions",
        question="Attending: asleep-awake-asleep vs conscious sedation? "
                "Stimulation parameters (biphasic vs monopolar)? "
                "Language testing protocol? "
                "5-ALA use? EOR goal for this lesion? Steroid and AED protocol? "
                "Postop imaging (MRI within 48h vs immediate CT)?",
        why_it_matters="Awake craniotomy has significant practice variation; "
                       "confirm attending preferences before the case",
        compiler_slot="Attending Preferences / Questions",
    ),
]

_AWAKE_CRANIOTOMY_RISK: list[QuestionCard] = [
    QuestionCard(
        target_file="05-risk-and-rescue.md",
        section_key="likely_complications",
        question="Intraoperative seizure (5-20%), transient neurological "
                "deficit (10-30%, resolves within days-weeks), "
                "permanent motor/language deficit (2-5%), "
                "CSF leak, wound infection, "
                "air embolism, DVT/PE, "
                "patient intolerance of awake phase requiring conversion to GA",
        why_it_matters="Preop counselling must cover expected vs unexpected "
                       "deficits and conversion risk",
        compiler_slot="Likely Complications",
    ),
    QuestionCard(
        target_file="05-risk-and-rescue.md",
        section_key="catastrophic_complications",
        question="Intraoperative seizure → status epilepticus; "
                "air embolism → cardiovascular collapse; "
                "intracerebral hemorrhage → mass effect/herniation; "
                "malignant cerebral edema; "
                "major arterial/venous injury → stroke; "
                "death",
        why_it_matters="Immediate recognition and pre-rehearsed response "
                       "sequence required for each",
        compiler_slot="Catastrophic Complications",
    ),
    QuestionCard(
        target_file="05-risk-and-rescue.md",
        section_key="mitigation",
        question="Preop fMRI/DTI for planning; AED load pre-incision; "
                "ECOG for seizure detection; cold saline immediately "
                "available on field; avoid hyperventilation (reduces "
                "seizure threshold); MAP 70-90 during resection; "
                "watertight dural closure; layered wound closure; "
                "postop dexamethasone taper; AED taper if no seizures",
        why_it_matters="Seizure and deficit mitigation are the dominant "
                       "safety concerns in awake craniotomy",
        compiler_slot="Mitigation",
    ),
    QuestionCard(
        target_file="05-risk-and-rescue.md",
        section_key="rescue_triggers",
        question="Seizure: cold saline irrigation on cortex immediately; "
                "if >30s, IV propofol bolus (20-50mg) or midazolam (1-2mg). "
                "Air embolism: flood field, Trendelenburg, left lateral "
                "decubitus, aspirate CVP, 100% FiO2. "
                "Hemorrhage: control bleeding, raise MAP if hypotensive, "
                "convert to GA, consider emergent CT. "
                "Malignant edema: hyperosmolar therapy (mannitol/hypertonic "
                "saline), consider decompressive craniectomy. "
                "New dense deficit: stop resection, consider intraop CT/MRI "
                "if available, steroids, MAP augmentation.",
        why_it_matters="Awake patients decompensate faster; pre-planned "
                       "triggers prevent delayed recognition",
        compiler_slot="Rescue Triggers",
    ),
]


# ── procedure-family registry ────────────────────────────────────────────────


_FAMILY_MANIFESTS: dict[str, dict[str, list[QuestionCard]]] = {
    "vestibular_schwannoma_retrosigmoid": {
        "anatomy_at_risk": _VS_ANATOMY_CARDS,
        "operative_plan": _VS_OPERATIVE_CARDS,
        "risk_and_rescue": _VS_RISK_CARDS,
    },
    "spine_schwannoma_c1c2": {
        "anatomy_at_risk": _SPINE_SCHWANNOMA_ANATOMY,
        "operative_plan": _SPINE_SCHWANNOMA_OPERATIVE,
        "risk_and_rescue": _SPINE_SCHWANNOMA_RISK,
    },
    "awake_craniotomy_tumor": {
        "anatomy_at_risk": _AWAKE_CRANIOTOMY_ANATOMY,
        "operative_plan": _AWAKE_CRANIOTOMY_OPERATIVE,
        "risk_and_rescue": _AWAKE_CRANIOTOMY_RISK,
    },
    # Thrombectomy is handled by context-aware family defaults in schema.py;
    # Explorer does not inject here.
}

# Map the builder's procedure-family IDs to manifest keys.
_FAMILY_ID_TO_MANIFEST_KEY: dict[str, str] = {
    "vestibular_schwannoma": "vestibular_schwannoma_retrosigmoid",
}

# Broad-profile fallbacks: when the parser can't pin to a specific procedure
# family but the raw input contains keywords, route to a manifest.
_VS_TOPIC_SIGNALS: tuple[str, ...] = (
    "vestibular schwannoma", "acoustic neuroma", "cpa tumor",
    "cerebellopontine angle", "retrosigmoid", "translabyrinthine",
)

_SPINE_SCHWANNOMA_SIGNALS: tuple[str, ...] = (
    "spinal schwannoma", "far-lateral schwannoma",
    "craniocervical schwannoma", "cervical schwannoma",
    "schwannoma with cord compression",
    "schwannoma far lateral",
)
# NOTE: "c1-2" and "c1" are deliberately excluded — they would
# fire on Chiari decompression queries which also mention C1/C2
# laminectomy but are not tumor cases.

_AWAKE_CRANIOTOMY_SIGNALS: tuple[str, ...] = (
    "awake craniotomy", "awake surgery", "motor mapping",
    "language mapping", "eloquent glioma", "eloquent glioblastoma",
    "awake mapping",
)


def _detect_manifest_key(procedure_family_id: str, topic: str) -> str | None:
    """Resolve a manifest key from the procedure-family ID or raw topic."""
    key = _FAMILY_ID_TO_MANIFEST_KEY.get(procedure_family_id)
    if key is not None:
        return key
    topic_lower = topic.lower()

    # Check specific families in priority order
    for signal in _VS_TOPIC_SIGNALS:
        if signal in topic_lower:
            return "vestibular_schwannoma_retrosigmoid"
    for signal in _SPINE_SCHWANNOMA_SIGNALS:
        if signal in topic_lower:
            return "spine_schwannoma_c1c2"
    for signal in _AWAKE_CRANIOTOMY_SIGNALS:
        if signal in topic_lower:
            return "awake_craniotomy_tumor"

    return None


def _merge_cards(
    primary: list[QuestionCard],
    secondary: list[QuestionCard],
) -> list[QuestionCard]:
    """Merge two card lists, keeping primary for overlapping section_keys.

    If both sources have cards for the same ``(target_file, section_key)``,
    prefer *primary* (hand-written templates).  Secondary cards fill gaps.
    Deduplicates by question text similarity (>70% word overlap).
    """
    # Index primary cards by (target_file, section_key)
    primary_keys: set[tuple[str, str]] = set()
    for card in primary:
        primary_keys.add((card.target_file, card.section_key))

    merged = list(primary)

    for card in secondary:
        key = (card.target_file, card.section_key)
        if key in primary_keys:
            continue  # primary already covers this slot

        # Check for near-duplicate questions
        card_words = set(card.question.lower().split())
        is_dup = False
        for existing in merged:
            exist_words = set(existing.question.lower().split())
            if not card_words or not exist_words:
                continue
            overlap = len(card_words & exist_words) / min(len(card_words), len(exist_words))
            if overlap > 0.7:
                is_dup = True
                break
        if not is_dup:
            merged.append(card)

    return merged


def build_question_manifest(
    procedure_family_id: str,
    topic: str,
    profile: str = "",
) -> QuestionManifest | None:
    """Build a deterministic question manifest for a procedure family.

    Resolution order (MERGE, not replace):
    1. Hand-written templates → authoritative for technique/approach sections
    2. PAPERS Knowledge Graph → fills gaps with evidence-backed facts
    3. Generic rule-based → covers remaining empty sections

    Returns ``None`` only when no profile can be determined at all.
    """

    # Import KG adapter (best-effort)
    try:
        from caseprep.explorer.kg_adapter import build_kg_manifest
    except ImportError:
        build_kg_manifest = None  # type: ignore[assignment]

    # ── 1. Collect hand-written template cards (primary) ──────────
    manifest_key = _detect_manifest_key(procedure_family_id, topic)
    template_cards: list[QuestionCard] = []
    if manifest_key is not None:
        section_cards = _FAMILY_MANIFESTS.get(manifest_key)
        if section_cards is not None:
            for cards in section_cards.values():
                template_cards.extend(cards)

    # ── 2. Collect KG cards (secondary) ────────────────────────────
    kg_cards: list[QuestionCard] = []
    if build_kg_manifest is not None:
        kg_manifest = build_kg_manifest(
            topic,
            procedure_family_id=procedure_family_id,
        )
        if kg_manifest is not None:
            kg_cards = list(kg_manifest.cards)

    # ── 3. Collect generic cards (tertiary) ────────────────────────
    generic_cards: list[QuestionCard] = []
    if profile:
        generic_manifest = build_generic_manifest(
            topic,
            procedure_family_id=procedure_family_id,
            profile=profile,
        )
        if generic_manifest is not None:
            generic_cards = list(generic_manifest.cards)

    # ── 4. Merge: template > KG > generic ──────────────────────────
    all_cards = _merge_cards(template_cards, kg_cards)
    all_cards = _merge_cards(all_cards, generic_cards)

    if not all_cards:
        return None

    family_label = manifest_key or procedure_family_id or "merged"
    return QuestionManifest(procedure_family=family_label, cards=all_cards)


def inject_manifest_into_schema(
    schema: dict[str, Any],
    manifest: QuestionManifest,
) -> None:
    """Mutate *schema* in place: replace empty section lists with Explorer
    question cards.  Sections that already have content (e.g. from family
    defaults) are left untouched."""
    # Build a lookup: (section_name, section_key) → list of rendered cards
    injection_map: dict[str, dict[str, list[str]]] = {}
    for card in manifest.cards:
        # Map target_file back to schema section name
        section_map: dict[str, str] = {
            "03-anatomy-at-risk.md": "anatomy_at_risk",
            "04-operative-plan.md": "operative_plan",
            "05-risk-and-rescue.md": "risk_and_rescue",
        }
        section_name = section_map.get(card.target_file)
        if section_name is None:
            continue
        injection_map.setdefault(section_name, {}).setdefault(
            card.section_key, []
        ).append(card.render_card())

    for section_name, keys in injection_map.items():
        case_section = schema["case"].get(section_name)
        if not isinstance(case_section, dict):
            continue
        for key, card_strings in keys.items():
            existing = case_section.get(key)
            if not existing:
                case_section[key] = card_strings
