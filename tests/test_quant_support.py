"""Hermetic unit tests for Ask quantitative-support extraction (app/quant_support.py), BACKLOG P2 #6.

Pure regex/parse — no Streamlit, engine, corpus, LLM, or network. `app/` is a bare-import script dir."""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from quant_support import (Metric, extract_metrics, has_quantitative_support,  # noqa: E402
                          unquantified_comparisons, summarize)


def test_extracts_percentages_counts_and_pvalues():
    text = ("Complete occlusion was achieved in 85% of patients (n=240). "
            "Retreatment occurred in 7.5% at 12 months. "
            "The difference was significant (p<0.01).")
    kinds = {m.kind for m in extract_metrics(text)}
    assert {"percent", "count", "pvalue", "duration"} <= kinds


def test_has_quantitative_support_true_and_false():
    assert has_quantitative_support("Mortality was 2.1%.") is True
    assert has_quantitative_support("This approach is generally preferred.") is False


def test_metric_carries_its_clause_and_value():
    [m] = [x for x in extract_metrics("Occlusion in 90% of cases.") if x.kind == "percent"]
    assert "90%" in m.value
    assert "Occlusion" in m.clause


def test_unquantified_comparison_is_flagged_only_without_numbers():
    text = ("Flow diverters achieve higher occlusion than coiling. "
            "Coiling has a 5% complication rate.")
    flags = unquantified_comparisons(text)
    assert any("higher occlusion" in f for f in flags)        # comparative, no number -> flagged
    assert all("5% complication" not in f for f in flags)     # quantified -> not flagged


def test_summarize_counts_by_kind():
    metrics = [Metric("a", "85%", "percent"), Metric("b", "n=10", "count"),
               Metric("c", "90%", "percent")]
    assert summarize(metrics) == {"percent": 2, "count": 1}


def test_ask_lane_renders_by_the_numbers(monkeypatch):
    """The Ask lane surfaces extracted metrics and flags unquantified comparisons, no exception.
    Hermetic: engine stubbed."""
    import pytest
    pytest.importorskip("streamlit")
    import neuro_caseboard.qa as qa

    class _Res:
        answer = ("Complete occlusion in 85% of patients (n=240). "
                  "Flow diverters achieve higher occlusion than coiling.")
        citations = []
        figures = []
        literature = None

    monkeypatch.setattr(qa, "answer_question", lambda question, **kw: _Res())

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=30)
    at.session_state["ask_q"] = "flow diverter vs coiling occlusion rates"
    at.run()
    assert len(at.exception) == 0
    blob = " ".join(m.value for m in at.markdown)
    assert "85%" in blob                      # extracted metric surfaced
    assert "higher occlusion" in blob         # unquantified comparison flagged
