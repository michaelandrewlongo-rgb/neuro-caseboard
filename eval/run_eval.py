"""Reproducible eval harness.

Runs every case in ``eval/cases.json`` through ``caseboard`` and writes a Markdown +
PDF board per case under ``eval/_outputs/<id>/``. The cases (and their must_cover /
red_flags grading ground truth) were authored by an attending-neurosurgeon agent; the
outputs were graded blind by a separate judge agent — see ``eval/JUDGMENT.md``.

Usage:
    python eval/run_eval.py            # offline (deterministic checklist)
    python eval/run_eval.py --enrich   # attach the local FTS5 corpus lane if available
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from neuro_caseboard.pipeline import generate, classify_profile

HERE = Path(__file__).parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--enrich", action="store_true", help="enable corpus enrichment")
    args = ap.parse_args()

    cases = json.loads((HERE / "cases.json").read_text())["cases"]
    out_root = HERE / "_outputs"
    out_root.mkdir(exist_ok=True)

    for c in cases:
        dossier, _ = generate(c["case_query"], output_dir=out_root / c["id"],
                              pdf=True, enrich=args.enrich)
        s = dossier.summary
        subitems = sum(len(cl.sub_items) for sec in dossier.sections for cl in sec.claims)
        print(f'{c["id"]:42} profile={classify_profile(c["case_query"]):10} '
              f'sections={len(dossier.sections)} '
              f'supported={s.supported} to_verify={s.to_verify} '
              f'quarantined={s.quarantined} checkboxes={subitems}')
    print(f"\nWrote boards to {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
