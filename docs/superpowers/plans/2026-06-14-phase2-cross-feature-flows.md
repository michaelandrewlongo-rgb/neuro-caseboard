# Phase 2 — Cross-feature Flows + Shared Evidence Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the Ask and Build features: a Q&A answer can seed a board (LLM-extracted topic), a board card can seed a follow-up question, and a shared `EvidenceRef` model powers inline "also appears in…" badges — all wired at the app boundary, engines untouched.

**Architecture:** A new neutral `neuro_core.evidence` module (typed `EvidenceRef` + adapters + pure session helpers) and a `neuro_caseboard.topic_extract` LLM helper. The Streamlit app composes these; `query.py` and `pipeline.py` are not modified. All logic lives in tested helpers; the Streamlit script stays a thin view (verified by `py_compile`).

**Tech Stack:** Python 3.10+, Streamlit (`st.session_state` + `st.rerun` for cross-flow navigation), `neuro_core.synth_clients` (Vertex LLM), pytest.

**Spec:** `docs/superpowers/specs/2026-06-14-phase2-cross-feature-flows-design.md`

**Branch:** Execute on a new branch `phase2-cross-feature-flows` (not `master`). The controller creates it before Task 1.

**Baseline:** `master` @ `7df505c` (Phase 1 merged + this spec), 278 tests passing. After this plan: 278 + 6 (evidence) + 3 (topic_extract) = **287** passing.

---

## File Structure

- **Create** `neuro_core/evidence.py` — `EvidenceRef` + adapters + `record`/`other_features`.
- **Create** `tests/test_evidence.py` — model unit tests.
- **Create** `neuro_caseboard/topic_extract.py` — `extract_board_topic` (injectable client).
- **Create** `tests/test_topic_extract.py` — extraction unit tests (fake client).
- **Modify** `app/streamlit_app.py` — wire both flows + cross-link badges via the helpers.

---

## Task 1: Shared evidence model (`neuro_core/evidence.py`)

**Files:**
- Create: `neuro_core/evidence.py`
- Test: `tests/test_evidence.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_evidence.py`:

```python
from neuro_core.evidence import (
    EvidenceRef, from_citation, from_figure, from_figure_item, record, other_features,
)


class _C:
    def __init__(self, n, book, chapter, page):
        self.n, self.book, self.chapter, self.page = n, book, chapter, page


class _F:
    def __init__(self, source_n, book, chapter, page, image_path, caption):
        self.source_n, self.book, self.chapter = source_n, book, chapter
        self.page, self.image_path, self.caption = page, image_path, caption


class _FI:
    def __init__(self, fig_id, image_path, caption, citation):
        self.fig_id, self.image_path = fig_id, image_path
        self.caption, self.citation = caption, citation


def test_key_figure_vs_citation():
    assert EvidenceRef(figure_path="/x/p1.png").key == "fig:/x/p1.png"
    assert EvidenceRef(book="Rhoton", page=538).key == "cite:Rhoton|538"


def test_from_citation_maps_fields_and_key():
    r = from_citation(_C(1, "Greenberg", "Tumors", 792))
    assert r.book == "Greenberg" and r.page == 792 and r.chapter == "Tumors"
    assert r.citation == "Greenberg, p.792" and r.figure_path is None
    assert r.key == "cite:Greenberg|792" and r.source == "qa"


def test_from_figure_sets_figure_path_key():
    r = from_figure(_F(2, "Rhoton", "CPA", 538, "/x/p538.png", "AICA in the CPA"))
    assert r.figure_path == "/x/p538.png" and r.caption == "AICA in the CPA"
    assert r.citation == "Rhoton, p.538" and r.key == "fig:/x/p538.png"


def test_from_figure_item_keys_on_path_without_book_page():
    r = from_figure_item(_FI("F1", "/x/p538.png", "AICA in the CPA", "Rhoton, p.538"))
    assert r.figure_path == "/x/p538.png" and r.citation == "Rhoton, p.538"
    assert r.key == "fig:/x/p538.png" and r.source == "board"


def test_record_and_other_features_cross_link():
    store = {}
    record(store, [from_figure(_F(1, "Rhoton", "CPA", 538, "/x/p538.png", "cap"))], 'answer: "q"')
    record(store, [from_figure_item(_FI("F1", "/x/p538.png", "cap", "Rhoton, p.538"))], 'board: "t"')
    assert other_features(store, "fig:/x/p538.png", 'answer: "q"') == ['board: "t"']
    assert other_features(store, "fig:/x/p538.png", 'board: "t"') == ['answer: "q"']


def test_other_features_excludes_same_label_only():
    store = {}
    record(store, [from_figure(_F(1, "Rhoton", "", 540, "/x/p540.png", "c"))], 'answer: "q"')
    assert other_features(store, "fig:/x/p540.png", 'answer: "q"') == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_evidence.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'neuro_core.evidence'`

