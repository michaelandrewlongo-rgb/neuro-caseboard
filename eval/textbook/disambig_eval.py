"""Eval the variant-disambiguation stage: conflation / over-ask / wrong-variant.

Pure metric functions (unit-tested) + a runner that needs the live corpus + Vertex.
Run:  python -m eval.textbook.disambig_eval --set eval/ambiguous_variants.yaml
"""
import argparse

from neuro_core.query import Clarification


def _answer_text(result):
    # A Clarification has no .answer -> "" -> conflation/wrong_variant treat it as clean.
    return getattr(result, "answer", "") or ""


def conflation(result, forbidden):
    """True if the answer mentions any forbidden (other-variant) term."""
    text = _answer_text(result).lower()
    return any(term.lower() in text for term in (forbidden or []))


def wrong_variant(result, expected_label):
    """True if a briefing was produced but does not name the expected variant."""
    if isinstance(result, Clarification) or not expected_label:
        return False
    return expected_label.lower() not in _answer_text(result).lower()


def over_ask(result, expect_ambiguous):
    """True if the engine clarified on a case that should NOT be ambiguous."""
    return isinstance(result, Clarification) and not expect_ambiguous


def main():
    import yaml
    from neuro_core.query import get_engine

    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="eval/ambiguous_variants.yaml")
    args = ap.parse_args()
    with open(args.set) as f:
        cases = yaml.safe_load(f)

    engine = get_engine()
    n = len(cases)
    confl = over = wrong = 0
    for c in cases:
        result = engine.query(c["question"])
        is_clar = isinstance(result, Clarification)
        cf = conflation(result, c.get("forbidden"))
        oa = over_ask(result, c.get("expect_ambiguous", False))
        wv = wrong_variant(result, c.get("expected_label"))
        confl += cf
        over += oa
        wrong += wv
        tag = "CLARIFY" if is_clar else "ANSWER"
        print(f"[{tag}] {c['question'][:60]}")
        print(f"    conflation={cf} over_ask={oa} wrong_variant={wv}")
    print(f"\nconflation_rate={confl}/{n}  over_ask_rate={over}/{n}  wrong_variant_rate={wrong}/{n}")
    print("Anchor: the DHC case must show conflation=False (0 bifrontal/Kjellberg mentions).")


if __name__ == "__main__":
    main()
