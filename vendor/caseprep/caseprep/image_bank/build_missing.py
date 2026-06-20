#!/usr/bin/env python3
"""
Build only the missing clusters in the Image Bank.
Wraps builder.py's internals but skips the 24 already-populated clusters.

Usage:
    python -m caseprep.image_bank.build_missing
"""
from __future__ import annotations
import sys
from pathlib import Path

# ── List of clusters that already have data (skip these) ──────────────────────
EXISTING_CLUSTERS = {
    "aneurysm_sah", "stroke_thrombectomy", "carotid_cervical_vascular",
    "avm_vascular_malformation", "intracranial_hemorrhage",
    "general_neurointerventional", "flow_diversion", "tumor_skull_base",
    "moyamoya", "venous_interventional", "cerebrovascular_other",
    "spine_interventional", "neurocritical_care",
    "pediatric_neurointerventional", "radiosurgery", "functional_epilepsy",
    "intracranial_atherosclerosis", "pterional_approach", "retrosigmoid_cpa",
    "transsphenoidal_skull_base", "far_lateral_craniovertebral",
    "ventricular_microsurgery", "brainstem_cerebellar",
    "white_matter_deep_nuclei",
}

# Import builder and filter to only missing clusters
from caseprep.image_bank import builder

MISSING = {
    name: queries
    for name, queries in builder.CORPUS_QUERIES.items()
    if name not in EXISTING_CLUSTERS
}

print(f"{'='*60}")
print(f"  Building {len(MISSING)} missing clusters (skipping {len(builder.CORPUS_QUERIES) - len(MISSING)} existing)")
print(f"{'='*60}")
for name, queries in MISSING.items():
    print(f"  {name:42s} {len(queries)} queries")
print(f"{'='*60}\n")

# Temporarily replace CORPUS_QUERIES with only missing clusters
builder.CORPUS_QUERIES = MISSING

# Run the build
import asyncio
asyncio.run(builder.build())