- [ ] **Step 3: Write the implementation**

Create `neuro_core/evidence.py`:

```python
"""Shared evidence model: a neutral, typed reference to one piece of cited evidence (a textbook
citation or a figure), used as the lingua franca for cross-feature flows. Q&A's Citation/Figure
and the board's FigureItem adapt to it at the app boundary; the engines are untouched."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceRef:
    book: str = ""
    page: int | None = None
    chapter: str = ""
    citation: str = ""
    figure_path: str | None = None
    caption: str = ""
    score: float | None = None
    source: str = ""

    @property
    def key(self) -> str:
        """Stable cross-link identity: figures by page-image path, citations by (book, page)."""
        if self.figure_path:
            return f"fig:{self.figure_path}"
        return f"cite:{self.book}|{self.page}"


def _cite_str(book, page) -> str:
    return f"{book}, p.{page}" if book else ""


def from_citation(c) -> EvidenceRef:
    return EvidenceRef(book=c.book, page=c.page, chapter=getattr(c, "chapter", "") or "",
                       citation=_cite_str(c.book, c.page), source="qa")


def from_figure(f) -> EvidenceRef:
    return EvidenceRef(book=f.book, page=f.page, chapter=getattr(f, "chapter", "") or "",
                       citation=_cite_str(f.book, f.page), figure_path=f.image_path,
                       caption=f.caption or "", source="qa")


def from_figure_item(fi) -> EvidenceRef:
    return EvidenceRef(citation=fi.citation or "", figure_path=fi.image_path,
                       caption=fi.caption or "", source="board")


def record(store: dict, refs, label: str) -> None:
    """Add `label` to the set of features each ref's key appears in."""
    for r in refs:
        store.setdefault(r.key, set()).add(label)


def other_features(store: dict, key: str, label: str) -> list[str]:
    """Feature labels (other than `label`) that this key appears in, sorted."""
    return sorted(lbl for lbl in store.get(key, set()) if lbl != label)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_evidence.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_core/evidence.py tests/test_evidence.py
git commit -m "feat(core): shared EvidenceRef model + adapters + session cross-link helpers"
```

---

## Task 2: LLM topic extraction (`neuro_caseboard/topic_extract.py`)

**Files:**
- Create: `neuro_caseboard/topic_extract.py`
- Test: `tests/test_topic_extract.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_topic_extract.py`:

```python
from neuro_caseboard.topic_extract import extract_board_topic


class _FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def generate(self, system, user, images):
        self.calls.append((system, user, images))
        return self.reply


def test_extract_returns_cleaned_single_line_topic():
    fc = _FakeClient("MCA aneurysm clipping\n")
    topic = extract_board_topic("what structures are at risk clipping an MCA aneurysm?", client=fc)
    assert topic == "MCA aneurysm clipping"
    assert "MCA aneurysm" in fc.calls[0][1]   # the question is passed to the client


def test_extract_falls_back_to_question_on_empty():
    fc = _FakeClient("   ")
    q = "vasospasm management in SAH"
    assert extract_board_topic(q, client=fc) == q


def test_extract_includes_answer_context_when_given():
    fc = _FakeClient("ACDF C5-6")
    extract_board_topic("q?", answer="the disc at C5-6 ...", client=fc)
    assert "Answer (context)" in fc.calls[0][1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_topic_extract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'neuro_caseboard.topic_extract'`

- [ ] **Step 3: Write the implementation**

Create `neuro_caseboard/topic_extract.py`:

```python
"""LLM topic extraction: turn a Q&A question (and optional answer context) into a short
case/procedure topic for a pre-op board. Uses the configured Vertex synth client by default
(GCP credits); the client is injectable for tests. Never returns empty (falls back to the
question)."""
from __future__ import annotations

_SYSTEM = (
    "You convert a neurosurgery clinical question into a short case or procedure topic "
    "suitable as the title of a pre-operative case board. Reply with ONLY the topic on a "
    "single line — no preamble, no quotes, no trailing punctuation. "
    "Example: 'what structures are at risk clipping an MCA aneurysm?' -> 'MCA aneurysm clipping'."
)


def _default_client():
    from neuro_core.config import load_config
    from neuro_core.synth_clients import make_synth_client
    return make_synth_client(load_config())


def extract_board_topic(question: str, answer: str = "", *, client=None) -> str:
    client = client or _default_client()
    user = f"Question: {question}"
    if answer:
        user += f"\n\nAnswer (context):\n{answer[:1500]}"
    out = (client.generate(_SYSTEM, user, []) or "").strip()
    if not out:
        return question.strip()
    return out.splitlines()[0].strip() or question.strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_topic_extract.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/topic_extract.py tests/test_topic_extract.py
git commit -m "feat(board): extract_board_topic — LLM question->case topic (Vertex, injectable)"
```

