"""`caseboard` command-line entry point: ask cited questions and build pre-op dossiers."""

from __future__ import annotations

import argparse
import sys

from neuro_caseboard.pipeline import generate, generate_case, render_ask_pdf, _slug
from neuro_caseboard.model import fallback_notice


def _answer_question(question, force=False):
    from neuro_caseboard.qa import answer_question
    return answer_question(question, force=force)


def _run_ask(args) -> int:
    from neuro_core.gpu_guard import GpuNotReadyError
    from neuro_core.query import Clarification
    try:
        result = _answer_question(args.question, force=args.force)
    except GpuNotReadyError as e:
        print(f"GPU not ready: {e}", file=sys.stderr)
        return 1
    if isinstance(result, Clarification):
        print("This question is ambiguous. Did you mean one of these variants?")
        for v in result.variants:
            print(f"  - {v.label}")
        print("\nRe-ask naming the variant you want.")
        return 0
    print(result.answer)
    print("\nSources:")
    for c in result.citations:
        loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
        print(f"  [{c.n}] {loc}")
    lit = getattr(result, "literature", None)
    if lit and lit.citations:
        print("\nContemporary Literature:")
        if lit.narrative:  # separate mode carries a standalone narrative; woven mode does not
            print(lit.narrative)
        for c in lit.citations:
            link = f"https://doi.org/{c.doi}" if c.doi else c.url
            print(f"  [L{c.n}] {c.title} — {c.journal} {c.year or ''} · {link}")
    if result.figures:
        print("\nFigures:")
        for f in result.figures:
            print(f"  [{f.source_n}] {f.book}, p.{f.page} -> {f.image_path}")
    import os
    if os.environ.get("CASEBOARD_VERIFY_DISPLAY", "1") != "0":
        from neuro_caseboard.answer_verify import verification_notice
        _note = verification_notice(getattr(result, "verification", None))
        if _note:
            print(_note)
    if getattr(args, "pdf", False):
        out_path = args.output or f"ask-{_slug(args.question)}.pdf"
        render_ask_pdf(result, args.question, out_path)
        print(f"\nWrote {out_path}")
    return 0


def _run_build(args) -> int:
    out = args.output or f"{_slug(args.topic)}-caseboard"
    dossier, artifacts = generate(
        args.topic, output_dir=out, pdf=args.pdf, enrich=not args.no_enrich,
        use_llm=False if args.no_llm else None)
    print(f"Wrote {artifacts['markdown']}")
    if "pdf" in artifacts:
        print(f"Wrote {artifacts['pdf']}")
    s = dossier.summary
    print(f"  {len(dossier.sections)} sections · "
          f"{s.supported} corpus-supported · {s.to_verify} to verify · "
          f"{s.quarantined} quarantined")
    prov = dossier.provenance
    print(f"  Explorer: {prov.source_label}")
    notice = fallback_notice(prov)
    if notice:
        print(f"  ⚠ {notice}")
    return 0


def _run_case(args) -> int:
    out = args.output or f"{_slug(args.dictation)}-case"
    case, dossier, artifacts = generate_case(
        args.dictation, output_dir=out, pdf=args.pdf, enrich=not args.no_enrich,
        use_llm=False if args.no_llm else None,
        literature=False if args.no_literature else None)
    missing = case.missing_critical()
    if missing:
        print("Note — for a sharper dossier, the dictation did not state: "
              + "; ".join(missing))
    print(f"Wrote {artifacts['markdown']}")
    if "pdf" in artifacts:
        print(f"Wrote {artifacts['pdf']}")
    s = dossier.summary
    figs = sum(len(sec.figures) for sec in dossier.sections)
    print(f"  {len(dossier.sections)} sections · {figs} figures · "
          f"{s.supported} corpus-supported · {s.to_verify} to verify · "
          f"{s.quarantined} quarantined")
    return 0


def _run_cards(args) -> int:
    from neuro_core.cards_query import cards_query, flagged_tags, CardsIndexNotBuilt
    try:
        res = cards_query(args.question, k=args.k)
    except CardsIndexNotBuilt as e:
        print(e, file=sys.stderr)
        return 1
    print("Personal board-review deck — not corpus-cited; verify against sources.")
    if not res.cards:
        print("No matching cards.")
        return 0
    for i, c in enumerate(res.cards, 1):
        deck = c.deck_name or c.deck_full or "cards"
        tags = f"  ·  {c.tags}" if c.tags else ""
        print(f"\n[{i}] ({deck}{tags})")
        if flagged_tags(c.tags):
            print("  ⚠ flagged in your deck as unverified")
        print(f"  Q: {c.question_text}")
        print(f"  A: {c.answer_text}")
        for p in c.image_paths:
            print(f"  img: {p}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="caseboard",
        description="Neurosurgical case prep: ask cited questions and build pre-op dossiers.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ask", help="Ask a cited clinical/anatomy question")
    a.add_argument("question", help="The clinical question, in quotes")
    a.add_argument("--force", action="store_true",
                   help="Run even if the GPU readiness guard fails.")
    a.add_argument("--pdf", action="store_true",
                   help="Also export the answer as a PDF briefing")
    a.add_argument("-o", "--output", default=None,
                   help="PDF output path (default ask-<slug>.pdf)")

    b = sub.add_parser("build", help="Build a dossier from a free-text case")
    b.add_argument("topic", help='Free-text case, e.g. "C5-6 corpectomy"')
    b.add_argument("-o", "--output", default=None, help="Output directory")
    b.add_argument("--pdf", action="store_true", help="Also export case-board.pdf")
    b.add_argument("--no-enrich", action="store_true",
                   help="Skip corpus enrichment (offline verify-only checklist)")
    b.add_argument("--no-llm", action="store_true",
                   help="Force the deterministic Explorer (skip the LLM case-specific Explorer)")

    cs = sub.add_parser("case", help="Build a patient-specific case dossier from a free-text dictation")
    cs.add_argument("dictation", help='Free-text clinical dictation for one patient, in quotes')
    cs.add_argument("-o", "--output", default=None, help="Output directory")
    cs.add_argument("--pdf", action="store_true", help="Also export case-dossier.pdf")
    cs.add_argument("--no-enrich", action="store_true",
                    help="Skip corpus enrichment (offline verify-only checklist)")
    cs.add_argument("--no-llm", action="store_true",
                    help="Force the deterministic intake + authors (no LLM)")
    cs.add_argument("--no-literature", action="store_true",
                    help="Skip the PubMed contemporary-literature lane")

    cards = sub.add_parser("cards", help="Search the board-review card bank")
    cards.add_argument("question", help="The question or keywords, in quotes")
    cards.add_argument("-k", type=int, default=6, help="How many cards to return")

    args = parser.parse_args(argv)
    if args.cmd == "ask":
        return _run_ask(args)
    if args.cmd == "build":
        return _run_build(args)
    if args.cmd == "case":
        return _run_case(args)
    if args.cmd == "cards":
        return _run_cards(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
