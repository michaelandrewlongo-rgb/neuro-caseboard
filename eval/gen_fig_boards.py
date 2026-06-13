"""Generate the 3 figure-acceptance boards once (textbook grounding + figures on), into
eval/_fig_boards/<id>/case-board.md. Board *text* (the anatomy claims the figure lane keys
on) is independent of figure cropping, so the same boards drive both the page-image
baseline and the cropped-plate final eval.

Run with the LLM + textbook env set (quality-first on the GCP free credit):
    CASEPREP_TEXTBOOK=1 CASEBOARD_TEXTBOOK_FIGURES=1 \
    CASEBOARD_LLM_PROVIDER=vertex GOOGLE_CLOUD_PROJECT=<project> \
    python eval/gen_fig_boards.py
"""

import json
from pathlib import Path

from neuro_caseboard.pipeline import generate

HERE = Path(__file__).parent


def main() -> int:
    cases = json.loads((HERE / "figure_cases.json").read_text())["cases"]
    for c in cases:
        out = HERE / "_fig_boards" / c["id"]
        print(f"generating {c['id']} ...", flush=True)
        generate(c["query"], output_dir=str(out), pdf=False, enrich=True)
        md = out / "case-board.md"
        n = len(md.read_text(encoding="utf-8").splitlines()) if md.exists() else 0
        print(f"  wrote {md} ({n} lines)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
