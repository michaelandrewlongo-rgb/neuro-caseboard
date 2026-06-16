"""Live blind text-judge of case-dossier section *quality* vs eval/cases.json.

MANUAL, CREDENTIALED step — NOT part of the required offline CI. Needs a configured LLM provider
(``CASEBOARD_LLM_PROVIDER=vertex`` + ``GOOGLE_CLOUD_PROJECT`` + ADC, or ``openrouter``). It is the
deferred "blind text-judge of section quality" from WS-1/WS-2.

For each dictation in ``eval/case_dictations.json`` it:
  1. parses the dictation (LLM intake) -> ``build_case_dossier(use_llm=True, enrich=False,
     literature=False)`` -> the LLM-authored 8-section dossier,
  2. renders the dossier to markdown,
  3. asks a blind judge model (attending-examiner persona) to grade the dossier text against the
     expert rubric in ``eval/cases.json`` (``must_cover`` points + ``red_flags``): per-point
     coverage (covered/partial/missing), red-flag bleed, clinical accuracy, hallucinated specifics,
     and reasoning depth.

Coverage % is computed from the judge's per-point verdicts (covered=1, partial=0.5), which is more
reliable than a self-reported score. Writes ``eval/CASE_TEXT_JUDGE_REPORT_<date>.md``.

Caveat: when author and judge share a model (e.g. both Vertex gemini-2.5-pro) this is partly
self-grading; the per-point rubric grounding mitigates leniency. Noted in the report.

Usage:
    CASEBOARD_LLM_PROVIDER=vertex GOOGLE_CLOUD_PROJECT=<proj> python3 eval/live_text_judge.py
    python3 eval/live_text_judge.py --ids spine_acdf_c56,vascular_mca_clip   # subset
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))   # worktree source wins over any global install

from neuro_caseboard.intake import parse_dictation              # noqa: E402
from neuro_caseboard.pipeline import build_case_dossier, llm_enabled  # noqa: E402
from neuro_caseboard.render_md import render_markdown           # noqa: E402
from neuro_caseboard.explore_llm import _default_complete, _extract_json, _llm_provider  # noqa: E402


JUDGE_SYSTEM = (
    "You are a fellowship-trained attending neurosurgeon serving as a board examiner. You are "
    "grading a written pre-operative case dossier produced by a junior resident. Grade strictly and "
    "blindly: you do not know who or what produced it. Reward only content that is explicitly present "
    "in the dossier text; do not give credit for what a competent surgeon would 'obviously' know but "
    "the text omits. Penalize fabricated specifics (invented measurements, made-up trial names, "
    "citations that look fake) and any content that belongs to a different operation than the one "
    "stated. Reply with a single JSON object and nothing else."
)


def _judge_user(case_query: str, must_cover: list[str], red_flags: list[str], dossier_md: str) -> str:
    mc = "\n".join(f"  M{i+1}. {p}" for i, p in enumerate(must_cover))
    rf = "\n".join(f"  R{i+1}. {p}" for i, p in enumerate(red_flags))
    return f"""CASE (the stated operation): {case_query}

EXPERT MUST-COVER CHECKLIST (each is a specific structure-at-risk, maneuver, or rescue the dossier
should explicitly address for THIS operation):
{mc}

RED-FLAG CONTENT (belongs to a DIFFERENT operation; must NOT appear in this dossier):
{rf}

DOSSIER UNDER REVIEW (markdown):
<<<
{dossier_md}
>>>

