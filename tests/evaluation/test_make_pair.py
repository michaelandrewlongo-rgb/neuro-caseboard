import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "make_pair", REPO / "evaluation" / "scripts" / "make_pair.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_render_pair_orders_hard_first_and_includes_both_answers():
    control = {"EASY-01": {"question": "qe", "answer": "ctrl easy"},
               "NIS-02": {"question": "qh", "answer": "ctrl hard"}}
    arm = {"EASY-01": {"question": "qe", "answer": "arm easy"},
           "NIS-02": {"question": "qh", "answer": "arm hard"}}
    md = mod.render_pair(control, arm, {"NIS-02"}, "RERANK_K=20")
    assert "RERANK_K=20" in md
    # hard section appears before easy section
    assert md.index("NIS-02") < md.index("EASY-01")
    # both answers present for each question
    for token in ("ctrl hard", "arm hard", "ctrl easy", "arm easy"):
        assert token in md
