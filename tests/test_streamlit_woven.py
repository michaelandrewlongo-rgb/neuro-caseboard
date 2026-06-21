import sys
from pathlib import Path
from types import SimpleNamespace

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from ask_literature import should_show_literature  # noqa: E402


def test_show_literature_when_citations_present_woven():
    lit = SimpleNamespace(narrative="", citations=[SimpleNamespace(n=1)])
    assert should_show_literature(lit) is True


def test_show_literature_separate_mode():
    lit = SimpleNamespace(narrative="Recent RCTs [L1].", citations=[SimpleNamespace(n=1)])
    assert should_show_literature(lit) is True


def test_hide_literature_when_no_citations():
    assert should_show_literature(None) is False
    assert should_show_literature(SimpleNamespace(narrative="", citations=[])) is False
