"""Figure-retrieval acceptance harness (decoupled from the slow LLM).

For each case in ``eval/figure_cases.json`` it reads a *generated* board's anatomy claims
and runs the figure lane (``build_figure_retriever`` + region guards) to produce the
figures the board would attach — then writes ``eval/FIGURE_REPORT.md`` for a blind
image-verifying judge to grade against ``figure_cases.json`` (domain correctness +
specific relevance).

First generate the three boards once (textbook + figures on), e.g.:
    CASEPREP_TEXTBOOK=1  python -c "from neuro_caseboard.pipeline import generate; \
        import json; \
        [generate(c['query'], output_dir=f'eval/_fig_boards/'+c['id'], pdf=False, enrich=True) \
         for c in json.load(open('eval/figure_cases.json'))['cases']]"
then:
    python eval/figure_eval.py            # default boards dir eval/_fig_boards
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from caseprep.explorer.question_manifest import QuestionCard, QuestionManifest
from neuro_caseboard.pipeline import _collect_figures
from neuro_caseboard.retrieve import build_figure_retriever

HERE = Path(__file__).parent
_SECT = {"Anatomy at Risk": "03-anatomy-at-risk.md", "Operative Plan": "04-operative-plan.md",
         "Risk and Rescue": "05-risk-and-rescue.md"}


def parse_cards(md: str):
    tf = "03-anatomy-at-risk.md"
    out = []
    for ln in md.splitlines():
        h = re.match(r"^## (.+)$", ln.strip())
        if h and h.group(1) in _SECT:
            tf = _SECT[h.group(1)]
            continue
        m = re.match(r"^- [✓⚠✗]\s+(.*)$", ln.strip())
        if m and not m.group(1).strip().endswith("?"):
            out.append((m.group(1).strip(), tf))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", default=str(HERE / "_fig_boards"))
    args = ap.parse_args()
    boards = Path(args.boards)

    cases = json.loads((HERE / "figure_cases.json").read_text())["cases"]
    figret = build_figure_retriever()
    print(f"figure rows loaded: {len(figret._rows) if figret else 0}")
    blocks = []
    for c in cases:
        board = boards / c["id"] / "case-board.md"
        if not board.exists():
            print(f"  MISSING board: {board} (generate it first)")
            continue
        cards = [QuestionCard(target_file=tf, section_key="neural_structures", question=q,
                              why_it_matters="", compiler_slot="x", answerability="x")
                 for q, tf in parse_cards(board.read_text(encoding="utf-8"))]
        ce, _ = _collect_figures(QuestionManifest(procedure_family="x", cards=cards),
                                 c["query"], figret=figret, max_total=8, per_card=1)
        figs = [(q[:60], r.metadata["citation"], r.metadata["caption"][:160],
                 r.metadata.get("figure_path", ""))
                for q, recs in ce.items() for r in recs]
        blocks.append(f"## {c['id']}\nQUERY: {c['query']}\nFIGURES ({len(figs)}):")
        for claim, cite, cap, path in figs:
            blocks.append(f"- [{cite}] {cap}\n    IMAGE: {path}\n    claim: {claim}")
        blocks.append("")
    txt = "\n".join(blocks)
    (HERE / "FIGURE_REPORT.md").write_text(txt, encoding="utf-8")
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
