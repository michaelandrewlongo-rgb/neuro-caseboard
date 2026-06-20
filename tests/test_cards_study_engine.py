"""Regression guards for the Cards study engine (BACKLOG P4 #13).

The behavioral logic is covered by the vitest suite web/src/lib/srs.test.ts (run via `npm test` in
web/); CI is pytest-only, so these static checks lock in the study-engine surface: a spaced-repetition
scheduler and a persistent review store providing self-rating, the due queue, missed-card review,
and progress tracking."""
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "web" / "src" / "lib"


def test_srs_scheduler_module_present():
    src = (LIB / "srs.ts").read_text()
    for sym in ("export function newSchedule", "export function schedule", "export function isDue",
                'Rating = "again" | "hard" | "good" | "easy"'):
        assert sym in src, sym


def test_review_store_exposes_study_workflow():
    src = (LIB / "reviewStore.ts").read_text()
    # self-rating, due/new queue, missed-card review, progress tracking
    for sym in ("export function rate", "export function dueCardIds",
                "export function missedCardIds", "export function progress"):
        assert sym in src, sym
    # persistence is injectable (KVStorage) so it is testable and not hard-bound to localStorage
    assert "KVStorage" in src


def test_study_engine_has_vitest_spec():
    assert (LIB / "srs.test.ts").exists()
