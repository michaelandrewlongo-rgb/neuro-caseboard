"""Hermetic unit tests for progress/latency feedback (app/progress.py), BACKLOG P3 #8.

Pure logic with an injected clock — no Streamlit, engine, or network. `app/` is a bare-import dir."""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from progress import (ProgressTracker, STAGES, STAGE_LABEL, out_of_scope)  # noqa: E402


class _Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def test_advance_is_monotonic_and_ignores_backward():
    c = _Clock()
    p = ProgressTracker(clock=c)
    p.advance("synthesis")
    assert p.current == "synthesis"
    p.advance("retrieval")           # earlier stage -> ignored (no backward looping)
    assert p.current == "synthesis"
    p.advance("verification")        # later stage -> moves forward
    assert p.current == "verification"


def test_label_maps_current_stage():
    p = ProgressTracker(clock=_Clock())
    p.advance("literature")
    assert p.label() == STAGE_LABEL["literature"]


def test_elapsed_tracks_injected_clock():
    c = _Clock()
    p = ProgressTracker(clock=c)
    c.t = 42.5
    assert p.elapsed() == 42.5


def test_fraction_progresses_and_completes():
    p = ProgressTracker(clock=_Clock())
    assert p.fraction() == 0.0
    p.advance(STAGES[0])
    assert 0.0 < p.fraction() < 1.0
    p.complete()
    assert p.fraction() == 1.0 and p.current == STAGES[-1]


def test_out_of_scope_only_when_no_sources_or_figures():
    assert out_of_scope(0, 0) is True
    assert out_of_scope(2, 0) is False
    assert out_of_scope(0, 1) is False
