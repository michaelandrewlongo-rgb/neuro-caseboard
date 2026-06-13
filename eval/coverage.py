"""Deterministic clinical-coverage metric for the attending ``must_cover`` items.

This is an *eval instrument*, not part of the product: for each must_cover item we
list distinctive clinical anchor terms; the item counts as covered if any anchor
appears in the board text. It gives a reproducible RED->GREEN signal for the
clinical-depth fix without spending judge-agent calls on every iteration. The final
quality grade is still the blind judge agent.

Usage:
    python3 eval/coverage.py [--root eval/_outputs_llm]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).parent

# case_id -> list of (label, [anchor substrings]); anchors are lowercased substrings.
ANCHORS = {
    "spine_acdf_c56": [
        ("recurrent laryngeal nerve", ["recurrent laryngeal", "tracheoesophageal", "hoarseness"]),
        ("carotid sheath lateral limit", ["carotid"]),
        ("esophageal perforation", ["perforation", "esophageal injury"]),
        ("cord/C6 root + SSEP/MEP monitoring", ["evoked potential", "ssep", "mep", "neuromonitor", "neuro-monitor"]),
        ("vertebral artery", ["vertebral artery"]),
        ("durotomy/CSF leak/OPLL", ["durotomy", "csf leak", "dural tear", "opll", "ossified", "lumbar drain"]),
        ("interbody graft/plate/lordosis", ["endplate", "interbody", "cage", "plate", "lordosis"]),
        ("C5 nerve root palsy", ["c5 palsy", "c5 nerve root palsy", "c5 root palsy", "c5 nerve root"]),
        ("neck hematoma -> airway rescue", ["hematoma", "airway", "reintubation", "evacuation"]),
    ],
    "skullbase_vs_retrosigmoid": [
        ("CN VII facial mapping/EMG", ["facial nerve", "cn vii", "facial emg"]),
        ("CN VIII cochlear ABR/hearing", ["cochlear", "abr", "baer", "hearing preservation", "cn viii"]),
        ("CN V trigeminal superior pole", ["trigeminal", "cn v "]),
        ("lower CN IX/X/XI caudal pole", ["lower cranial", "glossopharyngeal", "vagus", "accessory nerve"]),
        ("AICA loop preservation", ["aica", "anterior inferior cerebellar"]),
        ("IAC drilling/labyrinth/SCC", ["internal auditory canal", "iac", "labyrinth", "semicircular"]),
        ("brainstem/cerebellar retraction", ["brainstem", "cerebellar retraction"]),
        ("petrous air-cell CSF leak/bone wax", ["air cell", "bone wax", "pseudomeningocele"]),
        ("positioning/VAE if sitting", ["park-bench", "park bench", "lateral position", "semi-sitting", "sitting position", "air embolism"]),
    ],
    "functional_awake_glioma": [
        ("cortical language mapping/speech arrest", ["language mapping", "speech arrest", "naming", "broca", "anomia"]),
        ("subcortical tracts (arcuate/SLF/IFOF)", ["subcortical", "arcuate", "superior longitudinal", "ifof", "white matter tract"]),
        ("motor cortex/CST", ["motor cortex", "corticospinal"]),
        ("asleep-awake-asleep/scalp block/LMA", ["asleep-awake", "awake-asleep", "scalp block", "lma", "laryngeal mask"]),
        ("stimulation seizure -> iced saline rescue", ["iced saline", "cold saline", "cold ringer", "seizure", "after-discharge", "afterdischarge"]),
        ("functional/negative-mapping margins", ["negative mapping", "functional margin", "functional boundar"]),
        ("MCA/Sylvian vein preservation", ["sylvian", "cortical vein", "mca branch"]),
        ("neuronavigation/brain shift/US", ["neuronavigation", "brain shift", "intraoperative ultrasound"]),
        ("cooperation/anxiety/SMA syndrome", ["anxiety", "cooperation", "sma syndrome", "supplementary motor"]),
    ],
    "vascular_mca_clip": [
        ("proximal ICA/M1 control + temp clips", ["proximal control", "temporary clip", "m1"]),
        ("wide Sylvian split / M2 branches", ["sylvian", "m2"]),
        ("lenticulostriate perforators", ["lenticulostriate", "perforator"]),
        ("neck dissection / parent-vessel", ["aneurysm neck", "clip placement", "parent vessel", "parent-vessel"]),
        ("intraop rupture plan (two suckers)", ["intraoperative rupture", "premature rupture", "two suckers", "proximal clip"]),
        ("ICG / micro-Doppler", ["icg", "indocyanine", "videoangiography", "micro-doppler", "microvascular doppler", "flow probe"]),
        ("brain relaxation (lamina terminalis/mannitol/EVD)", ["lamina terminalis", "mannitol", "ventriculostomy", "cistern", "csf drainage"]),
        ("adenosine flow arrest", ["adenosine", "flow arrest", "rapid ventricular pacing"]),
        ("vasospasm/nimodipine + optic/chiasm", ["vasospasm", "nimodipine", "optic nerve", "chiasm"]),
    ],
    "neurooncology_convexity_meningioma": [
        ("Simpson I dural devascularization", ["simpson", "dural attachment", "devascular", "dural tail"]),
        ("MMA/ECA feeders + embolization", ["middle meningeal", "embolization", "feeding vessel", "feeders"]),
        ("cortical draining vein preservation", ["draining vein", "cortical vein", "bridging vein"]),
        ("blood loss/type & cross/large-bore IV", ["blood loss", "type and cross", "large-bore", "large bore"]),
        ("peritumoral edema/dexamethasone", ["edema", "dexamethasone", "steroid"]),
        ("internal debulking then capsule/pial plane", ["debulking", "capsule dissection", "pial plane", "piecemeal", "en bloc"]),
        ("dural reconstruction/cranioplasty/watertight", ["dural reconstruction", "duraplasty", "dural substitute", "cranioplasty", "watertight"]),
        ("seizure prophylaxis + early postop imaging", ["seizure prophylaxis", "antiepileptic", "levetiracetam", "postoperative imaging", "early imaging", "postoperative ct", "postoperative mri"]),
    ],
    "pediatric_posterior_fossa_medulloblastoma": [
        ("hydrocephalus EVD/ETV/CSF diversion", ["hydrocephalus", "evd", "etv", "external ventricular", "csf diversion", "shunt"]),
        ("telovelar approach / avoid mutism", ["telovelar", "vermian", "cerebellar mutism", "posterior fossa syndrome"]),
        ("4th-ventricle floor/facial colliculus", ["fourth ventricle floor", "facial colliculus", "floor of the fourth"]),
        ("lower CN IX/X/XII / bulbar", ["lower cranial", "glossopharyngeal", "hypoglossal", "bulbar", "swallow"]),
        ("PICA/tonsillar perforators", ["pica", "posterior inferior cerebellar", "tonsil"]),
        ("watertight closure/pseudomeningocele", ["watertight", "pseudomeningocele", "dural closure"]),
        ("prone/weight-based blood loss/VAE", ["prone", "air embolism", "weight-based", "weight based", "blood loss"]),
        ("oncologic staging (neuraxis MRI/CSF cytology)", ["neuraxis", "csf cytology", "staging", "leptomeningeal", "48 hour", "postoperative mri"]),
    ],
}


_INTERROGATIVE = ("what", "which", "how", "when", "should", "is ", "are ", "do ",
                  "does ", "can ", "would ", "could ", "where", "why ", "who ")


def declarative_text(board: str) -> str:
    """Return only the DECLARATIVE content of a board for honest coverage scoring.

    A card rendered as a question ("- ⚠ What role does ICG play…?") states no clinical
    fact, so counting its keywords inflates coverage. Drop any claim bullet that is a
    question (and its ``*Why:*`` line); keep declarative claims + their rationale."""
    out, skip_why = [], False
    for line in board.splitlines():
        s = line.strip()
        m = re.match(r"^- [⚠✓✗]\s+(.*)$", s)
        if m:
            claim = m.group(1).strip()
            low = claim.lower()
            is_q = claim.endswith("?") or low.startswith(_INTERROGATIVE)
            skip_why = is_q
            if not is_q:
                out.append(claim)
            continue
        if s.lower().startswith("*why:") or s.startswith("- *why"):
            if not skip_why:
                out.append(s)
            continue
        out.append(s)
    return "\n".join(out)


def score_board(text: str, items):
    low = declarative_text(text).lower()
    covered, missing = [], []
    for label, anchors in items:
        if any(a in low for a in anchors):
            covered.append(label)
        else:
            missing.append(label)
    return covered, missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(HERE / "_outputs_llm"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    root = Path(args.root)

    cases = json.loads((HERE / "cases.json").read_text())["cases"]
    total_cov = total_items = 0
    rows = []
    for c in cases:
        cid = c["id"]
        board = root / cid / "case-board.md"
        if not board.exists():
            print(f"  MISSING board: {board}")
            continue
        items = ANCHORS[cid]
        covered, missing = score_board(board.read_text(encoding="utf-8"), items)
        total_cov += len(covered)
        total_items += len(items)
        rows.append((cid, len(covered), len(items), missing))

    print(f"\n=== must_cover coverage @ {root} ===")
    for cid, n, t, missing in rows:
        print(f"{cid:44} {n:2}/{t}  ({100*n//t:3}%)")
        if not args.quiet and missing:
            for m in missing:
                print(f"      MISSING: {m}")
    if total_items:
        print(f"\nOVERALL: {total_cov}/{total_items} = {100*total_cov/total_items:.1f}% must_cover coverage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
