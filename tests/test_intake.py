"""Dictation intake: free text -> CaseContext.

Mirrors test_explore_llm.py: the model call is dependency-injected (complete_fn), so these
tests are deterministic and never touch the network. Also pins the topic-agnostic invariant —
the deterministic fallback extracts only text-structure signals, never clinical content.
"""

import json

from neuro_caseboard.intake import parse_dictation, deterministic_parse


def _fake(payload):
    """A complete_fn that ignores its args and returns the given string."""
    return lambda system, user: payload


SPINE_DICTATION = (
    "This is a 62 year old woman with progressive gait imbalance and right-hand clumsiness. "
    "MRI shows C5-6 spondylotic cord compression with myelomalacia. She has hypertension and "
    "type 2 diabetes, and takes aspirin. We plan an anterior cervical discectomy and fusion "
    "for cord decompression."
)

LLM_JSON = json.dumps({
    "age": 62, "sex": "female", "laterality": "right", "level": "C5-6",
    "pathology": "cervical spondylotic myelopathy",
    "procedure": "anterior cervical discectomy and fusion (ACDF)",
    "surgical_goal": "spinal cord decompression",
    "comorbidities": ["hypertension", "type 2 diabetes"],
    "medications": ["aspirin"],
})


def test_llm_parse_populates_fields_and_marks_source():
    cc = parse_dictation(SPINE_DICTATION, complete_fn=_fake(LLM_JSON))
    assert cc.source == "llm"
    assert cc.age == 62 and cc.sex == "F" and cc.laterality == "right"
    assert cc.level == "C5-6"
    assert "decompression" in cc.surgical_goal.lower()
    assert "hypertension" in cc.comorbidities
    assert cc.raw_dictation == SPINE_DICTATION
    assert cc.missing_critical() == []


def test_llm_parse_merges_deterministic_floor_for_blank_geometry():
    # The model omitted laterality/level/age/sex; the deterministic text-structure pass fills them.
    thin = json.dumps({"pathology": "myelopathy", "procedure": "ACDF",
                       "surgical_goal": "decompression"})
    cc = parse_dictation(SPINE_DICTATION, complete_fn=_fake(thin))
    assert cc.source == "llm"
    assert cc.level == "C5-6"          # filled from regex floor
    assert cc.laterality == "right"    # filled from regex floor
    assert cc.age == 62 and cc.sex == "F"


def test_llm_parse_tolerates_fenced_json():
    fenced = "```json\n" + LLM_JSON + "\n```"
    cc = parse_dictation(SPINE_DICTATION, complete_fn=_fake(fenced))
    assert cc.source == "llm" and cc.level == "C5-6"


def test_falls_back_to_deterministic_on_model_error():
    def boom(system, user):
        raise RuntimeError("provider down")
    cc = parse_dictation(SPINE_DICTATION, complete_fn=boom)
    assert cc.source == "deterministic"
    assert cc.level == "C5-6" and cc.laterality == "right"
    assert cc.age == 62 and cc.sex == "F"


def test_falls_back_to_deterministic_on_unparseable_output():
    cc = parse_dictation(SPINE_DICTATION, complete_fn=_fake("not json at all"))
    assert cc.source == "deterministic"
    assert cc.level == "C5-6"


def test_no_provider_no_fn_uses_deterministic(monkeypatch):
    # Hermetic: clear every provider selector so a dev shell defaulting to a provider can't leak.
    for v in ("CASEBOARD_LLM_PROVIDER", "GOOGLE_CLOUD_PROJECT", "ANTHROPIC_API_KEY",
              "ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    cc = parse_dictation(SPINE_DICTATION)
    assert cc.source == "deterministic" and cc.level == "C5-6"


# --- deterministic text-structure extraction across subspecialties ----------

def test_deterministic_extracts_cranial_laterality_no_level():
    cc = deterministic_parse(
        "A 47-year-old man with a left frontal lesion and word-finding difficulty.")
    assert cc.age == 47 and cc.sex == "M"
    assert cc.laterality == "left"
    assert cc.level == ""               # no spine level in a cranial case


def test_deterministic_extracts_vascular_and_lumbar_level():
    cc = deterministic_parse("65 y/o female, ruptured left MCA aneurysm.")
    assert cc.age == 65 and cc.sex == "F" and cc.laterality == "left"
    lumbar = deterministic_parse("Severe L4-5 stenosis with neurogenic claudication.")
    assert lumbar.level == "L4-5"


def test_deterministic_level_prefers_disc_range_over_single_root():
    # "right C6 radiculopathy" (single root) precedes "C5-6" (disc/operative level) — the range wins.
    cc = deterministic_parse(
        "right C6 radiculopathy; MRI shows C5-6 spondylotic cord compression; ACDF at C5-6.")
    assert cc.level == "C5-6"


def test_deterministic_preserves_sacral_level():
    # "L5-S1" is a common lumbosacral operative level. Dropping the sacral segment would build the
    # no-LLM dossier (topic, title, schematics) around the wrong level ("L5"), so S must be a
    # first-class vertebral letter alongside C/T/L — range form, slash form, and a bare sacral body.
    assert deterministic_parse("L5-S1 spondylolisthesis for TLIF.").level == "L5-S1"
    assert deterministic_parse("L5/S1 stenosis with neurogenic claudication.").level == "L5-S1"
    assert deterministic_parse("S1 radiculopathy from a paracentral disc.").level == "S1"


def test_deterministic_laterality_ignores_handedness():
    # "right-handed" is about the patient, not the lesion — the lesion side ("left") must win.
    cc = deterministic_parse(
        "A 38 year old right-handed woman with a left dominant frontal glioma.")
    assert cc.laterality == "left"


def test_deterministic_laterality_prefers_lesion_over_symptom_side():
    # WS-5: a stroke dictation names the SYMPTOM side first ("right-sided weakness") but the lesion /
    # operative side is the other one ("left MCA M1"); the dominant (most-mentioned) side wins,
    # topic-agnostically — no clinical lexicon, just token frequency.
    cc = deterministic_parse(
        "A 72 year old man with sudden right-sided weakness and aphasia; CTA shows a left middle "
        "cerebral artery M1 occlusion. We plan thrombectomy of the left M1.")
    assert cc.laterality == "left"


def test_deterministic_laterality_frequency_ties_break_to_first():
    # A single mention each: the first directional (the one the dictation leads with) wins.
    cc = deterministic_parse("A left pterional craniotomy; the right A1 is dominant.")
    assert cc.laterality == "left"


def test_deterministic_laterality_extracts_midline():
    cc = deterministic_parse("A midline suprasellar craniopharyngioma elevating the chiasm.")
    assert cc.laterality == "midline"


def test_deterministic_is_topic_agnostic_no_clinical_vocab():
    # The fallback must NOT invent semantics from a hardcoded clinical lexicon.
    cc = deterministic_parse(SPINE_DICTATION)
    assert cc.pathology == "" and cc.procedure == "" and cc.surgical_goal == ""
    assert cc.comorbidities == []
    assert cc.presentation == SPINE_DICTATION   # raw prose retained for the model/user
