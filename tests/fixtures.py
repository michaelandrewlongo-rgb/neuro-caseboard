"""Multi-subspecialty fixtures that reproduce all nine reviewed PDF defects.

Each fixture is a real ``caseprep`` ``AuditedManifest`` plus the per-card evidence
(``card_evidence``) and page text needed to exercise figure linkage / caption
completion. The four topics span distinct neurosurgical subspecialties so the tests
prove no fix is topic-coupled:

    spine   -> C5-6 corpectomy            (the reviewed artifact)
    cpa     -> left vestibular schwannoma (skull base)
    awake   -> awake left-temporal glioma (functional / tumor)
    carotid -> right carotid endarterectomy (vascular)

Defects deliberately planted in every fixture:
  #1 a card whose text contains non-latin glyphs (>=, ->, micro) that broke the
     latin-1 exporter
  #2/#3 a mix of audit_status values so the evidence summary has real counts (and no
     confidence axis exists to contradict it)
  #6 a compound "monitoring" card with several '?'-separated questions
  #7 a supported card with a figure whose caption is truncated to its first line
  #8 off_target + no_evidence cards that must surface in a real appendix
  #9 a closure phrase repeated near-verbatim across the Operative and Risk sections
"""

from __future__ import annotations

from dataclasses import dataclass

from caseprep.audit.card_auditor import AuditedManifest, AuditedCard
from caseprep.core.contracts import EvidenceRecord

ANATOMY = "03-anatomy-at-risk.md"
OPERATIVE = "04-operative-plan.md"
RISK = "05-risk-and-rescue.md"


@dataclass
class Fixture:
    topic: str
    manifest: AuditedManifest
    evidence: list  # flat list[EvidenceRecord]
    card_evidence: dict  # card.question -> list[EvidenceRecord]
    page_texts: dict  # figure_path -> full page text (for caption completion)