---

## Task 3: Wire cross-feature flows + badges into the Streamlit app

**Files:**
- Modify (full replace): `app/streamlit_app.py`

No unit test (logic is in the tested helpers); verify with `py_compile`. Do NOT modify
`query.py` or `pipeline.py`.

- [ ] **Step 1: Replace the entire contents of `app/streamlit_app.py`**

```python
"""Single local app: ask cited questions OR build a pre-op board, over the shared engine, with
cross-feature flows (answer -> build a board; board card -> ask a follow-up) and inline
cross-link badges backed by neuro_core.evidence.
Run: `streamlit run app/streamlit_app.py`. Set APP_PASSWORD to gate access (no gate locally)."""
import os
import tempfile
from pathlib import Path

import streamlit as st

from neuro_caseboard.board_view import board_view
from neuro_caseboard.pipeline import build_dossier
from neuro_caseboard.render_pdf import render_pdf
from neuro_caseboard.topic_extract import extract_board_topic
from neuro_core.evidence import from_figure, from_figure_item, other_features, record
from neuro_core.query import query

st.set_page_config(page_title="Neuro Case Prep", layout="wide")

# Optional passcode gate: set APP_PASSWORD in the deployment env. No gate locally.
_pw = os.environ.get("APP_PASSWORD", "")
if _pw and not st.session_state.get("authed"):
    _entered = st.text_input("Passcode", type="password")
    if _entered == _pw:
        st.session_state["authed"] = True
        st.rerun()
    if _entered:
        st.error("Wrong passcode.")
    st.stop()

# Apply any pending mode switch + field seeds requested by a cross-flow button on the PREVIOUS
# run, BEFORE the widgets that own those keys are instantiated (Streamlit forbids mutating a
# widget-backed session_state key after its widget is created).
if "_pending_mode" in st.session_state:
    st.session_state["mode"] = st.session_state.pop("_pending_mode")
if "seed_question" in st.session_state:
    st.session_state["ask_q"] = st.session_state.pop("seed_question")
if "seed_topic" in st.session_state:
    st.session_state["build_topic"] = st.session_state.pop("seed_topic")

# Session-scoped cross-feature evidence store: EvidenceRef.key -> set of feature labels.
_store = st.session_state.setdefault("session_evidence", {})

mode = st.sidebar.radio("Mode", ["Ask", "Build board"], key="mode")


def _badge(key, current_label):
    notes = other_features(_store, key, current_label)
    if notes:
        st.caption(f"→ also in {notes[0]}")


if mode == "Ask":
    st.title("Ask the neurosurgery corpus")
    st.caption("Citation-grounded answers from your textbook corpus. Decision-support only.")
    q = st.text_input("Ask a clinical or anatomy question", key="ask_q")
    if q:
        with st.spinner("Searching textbooks..."):
            result = query(q)
        label = f'answer: "{q}"'
        record(_store, [from_figure(f) for f in result.figures], label)
        st.markdown(result.answer)
        if result.figures:
            st.subheader("Figures")
            cols = st.columns(min(3, len(result.figures)))
            for col, f in zip(cols, result.figures):
                with col:
                    st.image(f.image_path,
                             caption=f"[{f.source_n}] {f.book}, p.{f.page} — {f.caption}",
                             use_container_width=True)
                    _badge(from_figure(f).key, label)
        st.subheader("Sources")
        for c in result.citations:
            loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
            st.write(f"[{c.n}] {loc}")
        if st.button("Build a board from this"):
            try:
                topic = extract_board_topic(q, result.answer)
            except Exception:
                topic = q
            st.session_state["seed_topic"] = topic
            st.session_state["_pending_mode"] = "Build board"
            st.rerun()

else:  # Build board
    st.title("Build a pre-op case board")
    st.caption("Structured, corpus-grounded pre-operative dossier. Decision-support only.")
    topic = st.text_input('Case, e.g. "C5-6 ACDF" or "left retrosigmoid vestibular schwannoma"',
                          key="build_topic")
    c1, c2, c3 = st.columns(3)
    want_pdf = c1.checkbox("PDF download", value=True)
    enrich = c2.checkbox("Corpus enrichment", value=True)
    use_llm = c3.checkbox("LLM explorer", value=True)
    if topic and st.button("Build board"):
        with st.spinner("Building board…"):
            dossier = build_dossier(topic, enrich=enrich, use_llm=None if use_llm else False)
            view = board_view(dossier)
        st.session_state["last_board"] = {
            "topic": topic,
            "claims": [c.text for s in dossier.sections for c in s.claims],
        }
        label = f'board: "{topic}"'
        record(_store, [from_figure_item(fi) for fi in view.figures], label)
        s = view.summary
        st.success(f"{len(dossier.sections)} sections · {s.supported} corpus-supported · "
                   f"{s.to_verify} to verify · {s.quarantined} quarantined")
        if want_pdf:
            with tempfile.TemporaryDirectory() as td:
                art = render_pdf(dossier, Path(td) / "case-board.pdf")
                pdf_bytes = Path(art.path).read_bytes()
            st.download_button("Download PDF", pdf_bytes, file_name="case-board.pdf",
                               mime="application/pdf")
        if view.figures:
            st.subheader("Figures")
            cols = st.columns(min(3, len(view.figures)))
            for col, fig in zip(cols, view.figures):
                with col:
                    st.image(fig.image_path,
                             caption=f"[{fig.fig_id}] {fig.caption} — {fig.citation}",
                             use_container_width=True)
                    _badge(from_figure_item(fig).key, label)
        st.markdown(view.markdown)

    # Board card -> ask a follow-up (uses the most recently built board this session).
    last = st.session_state.get("last_board")
    if last and last["claims"]:
        st.divider()
        st.subheader("Follow up")
        choice = st.selectbox(f'Ask a follow-up about a card from "{last["topic"]}"',
                              last["claims"], key="followup_choice")
        if st.button("Ask this"):
            st.session_state["seed_question"] = choice
            st.session_state["_pending_mode"] = "Ask"
            st.rerun()
```

