"""Live blind IMAGE-judge of generated case schematics (vision model).

MANUAL, CREDENTIALED step — NOT part of the required offline CI. The deferred "blind image-opening
judge (>=8/10 conceptual + case-specificity)" from WS-4.

Pipeline per case (from ``eval/case_dictations.json`` ground truth):
  CaseContext -> ``generate_case_figures`` (the real product renderer; figure specs authored by the
  active provider, e.g. Vertex Gemini — FREE GCP credit) -> PNG schematics -> a blind VISION judge
  (OpenRouter, e.g. ``openai/gpt-4o``) opens each PNG and grades conceptual correctness, anatomical
  plausibility, case-specificity (correct side/level/region), label legibility, and whether it reads
  as a schematic (with the mandatory "NOT A RADIOGRAPH" disclaimer). Target: overall >=8/10.

Cost control: ONLY the judge uses OpenRouter (paid). Each call requests ``usage.include`` so
OpenRouter returns the dollar cost; the harness accumulates it and HARD-STOPS before ``--budget``
(default $3.00 total) is exceeded. Figure generation uses the (free) Vertex/Gemini path.

Usage (key sourced into env by the caller, never printed):
    OPENROUTER_API_KEY=... CASEBOARD_LLM_PROVIDER=vertex GOOGLE_CLOUD_PROJECT=<p> \
        python3 eval/live_image_judge.py --budget 3.0 --model openai/gpt-4o
    python3 eval/live_image_judge.py --ids spine_acdf_c56,vascular_mca_clip --max-figs 1
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))   # worktree source wins over any global install

from neuro_caseboard.case_context import CaseContext            # noqa: E402
from neuro_caseboard.figures_gen import generate_case_figures   # noqa: E402

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

JUDGE_SYSTEM = (
    "You are a neurosurgical illustration reviewer. You are shown a single GENERATED SCHEMATIC "
    "(a code-drawn diagram, NOT a radiograph or photograph) intended to help a surgeon conceptualize "
    "one specific case. Grade it strictly and blindly against the stated case. A schematic is allowed "
    "to be simple/abstract — judge conceptual correctness and case-specificity, not artistic detail. "
    "Penalize wrong laterality, wrong level/region, mislabeled or illegible text, anatomically "
    "implausible layout, or anything that could be mistaken for a real radiograph. Reply with ONE "
    "JSON object and nothing else."
)


def _judge_user(expect: dict, caption: str) -> str:
    return f"""STATED CASE:
- procedure: {expect.get('procedure','')}
- pathology: {expect.get('pathology','')}
- laterality (expected side): {expect.get('laterality','') or 'n/a'}
- level (expected spinal level): {expect.get('level','') or 'n/a'}
- region/location: {expect.get('location','') or 'n/a'}
- figure caption shown to the surgeon: {caption}

