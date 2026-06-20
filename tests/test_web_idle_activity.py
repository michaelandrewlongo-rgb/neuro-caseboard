"""Guard tests for persistent page activity in the web console (BACKLOG P3 #10).

Static checks over web/src — no Node/browser. Codifies the P3 #10 confirmation: no hidden
polling/streaming, every setInterval is cleaned up, and the motion/visibility resource guards exist.
Runs under the pytest CI gate (the web console has no JS test runner in CI)."""
import re
from pathlib import Path

WEB_SRC = Path(__file__).resolve().parent.parent / "web" / "src"


def _all_sources():
    return list(WEB_SRC.rglob("*.tsx")) + list(WEB_SRC.rglob("*.ts"))


def test_no_hidden_polling_or_streaming_in_app_code():
    """No long-lived streams or background polling in app code (the dev-only Vite HMR socket is
    separate and absent from production builds)."""
    forbidden = ("new WebSocket", "new EventSource", "refetchInterval")
    offenders = []
    for f in _all_sources():
        text = f.read_text()
        for pat in forbidden:
            if pat in text:
                offenders.append(f"{f.relative_to(WEB_SRC)}: {pat}")
    assert not offenders, f"unexpected persistent-activity sources: {offenders}"


def test_every_setInterval_is_cleared():
    """Animation loaders may use setInterval, but each file must also clearInterval (no leaked
    timers that keep the page active after a component unmounts)."""
    for f in _all_sources():
        text = f.read_text()
        n_set = len(re.findall(r"\bsetInterval\s*\(", text))
        n_clear = len(re.findall(r"\bclearInterval\s*\(", text))
        assert n_set <= n_clear, f"{f.name}: {n_set} setInterval but {n_clear} clearInterval (leak)"


def test_reduced_motion_global_killswitch_present():
    css = (WEB_SRC / "index.css").read_text()
    assert "prefers-reduced-motion: reduce" in css
    assert "animation-iteration-count: 1 !important" in css


def test_background_tab_pause_guard_present():
    """A hidden tab must pause decorative animation (resource-bounded) — CSS keyed off
    data-doc-hidden, wired from App.tsx on visibilitychange with listener cleanup."""
    css = (WEB_SRC / "index.css").read_text()
    app = (WEB_SRC / "App.tsx").read_text()
    assert "data-doc-hidden" in css and "animation-play-state: paused !important" in css
    assert "visibilitychange" in app and "data-doc-hidden" in app
    assert "removeEventListener" in app
