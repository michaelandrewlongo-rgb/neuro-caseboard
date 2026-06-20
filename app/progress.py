"""Monotonic pipeline-progress tracking for Ask/Build (BACKLOG P3 #8).

Pure + clock-injectable so the progress logic is unit-testable without Streamlit. Stages are
ordered; ``advance`` never moves backward (fixes the 'progress loops backward' defect); ``elapsed``
and ``fraction`` drive the UI. ``out_of_scope`` is an early low-corpus-overlap signal."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

STAGES = ("retrieval", "reranking", "synthesis", "literature", "verification")
STAGE_LABEL = {
    "retrieval": "Retrieving textbook passages",
    "reranking": "Reranking by relevance",
    "synthesis": "Synthesizing the answer",
    "literature": "Searching contemporary literature",
    "verification": "Verifying claims against sources",
}


@dataclass
class ProgressTracker:
    stages: tuple = STAGES
    clock: Callable[[], float] = time.monotonic
    _idx: int = field(default=-1, init=False)
    _start: float = field(default=0.0, init=False)
    _done: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._start = self.clock()

    def advance(self, stage: str) -> None:
        """Move to ``stage`` only if it is later than the current one (monotonic)."""
        i = self.stages.index(stage)  # ValueError on unknown stage = caller bug
        if i > self._idx:
            self._idx = i

    @property
    def current(self) -> str | None:
        return self.stages[self._idx] if 0 <= self._idx < len(self.stages) else None

    def label(self) -> str:
        c = self.current
        return STAGE_LABEL.get(c, "") if c else ""

    def elapsed(self) -> float:
        return self.clock() - self._start

    def fraction(self) -> float:
        if self._done:
            return 1.0
        return (self._idx + 1) / len(self.stages) if self._idx >= 0 else 0.0

    def complete(self) -> None:
        self._idx = len(self.stages) - 1
        self._done = True


def out_of_scope(n_sources: int, n_figures: int = 0) -> bool:
    """Early out-of-scope signal: the answer drew on no corpus sources or figures, i.e. the
    question has low overlap with the indexed textbooks."""
    return n_sources <= 0 and n_figures <= 0