# Per-topic content. Each value drives one fixture. The clinical wording differs by
# subspecialty on purpose; the planted defects are structurally identical.
_TOPICS = {
    "spine": {
        "title": "C5-6 corpectomy",
        "anatomy_supported": (
            "Confirm vertebral artery course and the corpectomy trough width relative "
            "to the uncovertebral joints (target margin >= 5 mm, drill angle -> medial)",
            "VA injury and over-lateral troughing are the dominant catastrophic risks",
        ),
        "monitoring_compound": (
            "SSEP and MEP for upper and lower extremities? "
            "Free-run and triggered EMG for C5-C6 myotomes? "
            "Baseline signals before final positioning?",
            "IONM signal loss is the earliest warning of cord or root injury",
        ),
        "closure_phrase": (
            "Watertight dural closure if durotomy occurs; anterior plate and cage "
            "reconstruction; layered closure over a subfascial drain",
            "CSF leak, construct failure and wound breakdown drive reoperation",
        ),
        "figure_caption_first": "Figure 69-1. Anterior cervical construct",
        "figure_caption_full": (
            "Figure 69-1. Anterior cervical construct spanning the corpectomy defect "
            "from C4 to C6 with an interbody cage and anterior plate fixation."
        ),
        "citation": "Benzel Spine, p.592",
        "off_target": (
            "Lumbar interbody fusion cage subsidence rates",
            "Retrieved evidence is lumbar, not cervical",
        ),
        "no_evidence": (
            "Optimal rhBMP-2 dose for anterior cervical fusion in this patient",
            "No retrievable corpus evidence for this exact question",
        ),
    },
    "cpa": {
        "title": "left vestibular schwannoma, retrosigmoid",
        "anatomy_supported": (
            "Confirm AICA loop position relative to the porus and IAC drilling limit "
            "(stay >= 2 mm lateral to the labyrinth, trajectory -> fundus)",
            "AICA and labyrinthine artery injury cause brainstem or cochlear infarct",
        ),
        "monitoring_compound": (
            "Facial nerve EMG with free-run and triggered stimulation? "
            "BAEP for hearing preservation? "
            "Lower cranial nerve EMG if caudal extension?",
            "Real-time CN VII mapping defines the safe dissection plane",
        ),
        "closure_phrase": (
            "Watertight dural closure with a fascial graft; IAC sealed with fat and "
            "fibrin glue; layered closure over a subgaleal drain",
            "CSF rhinorrhoea and pseudomeningocele are the dominant complications",
        ),
        "figure_caption_first": "Figure 12-4. Retrosigmoid exposure",
        "figure_caption_full": (
            "Figure 12-4. Retrosigmoid exposure of the cerebellopontine angle showing "
            "the facial-vestibulocochlear complex draped over the tumor capsule."
        ),
        "citation": "Rhoton Cranial Anatomy, p.412",
        "off_target": (
            "Endoscopic endonasal approach to clival chordoma",
            "Retrieved evidence is endonasal, not retrosigmoid",
        ),
        "no_evidence": (
            "Exact stimulation threshold predicting House-Brackmann I in this case",
            "No retrievable corpus evidence for this exact question",
        ),
    },
    "awake": {
        "title": "awake left temporal glioma resection",
        "anatomy_supported": (
            "Map the arcuate fasciculus and ventral language stream relative to the "
            "resection cavity (subcortical stimulation <= 2 mA, current -> 60 Hz)",
            "Injury to language tracts causes permanent aphasia",
        ),
        "monitoring_compound": (
            "Continuous object naming during resection? "
            "Bipolar cortical and subcortical stimulation mapping? "
            "ECoG for after-discharges before each stimulation run?",
            "Live language testing is the only real-time guard against aphasia",
        ),
        "closure_phrase": (
            "Watertight dural closure with a pericranial graft; bone flap fixation with "
            "low-profile plates; layered scalp closure over a subgaleal drain",
            "CSF leak and bone-flap infection drive readmission",
        ),
        "figure_caption_first": "Figure 7-9. Cortical stimulation mapping",
        "figure_caption_full": (
            "Figure 7-9. Cortical stimulation mapping of the dominant temporal lobe "
            "with numbered tags marking naming-arrest sites along the resection margin."
        ),
        "citation": "Berger Glioma Surgery, p.211",
        "off_target": (
            "Stereotactic radiosurgery dosing for brain metastases",
            "Retrieved evidence is radiosurgery, not awake resection",
        ),
        "no_evidence": (
            "Patient-specific naming-arrest current threshold for this cortex",
            "No retrievable corpus evidence for this exact question",
        ),
    },
    "carotid": {
        "title": "right carotid endarterectomy",
        "anatomy_supported": (
            "Confirm the carotid bifurcation height relative to the mandible and plaque "
            "extent (clamp tolerance stump pressure >= 50 mmHg, shunt -> selective)",
            "High bifurcation and distal plaque change exposure and shunt decisions",
        ),
        "monitoring_compound": (
            "EEG for ischemia during cross-clamp? "
            "Stump pressure measurement before clamping? "
            "Somatosensory evoked potentials as an adjunct?",
            "Cross-clamp ischemia detection drives selective shunting",
        ),
        "closure_phrase": (
            "Arteriotomy closure with a bovine pericardial patch; meticulous flushing "
            "before flow restoration; layered closure over a closed-suction drain",
            "Patch thrombosis and neck hematoma are the dominant early complications",
        ),
        "figure_caption_first": "Figure 33-2. Carotid endarterectomy",
        "figure_caption_full": (
            "Figure 33-2. Carotid endarterectomy with patch angioplasty showing the "
            "endpoint tacking sutures at the distal internal carotid artery."
        ),
        "citation": "Rutherford Vascular Surgery, p.1488",
        "off_target": (
            "Endovascular thrombectomy device selection for M1 occlusion",
            "Retrieved evidence is thrombectomy, not endarterectomy",
        ),
        "no_evidence": (
            "Exact shunt-flow threshold guaranteeing no watershed infarct here",
            "No retrievable corpus evidence for this exact question",
        ),
    },
}


