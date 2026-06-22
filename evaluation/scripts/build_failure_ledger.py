#!/usr/bin/env python3
"""Build failure-ledger.jsonl (atomic defect records) deterministically from baseline grades.

The graders already sorted each criticism into typed arrays, so each array maps to a controlled
taxonomy category without re-classifying free text. Only `missing_content` items get light keyword
routing (threshold / comparator / risk / patient-selection / retrieval-omission). Causal layer and
candidate files are assigned per category from the repository audit; causal_status stays `hypothesis`
until the root-cause step confirms.

Run:  python3 evaluation/scripts/build_failure_ledger.py \
        --grades evaluation/runs/baseline-20260620-134705/baseline-grades.jsonl \
        --out evaluation/failure-ledger.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Per-category causal layer + candidate files (hypotheses, from repository-audit.md).
LAYER = {
    "outdated_evidence": ("retrieval", ["neuro_caseboard/retrieve.py", "neuro_caseboard/literature/", "CORPUS_DIR"]),
    "retrieval_omission": ("retrieval", ["neuro_caseboard/retrieve.py", "neuro_caseboard/qa.py"]),
    "missing_decision_threshold": ("model_synthesis", ["neuro_caseboard/qa.py", "neuro_caseboard/prompt*"]),
    "missing_comparator": ("model_synthesis", ["neuro_caseboard/qa.py"]),
    "missing_risk_or_tradeoff": ("model_synthesis", ["neuro_caseboard/qa.py"]),
    "missing_patient_selection": ("model_synthesis", ["neuro_caseboard/qa.py"]),
    "incorrect_synthesis": ("model_synthesis", ["neuro_caseboard/qa.py"]),
    "unsupported_claim": ("model_synthesis", ["neuro_caseboard/answer_verify.py", "neuro_core/synthesize.py"]),
    "citation_claim_mismatch": ("citation_rendering", ["neuro_caseboard/qa.py"]),
    "overabsolute_language": ("prompting", ["neuro_caseboard/qa.py", "prompt assembly"]),
    "poor_question_decomposition": ("query_decomposition", ["neuro_core/query.py", "neuro_core/query_analyze.py"]),
    "disambiguation_failure": ("query_decomposition", ["neuro_core/query.py", "neuro_core/query_analyze.py", "evaluation/scripts/run_benchmark.py:choose_variant"]),
    "engine_reliability": ("infrastructure", ["neuro_caseboard/qa.py", "api/server.py"]),
    "other": ("unknown", []),
}

KW = [
    (re.compile(r"\b(threshold|cutoff|target|>|<|mm ?hg|map\b|cpp|icp|map\s*>|spo2|paco2)", re.I), "missing_decision_threshold"),
    (re.compile(r"\b(vs\.?|versus|compared|comparator|alternative|rather than|over)\b", re.I), "missing_comparator"),
    (re.compile(r"\b(risk|complication|morbidity|trade-?off|harm|adverse|disability)\b", re.I), "missing_risk_or_tradeoff"),
    (re.compile(r"\b(selection|candidate|patient[- ]selection|eligib|indication)\b", re.I), "missing_patient_selection"),
]


def route_missing(text: str) -> str:
    for rx, cat in KW:
        if rx.search(text):
            return cat
    return "retrieval_omission"


def excerpt(s: str, n: int = 240) -> str:
    s = " ".join(s.split())
    return s[:n]


def defects_for_grade(g: dict) -> list[dict]:
    qid = g["question_id"]
    out: list[dict] = []

    def add(idx: int, category: str, severity: str, basis: str, confidence: float):
        layer, files = LAYER.get(category, ("unknown", []))
        out.append({
            "defect_id": f"{qid}-{category}-{idx}",
            "question_id": qid,
            "category": category,
            "severity": severity,
            "answer_excerpt": excerpt(basis),
            "grader_basis": f"{g.get('letter_grade','?')}/{g.get('score','?')}: {excerpt(basis)}",
            "probable_layer": layer,
            "candidate_files": files,
            "confidence": confidence,
            "causal_status": "hypothesis",
            "recommended_action": "investigate",
        })

    for i, t in enumerate(g.get("safety_critical_errors") or []):
        add(i, "incorrect_synthesis", "safety_critical", t, 0.6)
    for i, t in enumerate(g.get("outdated_claims") or []):
        add(i, "outdated_evidence", "material", t, 0.8)
    for i, t in enumerate(g.get("important_inaccuracies") or []):
        # an inaccuracy that is explicitly about outdated evidence routes to outdated_evidence
        cat = "outdated_evidence" if re.search(r"\b(outdated|predates|RCT|trial|FDA|approv|2022|2023|2024|2025|published)\b", t, re.I) else "incorrect_synthesis"
        sev = "material"
        add(i, cat, sev, t, 0.7 if cat == "outdated_evidence" else 0.6)
    for i, t in enumerate(g.get("missing_content") or []):
        cat = route_missing(t)
        # if it references a named trial/modality the corpus lacks, it's really outdated/missing evidence
        if re.search(r"\b(RCT|trial|FDA|approv|guideline|consensus|2022|2023|2024|2025|ENRICH|SELECT2|ESCAPE|SANTE|RESCUE|ARUBA|JLGK)\b", t, re.I):
            cat = "outdated_evidence"
        add(i, cat, "material", t, 0.7)
    for i, t in enumerate(g.get("overabsolute_claims") or []):
        add(i, "overabsolute_language", "minor", t, 0.6)
    for i, t in enumerate(g.get("minor_incompleteness") or []):
        add(i, route_missing(t), "minor", t, 0.5)

    # status-level defects (not_gradable etc.)
    if g.get("letter_grade") == "Not gradable" or g.get("clinical_usability") == "not gradable":
        out.append({
            "defect_id": f"{qid}-disambiguation_failure-0",
            "question_id": qid,
            "category": "disambiguation_failure",
            "severity": "material",
            "answer_excerpt": excerpt(g.get("reason", "engine returned an empty/None answer after disambiguation")),
            "grader_basis": "Not gradable: empty answer after disambiguation narrowed question scope",
            "probable_layer": LAYER["disambiguation_failure"][0],
            "candidate_files": LAYER["disambiguation_failure"][1],
            "confidence": 0.7,
            "causal_status": "supported",
            "recommended_action": "investigate",
        })
    return out


def defects_for_run_row(row: dict) -> list[dict]:
    """Emit an `unsupported_claim` defect when the run row's verification flags ungrounded claims.

    The post-synthesis entailment verifier (`neuro_caseboard/answer_verify.py`) records, per answer,
    how many cited claims it could not entail against their cited source. One defect is emitted when
    `verification.n_unsupported > 0`; otherwise no defect (a grounded answer is not a failure).
    """
    out: list[dict] = []
    v = (row or {}).get("verification") or {}
    nu = v.get("n_unsupported", 0) or 0
    if nu <= 0:
        return out
    qid = row.get("question_id", "?")
    nc = v.get("n_cited_claims", 0) or 0
    markers = v.get("unsupported_markers", []) or []
    category = "unsupported_claim"
    layer, files = LAYER.get(category, ("unknown", []))
    out.append({
        "defect_id": f"{qid}-{category}-0",
        "question_id": qid,
        "category": category,
        "severity": "material",
        "answer_excerpt": excerpt(row.get("answer", "") or ""),
        "grader_basis": f"verification: {nu}/{nc} cited claims not entailed by cited source (markers: {', '.join(markers)})",
        "probable_layer": layer,
        "candidate_files": files,
        "confidence": 0.5,
        "causal_status": "hypothesis",
        "recommended_action": "investigate",
    })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grades", required=True)
    ap.add_argument("--run")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    grades = [json.loads(l) for l in Path(args.grades).read_text(encoding="utf-8").splitlines() if l.strip()]
    defects: list[dict] = []
    for g in grades:
        defects.extend(defects_for_grade(g))
    if args.run:
        run_rows = [json.loads(l) for l in Path(args.run).read_text(encoding="utf-8").splitlines() if l.strip()]
        for row in run_rows:
            defects.extend(defects_for_run_row(row))
    with Path(args.out).open("w", encoding="utf-8") as fh:
        for d in defects:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")

    # quick cluster print
    import collections
    by_cat = collections.Counter(d["category"] for d in defects)
    by_sev = collections.Counter(d["severity"] for d in defects)
    print(f"wrote {len(defects)} defects -> {args.out}")
    print("by severity:", dict(by_sev))
    print("by category:", dict(by_cat.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
