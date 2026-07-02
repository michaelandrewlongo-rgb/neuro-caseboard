#!/usr/bin/env python3
"""Out-of-sample judge validation of a claim verifier's verdicts on a saved benchmark run.

The gold set in evaluation/groundedness-gold-set.jsonl was labeled for the LEXICAL checker, and the
NLI threshold was TUNED on it — so precision measured there is in-sample. This harness builds a FRESH
blind gold set from the verifier's ACTUAL verdicts on a full run and scores it with an independent
frontier judge (distinct from the answer model AND the checker), giving an honest out-of-sample
flag-precision / false-pass estimate.

Two phases:

  prep  (free): run the verifier over every cited claim in a run.jsonl, then emit a blinded sample —
        ALL flagged claims (usually few) + a deterministic sample of passed claims — as a labeling
        set with the verdict hidden. Writes <out>/blind-set.jsonl and <out>/keymap.json.

  judge (paid): send each blinded claim + its cited premise to an OpenRouter frontier judge for a
        supported/partial/not verdict, blind to the checker. Live per-call token cost is accumulated
        against a hard --budget ceiling; the run stops before the next call would exceed it. Writes
        <out>/judge-labels.jsonl and prints the out-of-sample confusion.

Judge independence: default judge is an Anthropic/OpenAI model on OpenRouter — NOT glm-5.2 (answer),
NOT gemini (disambig), NOT the deberta NLI checker.

Examples:
  python3 evaluation/scripts/judge_verifier.py prep \
      --run evaluation/runs/pr50-groundedness-20260622-125141/run.jsonl \
      --nli tasksource/deberta-base-long-nli --threshold 0.2 \
      --passes 80 --out evaluation/runs/pr50-groundedness-20260622-125141/nli-validation
  python3 evaluation/scripts/judge_verifier.py judge \
      --out evaluation/runs/pr50-groundedness-20260622-125141/nli-validation \
      --judge anthropic/claude-sonnet-4.5 --budget 3.00
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from neuro_caseboard.answer_verify import _strip_markers, segment_claims  # noqa: E402
from neuro_caseboard.entailment import (  # noqa: E402
    LexicalVerifier, NLIVerifier, _content_tokens, should_cite, unsupported_entities,
)

JUDGE_SYSTEM = (
    "You are a careful citation-faithfulness judge for a neurosurgery reference tool. You are given "
    "a CLAIM and the SOURCE PASSAGE(S) it cites. Decide whether the passage(s) support the claim — "
    "judge ONLY from the passage text shown, not your own medical knowledge, and not whether the "
    "claim is medically true. Reply with exactly one JSON object: "
    '{\"verdict\": \"S\"|\"P\"|\"N\", \"reason\": \"<one sentence>\"} where '
    "S=supported (a careful reader agrees the claim follows from the passage), "
    "P=partial (part backed, part not, or the claim overstates the passage), "
    "N=not supported (passage is off-topic or says something different)."
)


def _premise_for(span, citations: dict) -> str:
    return " ".join(citations[m] for m in span.markers if citations.get(m))


def _verifier(nli: str | None, threshold: float):
    if nli:
        return NLIVerifier(nli, entail_threshold=threshold)
    return LexicalVerifier()


def prep(args) -> None:
    """Verdict every cited claim in the run, then emit a blinded sample for judging."""
    verifier = _verifier(args.nli, args.threshold)
    flagged, passed = [], []
    for line in Path(args.run).read_text().splitlines():
        rec = json.loads(line)
        if rec.get("status") != "completed" or not rec.get("answer"):
            continue
        citations = {str(c["n"]): c.get("text") or "" for c in rec.get("citations") or []}
        for span in segment_claims(rec["answer"]):
            if not span.markers:
                continue
            premise = _premise_for(span, citations)
            claim = _strip_markers(span.text)
            min_tok = getattr(verifier, "min_premise_tokens", 5)
            thin = len(_content_tokens(premise)) < min_tok
            supported = True if thin else should_cite(premise, claim, verifier)
            if supported and not thin and unsupported_entities(claim, premise):
                supported = False
            item = {"qid": rec.get("question_id"), "claim": claim, "premise": premise,
                    "verdict": "supported" if supported else "flagged"}
            (passed if supported else flagged).append(item)

    # ALL flags (they are the precision-critical minority) + a deterministic sample of passes.
    # Deterministic (no RNG): evenly-strided pick so the sample spans the whole run, and re-runs are
    # reproducible. Skip thin-premise passes so the judge always has real passage text to read.
    judgeable_passes = [p for p in passed if len(_content_tokens(p["premise"])) >= 5]
    n = min(args.passes, len(judgeable_passes))
    stride = max(1, len(judgeable_passes) // n) if n else 1
    sample_passes = judgeable_passes[::stride][:n]
    sample = flagged + sample_passes

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    keymap, blind = {}, []
    for i, item in enumerate(sample):
        key = f"{i:03d}"
        keymap[key] = {"qid": item["qid"], "checker_verdict": item["verdict"]}
        blind.append({"key": key, "qid": item["qid"], "claim": item["claim"],
                      "premise": item["premise"]})
    (out / "keymap.json").write_text(json.dumps(keymap, indent=1))
    (out / "blind-set.jsonl").write_text("".join(json.dumps(b) + "\n" for b in blind))
    print(f"total cited claims: {len(flagged) + len(passed)}  "
          f"flagged: {len(flagged)}  passed: {len(passed)} ({len(judgeable_passes)} judgeable)")
    print(f"blind set: {len(blind)} items ({len(flagged)} flags + {len(sample_passes)} passes) "
          f"-> {out}/blind-set.jsonl")
    _estimate_cost(blind)


def _estimate_cost(blind: list) -> None:
    # ~4 chars/token; add ~500-token system+overhead per call, ~120-token reply.
    in_toks = sum((len(b["premise"]) + len(b["claim"])) // 4 + 500 for b in blind)
    out_toks = 120 * len(blind)
    print(f"est. tokens: ~{in_toks:,} in + ~{out_toks:,} out over {len(blind)} calls "
          f"(price via `judge` phase's live OpenRouter lookup)")


def _openrouter_client():
    from openai import OpenAI
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY not set (in .env)")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)


def _price_per_token(client, model: str) -> tuple[float, float]:
    """(prompt, completion) USD per token from OpenRouter's model list; (0,0) if unavailable."""
    try:
        import urllib.request
        with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=20) as r:
            models = json.load(r)["data"]
        for m in models:
            if m["id"] == model:
                p = m.get("pricing", {})
                return float(p.get("prompt", 0)), float(p.get("completion", 0))
    except Exception as exc:
        print(f"  (pricing lookup failed: {exc}; cost tracked as 0)")
    return 0.0, 0.0


