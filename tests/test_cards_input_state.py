"""Regression guards for Cards input-state synchronization (BACKLOG P4 #11).

Static checks over the web Cards page — no Node/browser (the behavioral logic is covered by the
vitest suite web/src/lib/cardsQuery.test.ts, which the pytest CI gate cannot run). These lock the
invariant that the visible input and internal state share a single source of truth."""
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
CARDS = WEB / "src" / "pages" / "Cards.tsx"
REDUCER = WEB / "src" / "lib" / "cardsQuery.ts"


def test_single_source_of_truth_reducer_exists():
    src = REDUCER.read_text()
    assert "cardsQueryReducer" in src
    # submitted must be DERIVED from question (cannot diverge from the visible input)
    assert "state.question.trim()" in src


def test_cards_uses_the_reducer_not_ad_hoc_state():
    src = CARDS.read_text()
    assert "cardsQueryReducer" in src and "useReducer" in src
    # the old desync-prone setters must be gone
    assert "setQuestion(" not in src and "setSubmitted(" not in src


def test_input_is_controlled_and_typing_dispatches_type():
    src = CARDS.read_text()
    assert "value={question}" in src                       # controlled input
    assert 'dispatch({ type: "type"' in src                # typing replaces via the reducer


def test_chip_selection_runs_and_syncs_the_input():
    src = CARDS.read_text()
    # chips submit through run(), which dispatches selectChip (syncs the visible input)
    assert "void run(h)" in src
    assert 'dispatch({ type: "selectChip"' in src
