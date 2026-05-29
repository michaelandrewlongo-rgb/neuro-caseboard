#!/usr/bin/env python3
"""Build missing image bank clusters. Run: python3 -m caseprep.image_bank.run_build_missing"""
import os, sys

def load_dotenv(path):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip().strip('\r').strip('"').strip("'")
                    os.environ[k] = v  # override, don't setdefault — source may have injected \r
    except OSError:
        pass

load_dotenv("/mnt/c/Users/Michael/Desktop/PAPERS/.env")
load_dotenv(os.path.expanduser("~/.hermes/.env"))

from caseprep.image_bank import builder as bm

EXISTING = {
    "aneurysm_sah", "stroke_thrombectomy", "carotid_cervical_vascular",
    "avm_vascular_malformation", "intracranial_hemorrhage",
    "general_neurointerventional", "flow_diversion", "tumor_skull_base",
    "moyamoya", "venous_interventional", "cerebrovascular_other",
    "spine_interventional", "neurocritical_care",
    "pediatric_neurointerventional", "radiosurgery", "functional_epilepsy",
    "intracranial_atherosclerosis", "pterional_approach", "retrosigmoid_cpa",
    "transsphenoidal_skull_base", "far_lateral_craniovertebral",
    "ventricular_microsurgery", "brainstem_cerebellar",
    "white_matter_deep_nuclei", "cerebral_venous_anatomy",
}
MISSING = {k: v for k, v in bm.CORPUS_QUERIES.items() if k not in EXISTING}

ncbi_key = os.environ.get("NCBI_API_KEY") or os.environ.get("NCBI_API_KEY_2", "")

print("=" * 60, flush=True)
print(f"  Building {len(MISSING)} missing clusters (skipping {len(bm.CORPUS_QUERIES) - len(MISSING)} existing)", flush=True)
print("=" * 60, flush=True)
for name, queries in sorted(MISSING.items()):
    print(f"  {name:42s} {len(queries)} queries", flush=True)
print(f"  NCBI key: {'✓ loaded' if ncbi_key else '✗ not found (low rate limit)'}", flush=True)
print(flush=True)

bm.CORPUS_QUERIES = MISSING
bm.NCBI_API_KEY = ncbi_key if ncbi_key else ""
bm.REQUEST_DELAY = 0.12 if ncbi_key else 0.35

import asyncio
asyncio.run(bm.build())