def _fig_record(topic_key: str, data: dict) -> EvidenceRecord:
    fig_path = f"/fake/assets/{topic_key}/p0001.png"
    return EvidenceRecord(
        id=f"textbook-{topic_key}-fig",
        source="textbook",
        title=data["citation"],
        text="figure-bearing page",
        metadata={
            "figure_path": fig_path,
            # NOTE: only the first physical line, as textbook-rag extract_caption emits
            "caption": data["figure_caption_first"],
            "citation": data["citation"],
            "book": data["citation"].split(",")[0],
            "page": 1,
        },
    )


def build(topic_key: str) -> Fixture:
    data = _TOPICS[topic_key]
    fig = _fig_record(topic_key, data)
    fig_path = fig.metadata["figure_path"]

    a_q, a_why = data["anatomy_supported"]
    m_q, m_why = data["monitoring_compound"]
    c_q, c_why = data["closure_phrase"]
    ot_q, ot_why = data["off_target"]
    ne_q, ne_why = data["no_evidence"]

    cards = [
        # #7 supported anatomy card carrying a figure + #1 non-latin glyphs in text
        AuditedCard(question=a_q, why_it_matters=a_why, target_file=ANATOMY,
                    section_key="surgical_corridor", compiler_slot="Surgical Corridor",
                    answerability="needs_patient_fact", audit_status="supported"),
        # #6 compound monitoring card (verify)
        AuditedCard(question=m_q, why_it_matters=m_why, target_file=OPERATIVE,
                    section_key="monitoring", compiler_slot="Monitoring",
                    answerability="needs_patient_fact", audit_status="needs_review"),
        # #9 closure phrase in the Operative section (supported)
        AuditedCard(question=c_q, why_it_matters=c_why, target_file=OPERATIVE,
                    section_key="closure_reconstruction",
                    compiler_slot="Closure / Reconstruction",
                    answerability="needs_patient_fact", audit_status="supported"),
        # #9 the SAME closure phrase echoed into the Risk section (verify) -> dedup
        AuditedCard(question=c_q, why_it_matters="Mitigation hinges on the same closure",
                    target_file=RISK, section_key="mitigation", compiler_slot="Mitigation",
                    answerability="needs_patient_fact", audit_status="needs_review"),
        # a DISTINCT Risk card that must survive dedup untouched
        AuditedCard(
            question="Pre-brief the dominant complications for this approach with the "
                     "anesthesia and nursing teams",
            why_it_matters="Shared situational awareness shortens recognition-to-rescue time",
            target_file=RISK, section_key="likely_complications",
            compiler_slot="Likely Complications",
            answerability="needs_patient_fact", audit_status="supported"),
        # #8 off-target -> appendix
        AuditedCard(question=ot_q, why_it_matters=ot_why, target_file=ANATOMY,
                    section_key="variants", compiler_slot="Variants",
                    answerability="needs_evidence", audit_status="off_target",
                    audit_reason=ot_why),
        # #8 no-evidence -> appendix
        AuditedCard(question=ne_q, why_it_matters=ne_why, target_file=RISK,
                    section_key="rescue_triggers", compiler_slot="Rescue Triggers",
                    answerability="needs_evidence", audit_status="no_evidence",
                    audit_reason=ne_why),
    ]

    manifest = AuditedManifest(procedure_family=topic_key, cards=cards)
    card_evidence = {a_q: [fig]}
    # Mimic how a caption wraps across physical PDF lines: the first line is exactly
    # what textbook-rag's extract_caption grabs (the truncation), the rest are
    # continuation lines, terminated by a blank line then unrelated body text.
    first = data["figure_caption_first"]
    remainder = data["figure_caption_full"][len(first):].strip()
    page_texts = {
        fig_path: "\n".join([
            first,
            remainder,
            "",
            "Some unrelated body text on the same page that must not be captured.",
        ]),
    }
    return Fixture(
        topic=data["title"],
        manifest=manifest,
        evidence=[fig],
        card_evidence=card_evidence,
        page_texts=page_texts,
    )


ALL_TOPICS = list(_TOPICS.keys())
