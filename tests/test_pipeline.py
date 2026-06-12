"""Pipeline orchestration: Explorer -> (Enricher -> Auditor) -> compile -> render.

Exercises the offline path (no retriever), which is deterministic and corpus-free, so it
runs anywhere. Live corpus enrichment is covered by manual end-to-end runs.
"""

import pytest

from neuro_caseboard.pipeline import classify_profile, build_dossier
from neuro_caseboard.render_md import render_markdown


@pytest.mark.parametrize("topic,prof", [
    ("C5-6 corpectomy", "spine"),
    ("left vestibular schwannoma, retrosigmoid", "skull_base"),
    ("right carotid endarterectomy", "vascular"),
])
def test_classify_profile(topic, prof):
    assert classify_profile(topic) == prof


@pytest.mark.parametrize("topic", [
    "C5-6 corpectomy",
    "left vestibular schwannoma retrosigmoid",
    "awake left temporal glioma resection",
    "right carotid endarterectomy",
])
def test_build_dossier_offline_produces_clean_board(topic):
    d = build_dossier(topic, enrich=False)
    headings = [s.heading for s in d.sections]
    assert "Anatomy at Risk" in headings
    assert "Operative Plan" in headings
    assert "Risk and Rescue" in headings
    # offline: nothing corpus-supported, everything to verify, nothing quarantined
    assert d.summary.supported == 0 and d.summary.quarantined == 0
    assert d.summary.to_verify > 0
    claims = [c for s in d.sections for c in s.claims]
    assert claims and all(c.status == "verify" and c.why for c in claims)
    md = render_markdown(d)
    assert "[low]" not in md and "🟢" not in md
    assert "✓" in md and "⚠" in md
