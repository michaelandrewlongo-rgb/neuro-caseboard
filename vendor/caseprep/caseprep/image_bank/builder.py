#!/usr/bin/env python3
"""
CasePrep Image Bank Builder — PubMed Central (E-utilities) Edition

Comprehensive image search across 51 neurosurgery/spine clusters.
Instead of the unreliable Open-i API, this fetches figures directly from
PubMed Central articles via NCBI's E-utilities and CDN.

Flow per query:
  esearch PMC → batch efetch XML → parse figures & captions →
  fetch HTML for CDN image URLs → download → store in SQLite

Usage:
    python -m caseprep.image_bank.builder            # full build
    python -m caseprep.image_bank.builder --dry-run   # structure only

Output: caseprep/image_bank/bank.db + caseprep/image_bank/images/<cluster>/
"""

from __future__ import annotations

import asyncio
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# ── Constants ──────────────────────────────────────────────────────────────────

BANK_DIR = Path(__file__).parent.resolve()
IMAGE_DIR = BANK_DIR / "images"
DB_PATH = BANK_DIR / "bank.db"

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PMC_CDN = "https://cdn.ncbi.nlm.nih.gov/pmc/blobs"
SEARCH_MAX = 100           # articles per query
XML_BATCH = 30             # articles per efetch XML call
MAX_RETRIES = 3

# NCBI API key for higher rate limits (10 req/sec vs 3)
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "") or os.environ.get("NCBI_API_KEY_2", "")
REQUEST_DELAY = 0.12 if NCBI_API_KEY else 0.35  # ~8/sec with key, ~3/sec without

# ── Query definitions ──────────────────────────────────────────────────────────
# Same comprehensive set: 51 clusters, 10 queries each, 510 total.

