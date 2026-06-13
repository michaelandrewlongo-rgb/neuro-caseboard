"""The topic-agnostic coverage ontology: archetype tagging + required dimensions."""

from neuro_caseboard.ontology import tag_archetypes, required_dimensions


def _dims(topic):
    return " | ".join(required_dimensions(topic)).lower()


def test_posterior_fossa_peds_requires_hydrocephalus_and_staging():
    d = _dims("suboccipital craniotomy for pediatric fourth-ventricle medulloblastoma")
    assert "hydrocephalus" in d                      # the item the LLM kept dropping
    assert "csf cytology" in d or "neuraxis" in d     # oncologic staging
    assert "weight-based allowable blood loss" in d   # pediatric dimension


def test_aneurysm_requires_proximal_control_icg_adenosine():
    d = _dims("pterional clipping of a ruptured left MCA bifurcation aneurysm")
    assert "proximal control" in d
    assert "icg" in d
    assert "adenosine" in d
    assert "vasospasm" in d


def test_meningioma_requires_embolization_blood_loss_veins():
    d = _dims("right frontal convexity meningioma resection, Simpson grade I")
    assert "embolization" in d
    assert "blood loss" in d
    assert "draining vein" in d


def test_acdf_requires_rln_and_airway_hematoma():
    d = _dims("C5-6 ACDF for cervical spondylotic myelopathy")
    assert "recurrent laryngeal nerve" in d
    assert "neck hematoma" in d


def test_universal_floor_always_present():
    d = _dims("some unusual peripheral nerve operation")
    assert "post-operative watch" in d or "immediate post-operative watch" in d
    assert "anesthesia / team brief" in d


def test_tags_are_multi_axis():
    tags = tag_archetypes("awake craniotomy for left dominant frontal glioma")
    assert "eloquent_awake" in tags and "glioma" in tags and "oncologic" in tags


def test_no_offtarget_dimensions_for_simple_case():
    # a convexity meningioma must not pull in CPA / posterior-fossa cranial-nerve dimensions
    d = _dims("right frontal convexity meningioma resection")
    assert "internal auditory canal" not in d
    assert "lower cranial nerves (ix, x, xii)" not in d
