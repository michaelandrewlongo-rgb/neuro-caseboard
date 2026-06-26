#!/usr/bin/env python3
"""Warm the frozen PubMed cache over a manifest (Lane-B retrieval only; no synthesis).

retrieve_records() fetches + caches under the deterministic build_query_terms key, so a later
cache hit during the actual runs skips the LLM rewrite entirely — literature stays frozen.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_log = logging.getLogger(__name__)


def warm(questions, retrieve_fn):
    """Call retrieve_fn(question) for each (qid, question); return [(qid, n_records, ok)]."""
    out = []
    for qid, q in questions:
        try:
            recs, _ = retrieve_fn(q)
            out.append((qid, len(recs), True))
        except Exception as exc:  # noqa: BLE001 — one bad question must not abort warming
            _log.warning("warm: qid=%s failed: %r", qid, exc)
            out.append((qid, 0, False))
    return out


def _load_questions(manifest_path):
    rows = [json.loads(line) for line in Path(manifest_path).read_text(encoding="utf-8").splitlines()
            if line.strip()]
    return [(r["id"], r["question"]) for r in rows if r.get("enabled", True)]


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    manifest = args[0] if args else str(REPO / "evaluation" / "inputs" / "bakeoff-21.manifest.jsonl")

    from neuro_caseboard.literature.config import load_literature_config
    from neuro_caseboard.qa import retrieve_records
    from neuro_core.config import load_config
    from neuro_core.synth_clients import make_synth_client

    lit_config = load_literature_config()
    synth_client = make_synth_client(load_config())

    def retrieve_fn(q):
        return retrieve_records(q, lit_config=lit_config, synth_client=synth_client)

    results = warm(_load_questions(manifest), retrieve_fn)
    ok = sum(1 for _, _, good in results if good)
    print(f"[warm_pubmed] cache_dir={lit_config.cache_dir} ttl_days={lit_config.cache_ttl_days}")
    for qid, n, good in results:
        print(f"  {qid:<12} records={n:<3} {'ok' if good else 'FAILED'}")
    print(f"[warm_pubmed] {ok}/{len(results)} warmed")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
