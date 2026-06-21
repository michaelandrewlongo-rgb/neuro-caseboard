import pytest
pytest.importorskip("streamlit")

from app.streamlit_app import _should_show_literature


def test_show_literature_when_citations_present_woven():
    from types import SimpleNamespace
    lit = SimpleNamespace(narrative="", citations=[SimpleNamespace(n=1)])
    assert _should_show_literature(lit) is True


def test_show_literature_separate_mode():
    from types import SimpleNamespace
    lit = SimpleNamespace(narrative="Recent RCTs [L1].", citations=[SimpleNamespace(n=1)])
    assert _should_show_literature(lit) is True


def test_hide_literature_when_no_citations():
    from types import SimpleNamespace
    assert _should_show_literature(None) is False
    assert _should_show_literature(SimpleNamespace(narrative="", citations=[])) is False