CORPUS_QUERIES: dict[str, list[tuple[str, str | None]]] = {
    "aneurysm_sah": [
        ("cerebral aneurysm angiogram", None),
        ("saccular aneurysm DSA", None),
        ("subarachnoid hemorrhage CT head", "ct"),
        ("aneurysm coiling embolization fluoroscopy", None),
        ("MCA bifurcation aneurysm 3D angiography", None),
        ("anterior communicating artery aneurysm CTA", "ct"),
        ("aneurysm clipping intraoperative microscope", None),
        ("vasospasm cerebral angiography", None),
        ("posterior communicating artery aneurysm", None),
        ("cerebral aneurysm MR angiography", "mri"),
    ],
    "stroke_thrombectomy": [
        ("acute ischemic stroke CT perfusion", "ct"),
        ("mechanical thrombectomy DSA", None),
        ("MCA occlusion CT angiography", "ct"),
        ("large vessel occlusion MRI DWI", "mri"),
        ("thrombectomy stent retriever fluoroscopy", None),
        ("cerebral infarction CT head", "ct"),
        ("stroke thrombectomy TICI recanalization", None),
        ("basilar artery occlusion thrombectomy", None),
        ("carotid terminus occlusion angiogram", None),
        ("stroke CT ASPECTS", "ct"),
    ],
    "carotid_cervical_vascular": [
        ("carotid stenosis cerebral angiography", None),
        ("carotid endarterectomy intraoperative photo", None),
        ("carotid artery stent angiogram", None),
        ("carotid duplex ultrasound stenosis", "ultrasound"),
        ("vertebral artery dissection MRA", "mri"),
        ("carotid CT angiography", "ct"),
        ("carotid bulb ulcerated plaque", None),
        ("carotid pseudoaneurysm angiogram", None),
        ("vertebral artery origin stenosis angiogram", None),
        ("carotid body tumor angiogram", None),
    ],
    "avm_vascular_malformation": [
        ("cerebral arteriovenous malformation DSA", None),
        ("brain AVM MRI T2", "mri"),
        ("dural arteriovenous fistula angiogram", None),
        ("cavernous malformation MRI brain", "mri"),
        ("AVM embolization Onyx fluoroscopy", None),
        ("vein of Galen malformation angiogram", None),
        ("cerebral AVM CT angiography", "ct"),
        ("spinal dural AVF angiography", None),
        ("AVM nidus microcatheter angiography", None),
        ("developmental venous anomaly MRI", "mri"),
    ],
    "intracranial_hemorrhage": [
        ("intracerebral hemorrhage CT head", "ct"),
        ("subdural hematoma CT brain", "ct"),
        ("middle meningeal artery embolization DSA", None),
        ("epidural hematoma CT head", "ct"),
        ("intraventricular hemorrhage CT", "ct"),
        ("chronic subdural hematoma MRI", "mri"),
        ("cerebral contusion CT", "ct"),
        ("ICH spot sign CT angiography", "ct"),
        ("subdural drain placement CT", "ct"),
        ("traumatic intracranial hemorrhage", "ct"),
    ],
    "general_neurointerventional": [
        ("diagnostic cerebral angiogram", None),
        ("femoral artery access angiography", None),
        ("radial artery cerebral angiography", None),
        ("cerebrovascular anatomy DSA", None),
        ("aortic arch angiography bovine anatomy", None),
        ("cerebral angiogram catheter selection", None),
        ("internal carotid artery angiogram", None),
        ("vertebral artery angiogram", None),
        ("external carotid artery angiogram", None),
        ("cerebral venous phase angiography", None),
    ],
    "flow_diversion": [
        ("Pipeline flow diverter angiogram", None),
        ("flow diverter stent fluoroscopy", None),
        ("WEB device intraoperative angiogram", None),
        ("intrasaccular flow disruption device", None),
        ("flow diverter aneurysm treatment DSA", None),
        ("FRED flow diverter angiogram", None),
        ("Surpass Evolve flow diverter", None),
        ("flow diversion CT angiography", "ct"),
        ("Pipeline embolization device fluoroscopy", None),
        ("flow diverter contrast stasis angiogram", None),
    ],
    "tumor_skull_base": [
        ("meningioma MRI T1 post-contrast", "mri"),
        ("glioblastoma MRI brain", "mri"),
        ("skull base tumor MRI", "mri"),
        ("meningioma CT head", "ct"),
        ("tumor embolization preoperative DSA", None),
        ("pituitary adenoma MRI sella", "mri"),
        ("vestibular schwannoma MRI CPA", "mri"),
        ("brain metastasis MRI post-contrast", "mri"),
        ("craniopharyngioma MRI", "mri"),
        ("meningioma MR venogram", "mri"),
    ],
    "moyamoya": [
        ("moyamoya disease cerebral angiography", None),
        ("moyamoya MRI brain", "mri"),
        ("EC-IC bypass intraoperative photo", None),
        ("moyamoya CT perfusion", "ct"),
        ("pial synangiosis postoperative angiogram", None),
        ("moyamoya collateral vessels DSA", None),
        ("moyamoya STA-MCA bypass angiography", None),
        ("moyamoya periventricular anastomosis", None),
        ("moyamoya ischemic stroke MRI", "mri"),
        ("moyamoya indirect bypass", None),
    ],
    "venous_interventional": [
        ("cerebral venous sinus thrombosis CT venogram", "ct"),
        ("venous sinus stenting fluoroscopy", None),
        ("MR venogram cerebral veins", "mri"),
        ("IIH venous sinus stenosis manometry", None),
        ("cerebral venous thrombosis MRI", "mri"),
        ("sigmoid sinus diverticulum angiogram", None),
        ("transverse sinus stenting DSA", None),
        ("cerebral venogram superior sagittal sinus", None),
        ("dural sinus thrombosis CT head", "ct"),
        ("jugular venous stenosis angiogram", None),
    ],
    "cerebrovascular_other": [
        ("CNS vasculitis cerebral angiography", None),
        ("vessel wall imaging MRI intracranial", "mri"),
        ("reversible cerebral vasoconstriction syndrome angiogram", None),
        ("moyamoya versus vasculitis angiography", None),
        ("cerebral proliferative angiopathy DSA", None),
        ("fibromuscular dysplasia carotid angiogram", None),
        ("carotid dissection MRA neck", "mri"),
        ("intracranial dissection vertebral artery angiogram", None),
        ("cerebral angiogram vasculopathy", None),
        ("RCVS cerebral angiography", None),
    ],
    "spine_interventional": [
        ("vertebroplasty fluoroscopy", None),
        ("kyphoplasty balloon intraoperative", None),
        ("spinal AVM angiography", None),
        ("spinal dural AVF MRI spine", "mri"),
        ("spinal angiogram segmental artery", None),
        ("spinal arteriovenous fistula DSA", None),
        ("cervical spine hemangioblastoma angiogram", None),
        ("spinal tumor embolization preoperative", None),
        ("scoliosis angiography spinal cord", None),
        ("vertebral body metastasis vertebroplasty", None),
    ],
    "neurocritical_care": [
        ("decompressive craniectomy CT head", "ct"),
        ("intracranial pressure monitor CT", "ct"),
        ("traumatic brain injury CT head", "ct"),
        ("external ventricular drain CT", "ct"),
        ("brain death cerebral angiography", None),
        ("hemicraniectomy postoperative CT", "ct"),
        ("ICP bolt insertion CT", "ct"),
        ("decompressive hemicraniectomy bone flap", None),
        ("cerebral edema MRI brain", "mri"),
        ("multimodal monitoring brain oxygenation", None),
    ],
    "pediatric_neurointerventional": [
        ("pediatric cerebral angiogram", None),
        ("pediatric AVM Onyx embolization", None),
        ("pediatric moyamoya angiography", None),
        ("pediatric intracranial aneurysm", None),
        ("pediatric head and neck arteriovenous malformation", None),
        ("pediatric cerebral angiography catheter", None),
        ("pediatric vein of Galen embolization", None),
        ("pediatric intracranial hemorrhage CT", "ct"),
        ("infant cerebral ultrasound", "ultrasound"),
        ("pediatric spinal arteriovenous shunt", None),
    ],
    "radiosurgery": [
        ("Gamma Knife radiosurgery MRI planning", "mri"),
        ("stereotactic radiosurgery frame CT", "ct"),
        ("LINAC radiosurgery head frame", None),
        ("SRS brain metastasis MRI planning", "mri"),
        ("Gamma Knife dose planning MRI", "mri"),
        ("stereotactic radiosurgery CT scan", "ct"),
        ("CyberKnife radiosurgery treatment", None),
        ("radiosurgery for trigeminal neuralgia MRI", "mri"),
        ("stereotactic radiosurgery AVM MRI", "mri"),
        ("radiosurgery tumor control imaging", "mri"),
    ],
    "functional_epilepsy": [
        ("epilepsy surgery MRI brain", "mri"),
        ("SEEG electrode implantation CT", "ct"),
        ("deep brain stimulation lead placement", None),
        ("Wada test cerebral angiography", None),
        ("vagus nerve stimulator implantation", None),
        ("functional MRI brain mapping language", "mri"),
        ("temporal lobectomy MRI mesial temporal sclerosis", "mri"),
        ("DBS subthalamic nucleus placement CT", "ct"),
        ("intraoperative electrocorticography", None),
        ("responsive neurostimulation RNS implantation", None),
    ],
    "intracranial_atherosclerosis": [
        ("intracranial stenosis cerebral angiography", None),
        ("basilar artery stenosis angioplasty", None),
        ("Wingspan stent intracranial deployment", None),
        ("intracranial atherosclerosis CT perfusion", "ct"),
        ("MCA stenosis MR angiography", "mri"),
        ("intracranial vertebrobasilar stenosis angiogram", None),
        ("intracranial angioplasty balloon fluoroscopy", None),
        ("tandem occlusion carotid MCA angiography", None),
        ("ICAD intracranial stent follow-up angiogram", None),
        ("intracranial atherosclerotic plaque vessel wall MRI", "mri"),
    ],

    # ── Rhoton cluster set 1: open cranial microsurgery ──────────────────────────

    "pterional_approach": [
        ("pterional approach Sylvian fissure dissection", None),
        ("Sylvian fissure microsurgical anatomy", None),
        ("sphenoid wing anatomy surgical", None),
        ("anterior clinoidectomy intraoperative", None),
        ("opticocarotid cistern anatomy", None),
        ("internal carotid artery bifurcation anatomy", None),
        ("anterior communicating artery complex anatomy", None),
        ("recurrent artery of Heubner anatomy", None),
        ("Sylvian cistern arachnoid dissection", None),
        ("pterional craniotomy extradural", None),
    ],
    "retrosigmoid_cpa": [
        ("retrosigmoid approach cerebellopontine angle", None),
        ("CPA microsurgical anatomy cranial nerves", None),
        ("trigeminal nerve microvascular decompression", None),
        ("facial nerve cochlear nerve CPA", None),
        ("petrous bone anatomy mastoidectomy", None),
        ("retrosigmoid craniotomy positioning", None),
        ("flocculus cerebellar peduncle anatomy", None),
        ("vestibular schwannoma retrosigmoid exposure", None),
        ("posterior fossa microsurgical anatomy", None),
        ("vertebral artery PICA CPA anatomy", None),
    ],
    "transsphenoidal_skull_base": [
        ("transsphenoidal approach sellar anatomy", None),
        ("sphenoid sinus anatomy endoscopic", None),
        ("cavernous sinus medial wall anatomy", None),
        ("optic chiasm parasellar anatomy", None),
        ("diaphragma sellae anatomy", None),
        ("pituitary stalk infundibulum anatomy", None),
        ("paraclinoid carotid artery anatomy", None),
        ("suprasellar cistern anatomy surgical", None),
        ("sellar floor reconstruction intraoperative", None),
        ("clival anatomy endonasal approach", None),
    ],
    "far_lateral_craniovertebral": [
        ("far lateral approach foramen magnum", None),
        ("vertebral artery V3 segment surgical anatomy", None),
        ("occipital condyle anatomy transcondylar", None),
        ("craniovertebral junction anatomy surgical", None),
        ("jugular foramen anatomy surgical approach", None),
        ("hypoglossal canal anatomy", None),
        ("PICA aneurysm far lateral approach", None),
        ("foramen magnum meningioma surgical", None),
        ("atlantoaxial anatomy transoral", None),
        ("dural ring vertebral artery", None),
    ],
    "ventricular_microsurgery": [
        ("lateral ventricle anatomy surgical", None),
        ("third ventricle microsurgical anatomy", None),
        ("foramen of Monro anatomy", None),
        ("choroidal fissure microsurgical anatomy", None),
        ("transcallosal approach intraventricular", None),
        ("colloid cyst transcallosal resection", None),
        ("trigone atrium lateral ventricle", None),
        ("septum pellucidum choroid plexus", None),
        ("internal cerebral vein velum interpositum", None),
        ("aqueduct of Sylvius anatomy", None),
    ],
    "brainstem_cerebellar": [
        ("fourth ventricle telovelar approach", None),
        ("brainstem safe entry zones anatomy", None),
        ("floor of fourth ventricle facial colliculus", None),
        ("cerebellar peduncle anatomy surgical", None),
        ("pontomedullary sulcus anatomy", None),
        ("medullary striae fourth ventricle", None),
        ("superior cerebellar peduncle decussation", None),
        ("cerebellomedullary cistern magna", None),
        ("pontine anatomy cranial nerve nuclei", None),
        ("rhomboid fossa floor anatomy", None),
    ],
    "white_matter_deep_nuclei": [
        ("corticospinal tract DTI dissection", None),
        ("arcuate fasciculus anatomy surgical", None),
        ("optic radiation temporal horn anatomy", None),
        ("internal capsule white matter anatomy", None),
        ("basal ganglia anatomy coronal", None),
        ("thalamus nuclear anatomy surgical", None),
        ("uncinate fasciculus frontotemporal", None),
        ("superior longitudinal fasciculus anatomy", None),
        ("fornix mammillary body anatomy", None),
        ("corona radiata centrum semiovale", None),
    ],
    "cerebral_venous_anatomy": [
        ("superior sagittal sinus anatomy bridging veins", None),
        ("transverse sinus sigmoid sinus anatomy", None),
        ("cavernous sinus microsurgical anatomy", None),
        ("vein of Labbe anatomy surgical", None),
        ("vein of Trolard anastomotic vein", None),
        ("deep venous system internal cerebral vein", None),
        ("basal vein of Rosenthal anatomy", None),
        ("sphenoparietal sinus middle meningeal", None),
        ("confluence of sinuses torcular anatomy", None),
        ("superior petrosal sinus tentorial", None),
    ],

    # ── Rhoton cluster set 2: additional cranial base & microsurgical corridors ──

    "orbitozygomatic_anterior_base": [
        ("orbitozygomatic craniotomy intraoperative", None),
        ("optic canal decompression surgical", None),
        ("orbital roof anatomy surgical", None),
        ("anterior skull base approach meningioma", None),
        ("supraorbital craniotomy eyebrow incision", None),
        ("optic nerve anatomy canalicular", None),
        ("anterior clinoid process optic strut", None),
        ("orbitofrontal approach aneurysm clipping", None),
        ("zygomatic osteotomy facial nerve", None),
        ("sphenoid wing meningioma surgical approach", None),
    ],
    "cavernous_sinus_middle_fossa": [
        ("cavernous sinus lateral wall anatomy cranial nerves", None),
        ("Meckel cave trigeminal nerve surgical", None),
        ("middle cranial fossa approach petrous apex", None),
        ("Kawase approach petroclival meningioma", None),
        ("cavernous sinus meningioma surgical resection", None),
        ("trigeminal schwannoma middle fossa approach", None),
        ("superior orbital fissure anatomy contents", None),
        ("foramen ovale foramen rotundum anatomy", None),
        ("petrous internal carotid artery surgical", None),
        ("greater superficial petrosal nerve anatomy", None),
    ],
    "posterior_circulation_microsurgery": [
        ("basilar apex aneurysm surgical approach", None),
        ("superior cerebellar artery SCA anatomy perforators", None),
        ("posterior cerebral artery PCA thalamoperforators", None),
        ("posterior communicating artery microsurgical anatomy", None),
        ("basilar trunk aneurysm far lateral approach", None),
        ("PICA distal aneurysm microsurgery", None),
        ("SCA aneurysm pterional transsylvian", None),
        ("basilar perforator arteries brainstem", None),
        ("posterior circulation microsurgical anatomy Rhoton", None),
        ("vertebral artery basilar confluence anatomy", None),
    ],
    "jugular_foramen_petroclival": [
        ("jugular foramen anatomy surgical approach", None),
        ("jugular foramen schwannoma resection approach", None),
        ("glomus jugulare tumor surgical management", None),
        ("petroclival meningioma surgical approach", None),
        ("presigmoid approach petrous temporal bone", None),
        ("transjugular approach skull base", None),
        ("sigmoid sinus jugular bulb anatomy", None),
        ("lower cranial nerve IX X XI surgical", None),
        ("petroclival region microsurgical anatomy", None),
        ("transpetrosal approach posterior fossa", None),
    ],
    "cranial_nerves_cisternal": [
        ("oculomotor nerve cisternal segment anatomy", None),
        ("trochlear nerve tentorial edge anatomy", None),
        ("trigeminal nerve gasserian ganglion anatomy", None),
        ("abducens nerve Dorello canal petrous", None),
        ("facial nerve nervus intermedius CPA", None),
        ("vestibulocochlear nerve internal auditory canal", None),
        ("glossopharyngeal nerve vagus nerve anatomy", None),
        ("spinal accessory nerve jugular foramen", None),
        ("hypoglossal nerve hypoglossal canal", None),
        ("cranial nerve vascular compression syndromes", None),
    ],
    "subarachnoid_cisterns": [
        ("basal cistern anatomy microsurgical", None),
        ("tentorial incisura tentorial notch anatomy", None),
        ("ambient cistern anatomy PCA", None),
        ("interpeduncular cistern basilar apex", None),
        ("prepontine cistern anatomy surgical", None),
        ("sylvian cistern arachnoid dissection", None),
        ("quadrigeminal cistern pineal anatomy", None),
        ("perimesencephalic cistern anatomy", None),
        ("cerebellomedullary cistern magna anatomy", None),
        ("lamina terminalis cistern anatomy", None),
    ],
    "anterior_interhemispheric": [
        ("interhemispheric transcallosal approach", None),
        ("anterior cerebral artery ACA segmental anatomy", None),
        ("callosomarginal artery pericallosal artery anatomy", None),
        ("anterior communicating artery complex microsurgery", None),
        ("lamina terminalis approach third ventricle", None),
        ("frontopolar artery orbitofrontal artery", None),
        ("interhemispheric fissure dissection anatomy", None),
        ("septal veins foramen of Monro", None),
        ("subfrontal approach anterior cranial fossa", None),
        ("olfactory tract gyrus rectus anatomy", None),
    ],
    "temporal_limbic": [
        ("anterior temporal lobectomy surgical anatomy", None),
        ("amygdala hippocampal anatomy surgical", None),
        ("transsylvian amygdalohippocampectomy", None),
        ("fusiform gyrus parahippocampal gyrus", None),
        ("uncus anatomy temporal lobe", None),
        ("fornix mammillary body Papez circuit", None),
        ("optic radiations temporal Meyer loop", None),
        ("temporal horn lateral ventricle anatomy", None),
        ("isthmus cingulate parahippocampal", None),
        ("mesial temporal sclerosis MRI anatomy", None),
    ],

    # ── Additional cranial clusters ──

    "cranioplasty_reconstruction": [
        ("cranioplasty bone flap reconstruction", None),
        ("titanium mesh cranioplasty intraoperative", None),
        ("PMMA cranioplasty technique surgical", None),
        ("custom 3D printed cranioplasty implant", None),
        ("cranioplasty infection management", None),
        ("calvarial reconstruction split thickness", None),
        ("cranioplasty bone flap resorption", None),
        ("autologous bone cranioplasty", None),
        ("cranial defect reconstruction surgical", None),
        ("cranioplasty postoperative CT", "ct"),
    ],
    "csf_diversion_shunts": [
        ("ventriculoperitoneal shunt placement intraoperative", None),
        ("ventriculoatrial shunt surgical technique", None),
        ("lumboperitoneal shunt technique", None),
        ("endoscopic third ventriculostomy ETV", None),
        ("shunt malfunction imaging CT", "ct"),
        ("shunt infection treatment surgical", None),
        ("slit ventricle syndrome management", None),
        ("hydrocephalus shunt revision", None),
        ("VP shunt tap technique", None),
        ("programmable shunt valve MRI", "mri"),
    ],
    "icp_monitoring": [
        ("intracranial pressure monitor insertion", None),
        ("ICP bolt ventriculostomy", None),
        ("intraparenchymal ICP monitor", None),
        ("external ventricular drain EVD placement", None),
        ("ICP waveform interpretation", None),
        ("elevated ICP management", None),
        ("multimodal monitoring brain oxygenation", None),
        ("lumbar drain ICP monitoring", None),
        ("decompressive craniectomy ICP", None),
        ("telemetric ICP monitoring", None),
    ],
    "cranial_fixation": [
        ("Mayfield head holder skull fixation", None),
        ("Sugita head frame positioning", None),
        ("cranial fixation pin site", None),
        ("head fixation pediatric cranial", None),
        ("horseshoe headrest positioning", None),
        ("cranial clamp skull fixation technique", None),
        ("patient positioning cranial surgery", None),
        ("park bench position craniotomy", None),
        ("three pin head fixation CT", "ct"),
        ("supine position head rotation craniotomy", None),
    ],
    "stereotactic_biopsy": [
        ("stereotactic brain biopsy technique", None),
        ("frameless stereotactic biopsy navigation", None),
        ("frame-based stereotactic biopsy surgery", None),
        ("stereotactic biopsy targeting MRI", "mri"),
        ("deep brain biopsy approach", None),
        ("stereotactic biopsy complications hemorrhage", None),
        ("brainstem stereotactic biopsy", None),
        ("stereotactic biopsy needle trajectory", None),
        ("minimally invasive brain biopsy", None),
        ("stereotactic biopsy fused PET MRI", "mri"),
    ],
    "endoscopic_cranial_approaches": [
        ("endoscopic transventricular approach lateral ventricle", None),
        ("endoscopic third ventriculostomy ETV anatomy", None),
        ("endoscopic aqueductoplasty stenosis", None),
        ("endoscopic intraventricular cyst fenestration", None),
        ("neuroendoscopy surgical technique", None),
        ("endoscopic colloid cyst resection", None),
        ("endoscopic septum pellucidum fenestration", None),
        ("endoscopic foramen of Monro anatomy", None),
        ("endoscopic third ventricle anatomy", None),
        ("neuroendoscopy instrumentation endoscope", None),
    ],
    "pediatric_craniosynostosis": [
        ("sagittal synostosis craniosynostosis repair", None),
        ("metopic synostosis fronto-orbital advancement", None),
        ("coronal synostosis unilateral repair", None),
        ("lambdoid synostosis posterior vault", None),
        ("endoscopic strip craniectomy technique", None),
        ("spring cranioplasty craniosynostosis", None),
        ("cranial vault remodeling pediatric", None),
        ("bicoronal synostosis syndrome", None),
        ("posterior plagiocephaly positional", None),
        ("cranial expansion distraction osteogenesis", None),
    ],
    "intraoperative_imaging": [
        ("intraoperative MRI brain tumor resection", "mri"),
        ("intraoperative CT navigation", "ct"),
        ("intraoperative ultrasound brain tumor", "ultrasound"),
        ("5-ALA fluorescence guided glioma surgery", None),
        ("neuronavigation registration technique", None),
        ("intraoperative angiography DSA", None),
        ("microscope integrated ICG fluorescence", None),
        ("cortical stimulation brain mapping", None),
        ("intraoperative tractography DTI", "mri"),
        ("augmented reality navigation neurosurgery", None),
    ],

    # ── Spine surgery clusters ──

    "cervical_degenerative": [
        ("ACDF anterior cervical discectomy fusion", None),
        ("cervical disc replacement arthroplasty", None),
        ("posterior cervical laminectomy fusion", None),
        ("cervical laminoplasty technique", None),
        ("cervical myelopathy MRI", "mri"),
        ("cervical radiculopathy foraminotomy", None),
        ("cervical corpectomy reconstruction", None),
        ("cervical spondylotic myelopathy surgical", None),
        ("anterior cervical plate fixation", None),
        ("cervical lateral mass screw fixation", None),
    ],
    "cervical_trauma": [
        ("odontoid fracture screw fixation", None),
        ("hangman fracture C2 pars screw", None),
        ("subaxial cervical spine fracture dislocation", None),
        ("cervical traction Gardner-Wells tongs", None),
        ("halo vest placement cervical spine", None),
        ("cervical spinal cord injury MRI", "mri"),
        ("C1 lateral mass screw C2 pars", None),
        ("occipitocervical fusion trauma", None),
        ("cervical facet dislocation reduction", None),
        ("unilateral facet fracture cervical", None),
    ],
    "lumbar_degenerative": [
        ("lumbar microdiscectomy technique", None),
        ("lumbar laminectomy spinal stenosis", None),
        ("TLIF transforaminal lumbar interbody fusion", None),
        ("PLIF posterior lumbar interbody fusion", None),
        ("ALIF anterior lumbar interbody fusion", None),
        ("OLIF oblique lumbar interbody fusion", None),
        ("lumbar spondylolisthesis reduction fusion", None),
        ("lumbar disc herniation MRI", "mri"),
        ("lumbar spinal stenosis decompression", None),
        ("posterolateral lumbar fusion instrumentation", None),
    ],
    "spine_deformity": [
        ("scoliosis posterior spinal fusion instrumentation", None),
        ("pedicle subtraction osteotomy PSO sagittal balance", None),
        ("Smith-Petersen osteotomy SPO technique", None),
        ("growing rod scoliosis pediatric", None),
        ("VEPTR expansion thoracoplasty", None),
        ("vertebral column resection VCR deformity", None),
        ("adult spinal deformity sagittal alignment", None),
        ("Scheuermann kyphosis osteotomy", None),
        ("hemivertebra resection congenital scoliosis", None),
        ("spinopelvic fixation pelvic screw", None),
    ],
    "spine_oncology": [
        ("intradural extramedullary tumor resection", None),
        ("intramedullary spinal cord tumor surgery", None),
        ("spinal meningioma resection", None),
        ("spinal schwannoma resection nerve sparing", None),
        ("chordoma clivus sacrum resection", None),
        ("spinal metastasis decompression stabilization", None),
        ("en bloc spondylectomy tumor resection", None),
        ("ependymoma spinal cord resection", None),
        ("spinal hemangioblastoma intraoperative", None),
        ("radiofrequency ablation spinal tumor", None),
    ],
    "spine_trauma": [
        ("thoracic compression fracture management", None),
        ("burst fracture thoracolumbar surgery", None),
        ("Chance fracture flexion distraction", None),
        ("thoracolumbar fracture classification TLICS", None),
        ("traumatic spinal cord injury MRI", "mri"),
        ("spinal fracture pedicle screw fixation", None),
        ("sacral fracture spinopelvic dissociation", None),
        ("thoracolumbar fracture corpectomy", None),
        ("traumatic spondylolisthesis reduction", None),
        ("spinal epidural hematoma surgical", None),
    ],
    "spine_infection_inflammatory": [
        ("vertebral osteomyelitis discitis MRI", "mri"),
        ("spinal epidural abscess decompression", None),
        ("Pott disease tuberculous spondylitis", None),
        ("postoperative spine infection wound", None),
        ("ankylosing spondylitis spinal fracture", None),
        ("rheumatoid arthritis cervical instability", None),
        ("pyogenic spondylodiscitis imaging", None),
        ("spinal fusion infection hardware removal", None),
        ("discitis osteomyelitis biopsy", None),
        ("fungal spinal infection imaging", None),
    ],
    "spine_congenital": [
        ("Chiari malformation decompression surgery", None),
        ("syringomyelia syrinx shunt management", None),
        ("tethered cord syndrome release surgery", None),
        ("spinal dysraphism myelomeningocele repair", None),
        ("diastematomyelia bone spur resection", None),
        ("lipomeningocele lipomyelomeningoceel surgical", None),
        ("dermal sinus tract spinal congenital", None),
        ("split cord malformation type I II", None),
        ("sacral agenesis caudal regression", None),
        ("neurenteric cyst spinal resection", None),
    ],
    "spine_anatomy_approaches": [
        ("transoral approach odontoid resection", None),
        ("costotransversectomy thoracic approach", None),
        ("retropleural thoracotomy approach thoracic spine", None),
        ("retroperitoneal approach lumbar spine", None),
        ("transpsoas approach lateral lumbar", None),
        ("paraspinal muscle splitting approach", None),
        ("posterior midline approach lumbar spine", None),
        ("spine surgical anatomy pedicle nerve root", None),
        ("ligamentum flavum hypertrophy anatomy", None),
        ("vertebral artery anatomy cervical approach", None),
    ],
    "minimally_invasive_spine": [
        ("MISS minimally invasive spine surgery", None),
        ("tubular retractor microdiscectomy", None),
        ("percutaneous pedicle screw placement", None),
        ("endoscopic lumbar discectomy technique", None),
        ("XLIF lateral interbody fusion", None),
        ("minimally invasive TLIF approach", None),
        ("percutaneous kyphoplasty technique", None),
        ("endoscopic cervical foraminotomy", None),
        ("minimally invasive laminectomy", None),
        ("O-arm navigation pedicle screw", None),
    ],
}

