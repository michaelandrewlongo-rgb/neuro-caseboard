"""WS-3 — per-section facet (slot) coverage of the deterministic case scaffold.

The completeness checklist is the section's own slot vocabulary (topic-agnostic; no clinical
literals). The deterministic scaffold must enumerate EVERY facet of EVERY section, even for a sparse
case (no imaging / functional status / comorbidities) — depth must not depend on rich input.
"""

from __future__ import annotations

from collections import defaultdict

from neuro_caseboard.case_context import CaseContext
from neuro_caseboard.case_author import deterministic_case_manifest
from neuro_caseboard.case_sections import CASE_SECTIONS


def _coverage(case):
    got = defaultdict(set)
    for c in deterministic_case_manifest(case).cards:
        got[c.target_file].add(c.section_key)
    return got


def test_scaffold_covers_every_facet_sparse_case():
    # Deliberately sparse: no imaging, no functional_status, no comorbidities.
    case = CaseContext.from_dict({
        "laterality": "left", "level": "L4-5", "pathology": "p",
        "procedure": "q", "surgical_goal": "r", "presentation": "s",
    })
    got = _coverage(case)
    for s in CASE_SECTIONS:
        missing = set(s.slots) - got.get(s.target_file, set())
        assert not missing, f"{s.target_file} missing facets {sorted(missing)} on a sparse case"


def test_scaffold_covers_every_facet_rich_case():
    case = CaseContext.from_dict({
        "laterality": "right", "level": "C5-6", "location": "cervical spine",
        "pathology": "p", "procedure": "q", "surgical_goal": "r",
        "presentation": "s", "imaging": "MRI finding", "functional_status": "ambulatory",
        "comorbidities": ["hypertension"],
    })
    got = _coverage(case)
    for s in CASE_SECTIONS:
        missing = set(s.slots) - got.get(s.target_file, set())
        assert not missing, f"{s.target_file} missing facets {sorted(missing)} on a rich case"