def judge(args) -> None:
    out = Path(args.out)
    blind = [json.loads(l) for l in (out / "blind-set.jsonl").read_text().splitlines() if l.strip()]
    client = _openrouter_client()
    p_in, p_out = _price_per_token(client, args.judge)
    print(f"judge: {args.judge}  price: ${p_in*1e6:.2f}/M in, ${p_out*1e6:.2f}/M out  "
          f"budget: ${args.budget:.2f}")

    labels_path = out / "judge-labels.jsonl"
    done = {}
    if labels_path.exists():  # resume: never re-pay for an already-judged claim
        for l in labels_path.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                done[r["key"]] = r
    spent = sum(r.get("cost", 0.0) for r in done.values())
    print(f"resuming: {len(done)} already judged, ${spent:.4f} spent")

    fh = labels_path.open("a")
    for b in blind:
        if b["key"] in done:
            continue
        # Stop BEFORE a call that could blow the budget (worst-case = this call's max cost estimate).
        est = ((len(b["premise"]) + len(b["claim"])) // 4 + 800) * p_in + 400 * p_out
        if spent + est > args.budget:
            print(f"  stopping at budget: ${spent:.4f} spent, next call ~${est:.4f} would exceed "
                  f"${args.budget:.2f}")
            break
        user = f"CLAIM:\n{b['claim']}\n\nSOURCE PASSAGE(S):\n{b['premise']}"
        resp = client.chat.completions.create(
            model=args.judge,
            messages=[{"role": "system", "content": JUDGE_SYSTEM},
                      {"role": "user", "content": user}],
            temperature=0, max_tokens=400,
        )
        u = resp.usage
        cost = (u.prompt_tokens * p_in) + (u.completion_tokens * p_out)
        spent += cost
        verdict = _parse_verdict(resp.choices[0].message.content)
        rec = {"key": b["key"], "qid": b["qid"], "judge_label": verdict,
               "raw": resp.choices[0].message.content, "cost": cost}
        fh.write(json.dumps(rec) + "\n")
        fh.flush()
        done[b["key"]] = rec
    fh.close()
    print(f"judged: {len(done)}/{len(blind)}  total cost: ${spent:.4f}")
    _score(out, done)


def _parse_verdict(text: str) -> str:
    try:
        obj = json.loads(text[text.index("{"):text.rindex("}") + 1])
        v = str(obj.get("verdict", "")).strip().upper()[:1]
        return v if v in ("S", "P", "N") else "?"
    except Exception:
        t = (text or "").strip().upper()
        return next((c for c in t if c in "SPN"), "?")


def _score(out: Path, done: dict) -> None:
    keymap = json.loads((out / "keymap.json").read_text())
    bad = lambda lbl: lbl in ("P", "N")
    flags = [(k, r) for k, r in done.items() if keymap[k]["checker_verdict"] == "flagged"]
    passes = [(k, r) for k, r in done.items() if keymap[k]["checker_verdict"] == "supported"]
    tf = sum(1 for _, r in flags if bad(r["judge_label"]))
    fp = sum(1 for _, r in passes if bad(r["judge_label"]))
    print("\n== OUT-OF-SAMPLE judge confusion (verifier verdict vs frontier judge) ==")
    print(f"flags judged: {len(flags)}  flag precision (judge agrees bad): "
          f"{tf}/{len(flags) or 1} = {tf / (len(flags) or 1):.2f}")
    print(f"passes judged: {len(passes)}  false-pass (judge says bad): "
          f"{fp}/{len(passes) or 1} = {fp / (len(passes) or 1):.3f}")
    for k, r in passes:
        if bad(r["judge_label"]):
            print(f"  FALSE PASS {k} ({r['judge_label']}) qid={r['qid']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep")
    p.add_argument("--run", required=True)
    p.add_argument("--nli", help="NLI model (omit for lexical)")
    p.add_argument("--threshold", type=float, default=0.2)
    p.add_argument("--passes", type=int, default=80, help="how many passed claims to sample")
    p.add_argument("--out", required=True)
    p.set_defaults(func=prep)
    j = sub.add_parser("judge")
    j.add_argument("--out", required=True)
    j.add_argument("--judge", default="anthropic/claude-sonnet-4.5")
    j.add_argument("--budget", type=float, default=3.00, help="hard USD ceiling")
    j.set_defaults(func=judge)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