# ── Database ───────────────────────────────────────────────────────────────────


def init_db() -> sqlite3.Connection:
    """Create schema if needed, return connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fig_id      TEXT UNIQUE NOT NULL,   -- {pmcid}_{fig_label}
            cluster     TEXT NOT NULL,
            query       TEXT NOT NULL,
            pmcid       TEXT,
            pmid        TEXT,
            title       TEXT,
            caption     TEXT,
            fig_label   TEXT,
            journal     TEXT,
            img_url     TEXT,                    -- CDN image URL
            local_path  TEXT,
            fetched_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_images_cluster ON images(cluster)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_images_fig_id ON images(fig_id)
    """)
    return conn


def fig_already_stored(conn: sqlite3.Connection, fig_id: str) -> bool:
    return conn.execute("SELECT 1 FROM images WHERE fig_id = ?", (fig_id,)).fetchone() is not None


def insert_image(conn: sqlite3.Connection, record: dict) -> None:
    try:
        conn.execute("""
            INSERT OR IGNORE INTO images (
                fig_id, cluster, query, pmcid, pmid, title, caption,
                fig_label, journal, img_url, local_path
            ) VALUES (
                :fig_id, :cluster, :query, :pmcid, :pmid, :title, :caption,
                :fig_label, :journal, :img_url, :local_path
            )
        """, record)
    except sqlite3.IntegrityError:
        pass