Return JSON exactly in this shape:
{{
  "must_cover": [
    {{"id": "M1", "status": "covered" | "partial" | "missing",
      "evidence": "<<=15-word quote/locus from the dossier, or why it's missing>"}}
    // ... one entry per checklist item M1..Mn, in order
  ],
  "red_flag_bleed": [
    {{"id": "R1", "present": true | false, "where": "<short locus if present, else ''>"}}
    // ... one entry per red flag
  ],
  "hallucinations": ["<specific fabricated/unsupported claim>", "..."],
  "scores": {{"coverage": 0-10, "accuracy": 0-10, "reasoning": 0-10, "safety": 0-10, "overall": 0-10}},
  "top_weaknesses": ["<concrete, actionable weakness>", "..."]
}}
- "covered": the dossier explicitly and correctly addresses the specific point.
- "partial": alluded to vaguely or only half-right.
- "missing": absent.
- safety = 10 only if zero red-flag bleed AND postoperative rescue/complication handling is sound.
"""


def grade_case(case: dict, dictation: str) -> dict:
    """Build the LLM dossier for one case and return the parsed judge verdict (+ raw + timings)."""
    t0 = time.time()
    ctx = parse_dictation(dictation)                 # LLM intake (active provider)
    dossier = build_case_dossier(ctx, enrich=False, use_llm=True, literature=False)
    md = render_markdown(dossier)
    t_build = time.time() - t0

    t0 = time.time()
    raw = _default_complete(JUDGE_SYSTEM,
                            _judge_user(case["case_query"], case["must_cover"],
                                        case.get("red_flags", []), md),
                            temperature=0.0)
    verdict = json.loads(_extract_json(raw))
    t_judge = time.time() - t0
    return {"verdict": verdict, "dossier_md": md, "t_build": t_build, "t_judge": t_judge,
            "n_sections": len(dossier.sections)}


def _coverage(verdict: dict, n_items: int) -> tuple[float, int, int, int]:
    rows = verdict.get("must_cover", [])
    cov = sum(1.0 for r in rows if r.get("status") == "covered")
    par = sum(1.0 for r in rows if r.get("status") == "partial")
    miss = sum(1 for r in rows if r.get("status") == "missing")
    pct = (cov + 0.5 * par) / n_items * 100 if n_items else 0.0
    return pct, int(cov), int(par), int(miss)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="", help="comma-separated case ids (default: all)")
    ap.add_argument("--tag", default="", help="suffix for the report filename (e.g. 'after')")
    args = ap.parse_args()

    if not llm_enabled():
        print(f"NO PROVIDER configured (provider={_llm_provider()!r}); this is the keyed step. "
              "Set CASEBOARD_LLM_PROVIDER=vertex + GOOGLE_CLOUD_PROJECT + ADC.", file=sys.stderr)
        return 2

    dictations = {d["id"]: d for d in
                  json.loads((HERE / "case_dictations.json").read_text())["dictations"]}
    cases = json.loads((HERE / "cases.json").read_text())["cases"]
    if args.ids:
        want = {x.strip() for x in args.ids.split(",") if x.strip()}
        cases = [c for c in cases if c["id"] in want]

    rows = []
    for case in cases:
        cid = case["id"]
        dct = dictations.get(cid, {}).get("dictation", case["case_query"])
        try:
            r = grade_case(case, dct)
        except Exception as e:                       # repair-and-continue: log, keep going
            print(f"[{cid}] ERROR {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
            rows.append({"id": cid, "sub": case["subspecialty"], "error": str(e)[:200]})
            continue
        v = r["verdict"]
        pct, cov, par, miss = _coverage(v, len(case["must_cover"]))
        bleed = [b for b in v.get("red_flag_bleed", []) if b.get("present")]
        sc = v.get("scores", {})
        rows.append({
            "id": cid, "sub": case["subspecialty"], "pct": pct, "cov": cov, "par": par, "miss": miss,
            "bleed": bleed, "scores": sc, "halluc": v.get("hallucinations", []),
            "weak": v.get("top_weaknesses", []), "missing_items": [
                (case["must_cover"][i] if i < len(case["must_cover"]) else mr.get("id"))
                for i, mr in enumerate(v.get("must_cover", [])) if mr.get("status") == "missing"],
            "t_build": r["t_build"], "t_judge": r["t_judge"]})
        print(f"[{cid:42}] coverage {pct:5.1f}%  ({cov}cov/{par}par/{miss}miss)  "
              f"overall {sc.get('overall','?')}/10  bleed={len(bleed)}  "
              f"build {r['t_build']:.0f}s judge {r['t_judge']:.0f}s")

    graded = [r for r in rows if "error" not in r]
    mean_cov = sum(r["pct"] for r in graded) / len(graded) if graded else 0.0
    mean_overall = (sum(float(r["scores"].get("overall", 0) or 0) for r in graded) / len(graded)
                    if graded else 0.0)
    total_bleed = sum(len(r["bleed"]) for r in graded)

    today = dt.date.today().isoformat()
    tag = f"_{args.tag}" if args.tag else ""
    report = HERE / f"CASE_TEXT_JUDGE_REPORT_{today}{tag}.md"
    L = [
        f"# Live Blind Text-Judge — case-dossier quality vs `cases.json` ({today})", "",
        f"Provider: **{_llm_provider()}**.  Reproduce: "
        f"`CASEBOARD_LLM_PROVIDER={_llm_provider()} GOOGLE_CLOUD_PROJECT=<proj> "
        f"python3 eval/live_text_judge.py`.", "",
        "Each dictation -> LLM-authored 8-section dossier (`enrich=False, literature=False`) -> a "
        "blind attending-examiner judge grades coverage of every `must_cover` point, red-flag bleed, "
        "accuracy, reasoning, and hallucinations. Coverage% is computed from per-point verdicts "
        "(covered=1, partial=0.5). **Caveat:** author and judge share the provider model, so this is "
        "partly self-grading; the per-point rubric grounding mitigates leniency.", "",
        "| case | subspecialty | coverage | cov/par/miss | overall | accuracy | safety | bleed | halluc |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if "error" in r:
            L.append(f"| {r['id']} | {r['sub']} | ERROR | — | — | — | — | — | {r['error']} |")
            continue
        s = r["scores"]
        L.append(f"| {r['id']} | {r['sub']} | {r['pct']:.0f}% | {r['cov']}/{r['par']}/{r['miss']} "
                 f"| {s.get('overall','?')} | {s.get('accuracy','?')} | {s.get('safety','?')} "
                 f"| {len(r['bleed'])} | {len(r['halluc'])} |")
    L += ["", "## Aggregate",
          f"- Mean must-cover coverage: **{mean_cov:.1f}%**",
          f"- Mean overall (judge): **{mean_overall:.1f}/10**",
          f"- Total red-flag bleed incidents: **{total_bleed}**", ""]
    for r in graded:
        L.append(f"### {r['id']} — {r['pct']:.0f}% coverage, overall {r['scores'].get('overall','?')}/10")
        if r["missing_items"]:
            L.append("**Missing must-cover:**")
            L += [f"- {m}" for m in r["missing_items"]]
        if r["bleed"]:
            L.append("**Red-flag bleed:** " + "; ".join(
                f"{b.get('id')} @ {b.get('where','')}" for b in r["bleed"]))
        if r["halluc"]:
            L.append("**Hallucinations:** " + "; ".join(r["halluc"]))
        if r["weak"]:
            L.append("**Top weaknesses:**")
            L += [f"- {w}" for w in r["weak"]]
        L.append("")
    report.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\nMean coverage {mean_cov:.1f}% | mean overall {mean_overall:.1f}/10 | "
          f"bleed {total_bleed} | wrote {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
