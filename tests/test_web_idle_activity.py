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
    """No HIDDEN/perpetual streams or background polling in app code (the dev-only Vite HMR socket
    is separate and absent from production builds).

    The Ask answer stream is the one allowed EventSource: it is user-initiated and request-scoped
    (opened on submit, closed on the terminal `done` event and on unmount), so it is confined to
    the dedicated client (lib/api.ts) and its bounded lifecycle is asserted in
    test_ask_stream_is_bounded — not the perpetual background activity this guard forbids."""
    forbidden = ("new WebSocket", "refetchInterval")
    offenders = []
    for f in _all_sources():
        text = f.read_text()
        rel = f.relative_to(WEB_SRC).as_posix()
        for pat in forbidden:
            if pat in text:
                offenders.append(f"{rel}: {pat}")
        # EventSource is allowed only in the dedicated Ask stream client — nowhere else.
        if "new EventSource" in text and rel != "lib/api.ts":
            offenders.append(f"{rel}: new EventSource (only lib/api.ts may open the Ask stream)")
    assert not offenders, f"unexpected persistent-activity sources: {offenders}"


def test_ask_stream_is_bounded():
    """The Ask EventSource must be request-scoped, not perpetual: the consumer closes it on the
    terminal event and on unmount, so no stream survives navigation or a backgrounded tab."""
    ask = (WEB_SRC / "pages" / "Ask.tsx").read_text()
    assert ".close()" in ask, "Ask.tsx must close the EventSource (bounded lifecycle)"
    assert "return () => esRef.current?.close()" in ask, \
        "Ask.tsx must close the stream on unmount"


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