- [ ] **Step 2: Verify it compiles and the new imports resolve**

Run: `python3 -m py_compile app/streamlit_app.py && echo "compile OK"`
Expected: `compile OK`.

Run: `python3 -c "from neuro_core.evidence import from_figure, from_figure_item, record, other_features; from neuro_caseboard.topic_extract import extract_board_topic; print('imports OK')"`
Expected: `imports OK`.

- [ ] **Step 3: Confirm the engines were not touched**

Run: `git diff --stat master -- neuro_core/query.py neuro_caseboard/pipeline.py`
Expected: no output (both files identical to master).

- [ ] **Step 4: Commit**

```bash
git add app/streamlit_app.py
git commit -m "feat(web): cross-feature flows (answer<->board) + figure cross-link badges"
```

---

## Task 4: Final acceptance verification

**Files:** none (verification only).

- [ ] **Step 1: Full suite**

Run: `python3 -m pytest -q`
Expected: `287 passed` (278 + 6 + 3).

- [ ] **Step 2: Static acceptance checks**

```bash
python3 -m py_compile app/streamlit_app.py && echo "streamlit compile OK"
python3 -c "import neuro_core.evidence, neuro_caseboard.topic_extract; print('modules import OK')"
git diff --stat master -- neuro_core/query.py neuro_caseboard/pipeline.py && echo "engines untouched OK"
```
Expected: each OK marker prints; the `git diff` line is empty (engines unchanged).

- [ ] **Step 3: Hand off**

REQUIRED SUB-SKILL: Use superpowers:finishing-a-development-branch to present merge options for `phase2-cross-feature-flows`.

---

## Self-Review (controller, before execution)

- **Spec coverage:** §3.1 model → Task 1; §3.2 topic extraction → Task 2; §3.3 flow A + §3.4 badges + §3.5 wiring → Task 3; §4 acceptance → Task 4. All covered.
- **Type consistency:** `EvidenceRef.key` and the three adapters used identically in Task 1 tests and the Task 3 app. `record(store, refs, label)` / `other_features(store, key, label)` signatures match between Task 1 and Task 3. `extract_board_topic(question, answer="", *, client=None)` and the `.generate(system, user, images)` client contract match Task 2 and Task 3.
- **Placeholder scan:** none — every code step is complete.
- **Streamlit gotcha:** mode switches use `_pending_mode` (a non-widget key) applied before the `key="mode"` radio is created — avoids the "cannot modify after widget instantiated" error.