# ── PMC API ────────────────────────────────────────────────────────────────────


async def search_pmc(client: httpx.AsyncClient, query: str) -> list[str]:
    """Search PMC for articles matching query. Returns list of PMCID numbers."""
    params = {"db": "pmc", "term": query, "retmax": str(SEARCH_MAX), "retmode": "json"}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(f"{EUTILS}/esearch.fcgi", params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            return data.get("esearchresult", {}).get("idlist", [])
        except Exception as exc:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(attempt * 2.0)
            else:
                print(f"    [FAIL] PMC search: {exc}")
                return []
    return []


async def fetch_article_xml(client: httpx.AsyncClient, pmcids: list[str]) -> str | None:
    """Fetch full XML for a batch of articles. Returns raw XML string."""
    ids = ",".join(pmcids)
    params = {"db": "pmc", "id": ids, "retmode": "xml"}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(f"{EUTILS}/efetch.fcgi", params=params, timeout=60.0)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(attempt * 2.0)
            else:
                print(f"    [FAIL] XML fetch batch {ids[:40]}...: {exc}")
                return None
    return None


def parse_figures_from_xml(
    xml_text: str,
) -> list[dict[str, Any]]:
    """Parse PMC XML and extract figures with captions and graphic filenames.

    Returns list of dicts with: pmcid, pmid, title, caption, fig_label,
    graphic_href, journal.
    """
    figures: list[dict[str, Any]] = []

    # Extract PMCID from the XML (just the numeric part)
    pmcid_match = re.search(r'<article-id\s+[^>]*pub-id-type\s*=\s*"pmcid"[^>]*>PMC?(\d+)', xml_text)
    pmcid = pmcid_match.group(1) if pmcid_match else ""

    pmid_match = re.search(r'<article-id\s+[^>]*pub-id-type\s*=\s*"pmid"[^>]*>(\d+)', xml_text)
    pmid = pmid_match.group(1) if pmid_match else ""

    article_title_match = re.search(r'<article-title[^>]*>(.*?)</article-title>', xml_text, re.DOTALL)
    article_title = _strip_html(article_title_match.group(1)) if article_title_match else ""

    journal_match = re.search(r'<journal-title[^>]*>(.*?)</journal-title>', xml_text)
    journal = journal_match.group(1) if journal_match else ""

    if not pmcid:
        return figures

    # Find all <fig> elements
    fig_pattern = re.compile(r'<fig[^>]*>.*?</fig>', re.DOTALL)
    for fig_match in fig_pattern.finditer(xml_text):
        fig_xml = fig_match.group()

        fig_id_match = re.search(r'id\s*=\s*"([^"]+)"', fig_xml)
        fig_id = fig_id_match.group(1) if fig_id_match else ""

        # Label (e.g., "Fig. 1", "Figure 2")
        label_match = re.search(r'<label[^>]*>(.*?)</label>', fig_xml)
        fig_label = _strip_html(label_match.group(1)) if label_match else fig_id

        # Caption
        cap_match = re.search(r'<caption[^>]*>(.*?)</caption>', fig_xml, re.DOTALL)
        caption = ""
        if cap_match:
            cap_text = cap_match.group(1)
            caption = _strip_html(cap_text).strip()

        # Graphic href (filename)
        href_match = re.search(r'xlink:href\s*=\s*"([^"]+)"', fig_xml)
        graphic_href = href_match.group(1) if href_match else ""

        if graphic_href:
            figures.append({
                "pmcid": pmcid,
                "pmid": pmid,
                "title": article_title,
                "journal": journal,
                "caption": caption,
                "fig_label": fig_label,
                "graphic_href": graphic_href,
            })

    return figures


def _strip_html(text: str) -> str:
    """Remove XML/HTML tags from text."""
    text = re.sub(r'<[^>]+>', "", text)
    text = text.replace("\\n", " ").replace("\\t", " ")
    text = re.sub(r'\s+', " ", text).strip()
    return text


async def fetch_cdn_url(
    client: httpx.AsyncClient,
    pmcid: str,
) -> dict[str, str] | None:
    """Fetch article HTML page and extract figure CDN URLs.

    Returns dict of {graphic_href: cdn_url} or None on failure.
    """
    url = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmcid}/"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(url, timeout=30.0, follow_redirects=True)
            resp.raise_for_status()
            html = resp.text

            # Extract all figure image src URLs
            # Pattern: <img[^>]*src="https://cdn.ncbi.nlm.nih.gov/pmc/blobs/.../filename"
            cdn_map: dict[str, str] = {}
            # Find all img tags with CDN URLs
            img_pattern = re.compile(r'<img[^>]*src="(https://cdn\.ncbi\.nlm\.nih\.gov/pmc/blobs/[^"]+)"')
            for img_match in img_pattern.finditer(html):
                cdn_url = img_match.group(1)
                # Extract the filename from the end of the CDN URL
                filename = cdn_url.rsplit("/", 1)[-1] if "/" in cdn_url else ""
                if filename:
                    cdn_map[filename] = cdn_url

            return cdn_map if cdn_map else None

        except Exception as exc:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(attempt * 1.0)
            else:
                return None
    return None