Grade the schematic. Return JSON exactly:
{{
  "scores": {{
    "conceptual": 0-10,        // does it depict the right concept for this operation/anatomy?
    "case_specificity": 0-10,  // does it reflect the correct side/level/region for THIS case?
    "plausibility": 0-10,      // anatomically/spatially plausible layout
    "labels": 0-10,            // labels legible, correct, not overlapping
    "is_schematic": 0-10,      // clearly a schematic w/ disclaimer, not mistakable for a radiograph
    "overall": 0-10
  }},
  "side_correct": true | false | "n/a",
  "level_region_correct": true | false | "n/a",
  "issues": ["<concrete defect>", "..."],
  "verdict": "pass" | "fail"   // pass iff overall >= 8
}}"""


def _img_data_url(path: str) -> str:
    b = Path(path).read_bytes()
    return "data:image/png;base64," + base64.b64encode(b).decode("ascii")


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        import re
        m = re.search(r"\{.*\}", text or "", re.DOTALL)
        return json.loads(m.group(0)) if m else {"scores": {}, "issues": ["unparseable judge reply"]}


def judge_image_vertex(path: str, expect: dict, caption: str, *, model: str = "gemini-2.5-pro"):
    """One Vertex (Gemini multimodal) vision grade. Returns (verdict, cost=0.0) — spends GCP
    free credit, not a paid key. Auth via ADC + GOOGLE_CLOUD_PROJECT (same as explore_llm)."""
    from google import genai
    from google.genai import types
    client = genai.Client(vertexai=True, project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                          location=os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1")
    png = Path(path).read_bytes()
    resp = client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=[
            types.Part.from_text(text=_judge_user(expect, caption)),
            types.Part.from_bytes(data=png, mime_type="image/png")])],
        config=types.GenerateContentConfig(system_instruction=JUDGE_SYSTEM, temperature=0.0,
                                           response_mime_type="application/json"),
    )
    return _parse_json(resp.text or ""), 0.0


def judge_image(path: str, expect: dict, caption: str, *, model: str, timeout: int = 120):
    """One OpenRouter vision call. Returns (verdict_dict, cost_usd). Raises on transport error."""
    import requests
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": _judge_user(expect, caption)},
                {"type": "image_url", "image_url": {"url": _img_data_url(path)}},
            ]},
        ],
        "temperature": 0.0,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
        "usage": {"include": True},      # ask OpenRouter to return the dollar cost
    }
    headers = {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json",
        "X-Title": "neuro-caseboard-imagejudge",
    }
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    cost = float((data.get("usage") or {}).get("cost", 0.0) or 0.0)
    try:
        verdict = json.loads(content)
    except Exception:
        import re
        m = re.search(r"\{.*\}", content, re.DOTALL)
        verdict = json.loads(m.group(0)) if m else {"scores": {}, "issues": ["unparseable judge reply"]}
    return verdict, cost


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="", help="comma-separated case ids (default: all)")
    ap.add_argument("--backend", default="vertex", choices=("vertex", "openrouter"),
                    help="vision-judge backend (default: vertex / Gemini multimodal on GCP credit)")
    ap.add_argument("--model", default="",
                    help="judge model (default: gemini-2.5-pro for vertex, a free VL model for "
                         "openrouter)")
    ap.add_argument("--budget", type=float, default=3.0, help="hard USD cap (openrouter backend)")
    ap.add_argument("--max-figs", type=int, default=2, help="figures graded per case")
    ap.add_argument("--tag", default="", help="report filename suffix (e.g. 'after')")
    ap.add_argument("--outdir", default="", help="dir to keep rendered PNGs (default: temp)")
    args = ap.parse_args()

    if not args.model:
        args.model = ("gemini-2.5-pro" if args.backend == "vertex"
                      else "nvidia/nemotron-nano-12b-v2-vl:free")
    if args.backend == "vertex" and not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        print("GOOGLE_CLOUD_PROJECT not set — needed for the vertex backend.", file=sys.stderr)
        return 2
    if args.backend == "openrouter" and not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY not set — source it from your env file first.", file=sys.stderr)
        return 2
    margin = 0.05   # leave headroom so we never cross the cap mid-call (openrouter)

    dictations = json.loads((HERE / "case_dictations.json").read_text())["dictations"]
    if args.ids:
        want = {x.strip() for x in args.ids.split(",") if x.strip()}
        dictations = [d for d in dictations if d["id"] in want]

    out_root = Path(args.outdir) if args.outdir else Path(tempfile.mkdtemp(prefix="imgjudge_"))
    out_root.mkdir(parents=True, exist_ok=True)

    spent = 0.0
    rows = []
    stopped = False
    for d in dictations:
        cid = d["id"]
        gt = dict(d["ground_truth"])
        gt.setdefault("procedure", "")
        case = CaseContext.from_dict({**gt, "presentation": d["dictation"]})
        figdir = out_root / cid
        figdir.mkdir(parents=True, exist_ok=True)
        try:
            items = generate_case_figures(case, figdir)      # provider-authored specs (free Vertex)
        except Exception as e:
            print(f"[{cid}] figure-gen ERROR {type(e).__name__}: {str(e)[:160]}", file=sys.stderr)
            rows.append({"id": cid, "error": f"figgen: {str(e)[:160]}"})
            continue
        items = items[: args.max_figs]
        if not items:
            rows.append({"id": cid, "error": "no figures generated"})
            continue
        for it in items:
            if args.backend == "openrouter" and spent + margin >= args.budget:
                print(f"BUDGET STOP: spent ${spent:.4f} of ${args.budget:.2f}; not grading more.",
                      file=sys.stderr)
                stopped = True
                break
            t0 = time.time()
            try:
                if args.backend == "vertex":
                    verdict, cost = judge_image_vertex(it.image_path, gt, it.caption, model=args.model)
                else:
                    verdict, cost = judge_image(it.image_path, gt, it.caption, model=args.model)
            except Exception as e:
                print(f"[{cid}] judge ERROR {type(e).__name__}: {str(e)[:160]}", file=sys.stderr)
                rows.append({"id": cid, "img": Path(it.image_path).name,
                             "error": f"judge: {str(e)[:160]}"})
                continue
            spent += cost
            sc = verdict.get("scores", {})
            overall = sc.get("overall")
            if not isinstance(overall, (int, float)):     # some models omit the roll-up
                subs = [sc.get(k) for k in ("conceptual", "case_specificity", "plausibility",
                                            "labels", "is_schematic")]
                subs = [x for x in subs if isinstance(x, (int, float))]
                overall = round(sum(subs) / len(subs), 1) if subs else None
                sc["overall"] = overall
            rows.append({
                "id": cid, "img": Path(it.image_path).name, "caption": it.caption,
                "scores": sc, "overall": overall,
                "side": verdict.get("side_correct"), "lvl": verdict.get("level_region_correct"),
                "issues": verdict.get("issues", []), "verdict": verdict.get("verdict"),
                "cost": cost, "path": it.image_path})
            print(f"[{cid:42}] {Path(it.image_path).name:18} overall {sc.get('overall','?')}/10 "
                  f"side={verdict.get('side_correct')} lvl={verdict.get('level_region_correct')} "
                  f"${cost:.4f} (cum ${spent:.4f}) {time.time()-t0:.0f}s")
        if stopped:
            break

    graded = [r for r in rows if "scores" in r and isinstance(r.get("overall"), (int, float))]
    mean_overall = sum(r["overall"] for r in graded) / len(graded) if graded else 0.0
    n_pass = sum(1 for r in graded if (r["overall"] or 0) >= 8)

    today = dt.date.today().isoformat()
    tag = f"_{args.tag}" if args.tag else ""
    report = HERE / f"CASE_IMAGE_JUDGE_REPORT_{today}{tag}.md"
    L = [
        f"# Live Blind Image-Judge — generated schematics ({today})", "",
        f"Vision judge: **{args.model}** ({args.backend}). Figure specs authored by the active "
        f"provider ({os.environ.get('CASEBOARD_LLM_PROVIDER','?')}); rendered by the deterministic "
        "PIL renderer. Each PNG graded blindly for conceptual correctness, case-specificity "
        "(side/level/region), plausibility, labels, and schematic-clarity. Pass = overall >=8/10.", "",
        (f"**OpenRouter spend: ${spent:.4f} of ${args.budget:.2f} cap"
         + ("  — BUDGET STOP hit (some figures ungraded)." if stopped else ".") + "**"
         if args.backend == "openrouter"
         else "**Cost: $0 — graded on Vertex/Gemini (GCP free credit).**"), "",
        "| case | image | overall | concept | case-spec | plaus | labels | schem | side | lvl | $ |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if "error" in r:
            L.append(f"| {r['id']} | {r.get('img','—')} | ERROR | | | | | | | | {r['error']} |")
            continue
        s = r["scores"]
        L.append(f"| {r['id']} | {r['img']} | {s.get('overall','?')} | {s.get('conceptual','?')} "
                 f"| {s.get('case_specificity','?')} | {s.get('plausibility','?')} "
                 f"| {s.get('labels','?')} | {s.get('is_schematic','?')} | {r['side']} | {r['lvl']} "
                 f"| {r['cost']:.4f} |")
    L += ["", "## Aggregate",
          f"- Figures graded: **{len(graded)}**",
          f"- Mean overall: **{mean_overall:.1f}/10**",
          f"- Passing (>=8/10): **{n_pass}/{len(graded)}**",
          f"- OpenRouter spend: **${spent:.4f}** of ${args.budget:.2f} cap", ""]
    for r in graded:
        if r["issues"]:
            L.append(f"### {r['id']} / {r['img']} — overall {r['overall']}/10")
            L.append(f"caption: {r.get('caption','')}")
            L += [f"- {i}" for i in r["issues"]]
            L.append("")
    report.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\nGraded {len(graded)} | mean {mean_overall:.1f}/10 | pass {n_pass}/{len(graded)} | "
          f"spent ${spent:.4f}/{args.budget:.2f} | PNGs in {out_root} | wrote {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