# ── Download ────────────────────────────────────────────────────────────────────


async def download_image(client: httpx.AsyncClient, url: str, filepath: Path) -> bool:
    """Download image from URL to filepath. Returns True on success."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    if filepath.exists():
        return True

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(url, timeout=30.0)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
            return True
        except Exception as exc:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(attempt * 1.0)
            else:
                return False
    return False


# ── Orchestration ───────────────────────────────────────────────────────────────


def print_stats(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT cluster, COUNT(*) FROM images GROUP BY cluster ORDER BY COUNT(*) DESC",
    ).fetchall()
    total = sum(r[1] for r in rows)
    print(f"\n{'='*60}")
    print(f"  Image Bank Summary — {total} figures in {len(rows)} clusters")
    print(f"{'='*60}")
    for cluster, count in rows:
        print(f"  {cluster:42s} {count:4d}")
    print(f"{'='*60}")
    print(f"  DB:  {DB_PATH}")
    print(f"  Images: {IMAGE_DIR}/")
    print(f"{'='*60}\n")


async def _process_query(
    client: httpx.AsyncClient,
    conn: sqlite3.Connection,
    query: str,
    cluster: str,
    cdn_cache: dict[str, dict[str, str] | None],
) -> tuple[int, int, int]:
    """Process one query: search PMC → fetch XML → parse figures → download.

    Returns (articles_found, figures_found, figures_downloaded).
    """
    print(f"    Searching PMC...", end=" ", flush=True)
    pmcids = await search_pmc(client, query)

    if not pmcids:
        print("0 articles")
        return 0, 0, 0

    print(f"{len(pmcids)} articles")

    total_figures = 0
    total_downloaded = 0

    # Process articles in XML batches
    for batch_start in range(0, len(pmcids), XML_BATCH):
        batch = pmcids[batch_start:batch_start + XML_BATCH]
        xml_text = await fetch_article_xml(client, batch)
        if not xml_text:
            continue

        # Split XML into individual articles (they're concatenated in the response)
        article_pattern = re.compile(r'(<article\s[^>]*>.*?</article>)', re.DOTALL)
        articles = article_pattern.findall(xml_text)

        for article_xml in articles:
            figures = parse_figures_from_xml(article_xml)
            if not figures:
                continue

            pmcid = figures[0]["pmcid"]

            # Get CDN URLs - use cache if available
            if pmcid not in cdn_cache:
                cdn_map = await fetch_cdn_url(client, pmcid)
                cdn_cache[pmcid] = cdn_map
                await asyncio.sleep(REQUEST_DELAY)

            cdn_map = cdn_cache.get(pmcid)

            for fig in figures:
                fig_id = f"{pmcid}_{fig['fig_label']}"
                if fig_already_stored(conn, fig_id):
                    continue

                graphic_href = fig["graphic_href"]
                img_url = ""

                # Get CDN URL from map, or try constructing
                if cdn_map:
                    img_url = cdn_map.get(graphic_href, "")

                if not img_url:
                    continue

                # Download
                ext = Path(graphic_href).suffix or ".jpg"
                cluster_dir = IMAGE_DIR / cluster
                cluster_dir.mkdir(parents=True, exist_ok=True)
                filepath = cluster_dir / f"{fig_id}{ext}"

                downloaded = await download_image(client, img_url, filepath)
                if downloaded:
                    total_downloaded += 1

                # Store in DB
                record = {
                    "fig_id": fig_id,
                    "cluster": cluster,
                    "query": query,
                    "pmcid": f"PMC{pmcid}",
                    "pmid": fig.get("pmid", ""),
                    "title": fig.get("title", ""),
                    "caption": fig.get("caption", ""),
                    "fig_label": fig.get("fig_label", ""),
                    "journal": fig.get("journal", ""),
                    "img_url": img_url,
                    "local_path": str(filepath.resolve()) if downloaded else "",
                }
                insert_image(conn, record)
                total_figures += 1

            conn.commit()

    return len(pmcids), total_figures, total_downloaded


async def build() -> None:
    """Main build orchestration."""
    conn = init_db()
    cdn_cache: dict[str, dict[str, str] | None] = {}

    total_articles = 0
    total_figures = 0
    total_downloaded = 0

    print(f"{'='*60}")
    print(f"  CasePrep Image Bank Builder — PMC Edition")
    print(f"  {len(CORPUS_QUERIES)} clusters, {sum(len(qs) for qs in CORPUS_QUERIES.values())} queries")
    print(f"  Searching {SEARCH_MAX} articles per query via NCBI E-utilities")
    print(f"  DB:  {DB_PATH}")
    print(f"  Images: {IMAGE_DIR}/")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60.0),
        headers={"User-Agent": "CasePrep/1.0 (image-bank builder; academic)", "Accept": "text/xml,application/json,text/html"},
    ) as client:

        for cluster_idx, (cluster, queries) in enumerate(CORPUS_QUERIES.items(), 1):
            cluster_articles = 0
            cluster_figures = 0
            cluster_downloaded = 0

            print(f"\n[{cluster_idx}/{len(CORPUS_QUERIES)}] {cluster} ({len(queries)} queries)")

            for q_idx, (query, _modality) in enumerate(queries, 1):
                print(f"  [{q_idx}/{len(queries)}] \"{query}\"", flush=True)

                articles, figures, downloaded = await _process_query(
                    client, conn, query, cluster, cdn_cache,
                )
                cluster_articles += articles
                cluster_figures += figures
                cluster_downloaded += downloaded

                # Rate limit: be polite to E-utilities
                await asyncio.sleep(REQUEST_DELAY)

            print(f"  ── {cluster}: {cluster_articles} articles, {cluster_figures} figures, "
                  f"{cluster_downloaded} downloaded {'✓' if cluster_figures > 0 else '∅'}")

            total_articles += cluster_articles
            total_figures += cluster_figures
            total_downloaded += cluster_downloaded

    print_stats(conn)
    conn.close()


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        conn = init_db()
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        for cluster in CORPUS_QUERIES:
            (IMAGE_DIR / cluster).mkdir(parents=True, exist_ok=True)
        total_q = sum(len(qs) for qs in CORPUS_QUERIES.values())
        print(f"{'='*60}")
        print(f"  Image Bank Dry Run — PMC Edition — structure validated")
        print(f"{'='*60}")
        print(f"  DB:       {DB_PATH}")
        print(f"  Image dir:{IMAGE_DIR}/")
        print(f"  Clusters: {len(CORPUS_QUERIES)}")
        print(f"  Queries:  {total_q} (up to {total_q * SEARCH_MAX} article searches)")
        print()
        print("  Cluster directories created:")
        for c in sorted(CORPUS_QUERIES):
            print(f"    {c:42s} {len(CORPUS_QUERIES[c])} queries")
        print(f"{'='*60}")
        conn.close()
    else:
        asyncio.run(build())
