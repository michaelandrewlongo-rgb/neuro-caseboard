# Phase 2 — Cross-feature flows + shared evidence model

**Date:** 2026-06-14
**Status:** Approved design (implements Phase 2 of the integration; Phases 0 and 1 are merged)
**Author:** Michael Longo + Claude
**Predecessor:** `2026-06-14-caseboard-textbookrag-integration-design.md` (§4 Phase 2);
`2026-06-14-phase1-unified-surface-design.md`

## 1. Context & problem

Phases 0–1 gave us one engine (`neuro_core`), one CLI (`caseboard ask`/`build`), and one
Streamlit app with **Ask** and **Build board** modes. But the two features are still siblings,
not connected:

- You can't move between them: a board card can't seed a follow-up question, and a Q&A answer
  can't seed a board.
- They speak different evidence dialects. Q&A uses **typed** dataclasses —
  `neuro_core.synthesize.Citation(n, book, chapter, page)` and `neuro_core.query.Figure(source_n,
  book, chapter, page, image_path, caption)`. Boards use caseprep's **stringly-typed**
  `EvidenceRecord` internally and emit `neuro_caseboard.model.FigureItem(fig_id, image_path,
  caption, citation, ...)` as output. There is no shared type, so the app can't tell that a figure
  cited in an answer is the *same* figure on a board.

## 2. Decisions (locked during brainstorming)

- **Depth: flows AND a shared evidence model** (the deeper, "integrated positively" path), not
  just UI navigation.
- **Model home: a neutral typed `neuro_core` type** (`EvidenceRef`). Q&A's `Citation`/`Figure`
  and the board's `FigureItem` adapt to it **at the app boundary**. caseprep stays external;
  `query.py` and `pipeline.py` are **not** modified.
- **Answer → board: LLM-extract a clean topic** from the question (using the configured Vertex
  synth client — GCP credits), pre-filled and **editable** before building.
- **Cross-links: inline badge** on the evidence itself (e.g. `→ also on your "MCA aneurysm
  clipping" board`).

## 3. Detailed design

### 3.1 Shared evidence model — `neuro_core/evidence.py` (new)

A frozen, typed lingua franca plus boundary adapters and two pure session helpers.

```python
@dataclass(frozen=True)
class EvidenceRef:
    book: str = ""
    page: int | None = None
    chapter: str = ""
    citation: str = ""               # display string, e.g. "Rhoton, p.538"
    figure_path: str | None = None   # set when this evidence is a figure
    caption: str = ""
    score: float | None = None
    source: str = ""                 # provenance tag, e.g. "qa" / "board"

    @property
    def key(self) -> str:
        """Stable cross-link identity. Figures are identified by their page-image path
        (both lanes draw figure_path from the same figures.lance row); text citations by
        (book, page)."""
        if self.figure_path:
            return f"fig:{self.figure_path}"
        return f"cite:{self.book}|{self.page}"
```

Adapters (module-level functions):
- `from_citation(c) -> EvidenceRef` — Q&A citation (`c.n/book/chapter/page`).
- `from_figure(f) -> EvidenceRef` — Q&A figure (`f.book/chapter/page/image_path/caption`),
  sets `figure_path`.
- `from_figure_item(fi) -> EvidenceRef` — board output figure (`fi.image_path/caption/citation`);
  `book/page` absent (FigureItem carries only a citation string), which is fine because figure
  identity is `figure_path`.

Pure session helpers (the app holds the store in `st.session_state`):
```python
def record(store: dict[str, set[str]], refs, label: str) -> None:
    for r in refs:
        store.setdefault(r.key, set()).add(label)

def other_features(store: dict[str, set[str]], key: str, label: str) -> list[str]:
    return sorted(lbl for lbl in store.get(key, set()) if lbl != label)
```

### 3.2 Flow B — answer → build a board (`neuro_caseboard/topic_extract.py`, new)

```python
def extract_board_topic(question: str, answer: str = "", *, client=None) -> str: ...
```
- Default client = `make_synth_client(load_config())` (Vertex when configured; injectable for
  tests). Calls `client.generate(system, user, images=[])`.
- System prompt: "convert a neurosurgery clinical question into a short case/procedure topic …
  reply with ONLY the topic." Includes a worked example.
- Returns the first non-empty line, stripped. **Fallback:** if the model returns empty, return
  the raw `question` (never produce an empty topic).

App wiring: in Ask mode, after an answer, a **"Build a board from this"** button →
`extract_board_topic(question, answer)` (wrapped in try/except → fall back to the raw question on
any client error) → set `st.session_state["seed_topic"]`, switch mode to "Build board",
`st.rerun()`. Build mode pre-fills its topic field from `seed_topic` (editable).

### 3.3 Flow A — board card → ask a follow-up

In Build mode, below the rendered board: a `st.selectbox("Ask a follow-up about a card", [claim
texts])` over `dossier.sections[].claims[].text`, plus an **"Ask this"** button → set
`st.session_state["seed_question"]`, switch mode to "Ask", `st.rerun()`. Ask mode pre-fills its
question field from `seed_question`.

(A selectbox, not per-claim buttons: the board renders as a single `st.markdown` blob, so there
are no per-claim widgets to attach buttons to. The selectbox gives card-level follow-up without
restructuring the render.)

### 3.4 Cross-link badges

- The app keeps `st.session_state["session_evidence"]: dict[str, set[str]]`.
- After an answer: `record(store, [from_figure(f) for f in result.figures], label=f'answer: "{q}"')`.
- After a board build: `record(store, [from_figure_item(fi) for fi in view.figures],
  label=f'board: "{topic}"')`.
- When rendering each figure, compute its `EvidenceRef.key`; `notes = other_features(store, key,
  current_label)`; if non-empty, render a one-line caption suffix / `st.caption`
  (`→ also on your {notes[0]}`). Figures are the cross-link surface this phase (reliable shared
  identity via `figure_path`).

### 3.5 Streamlit wiring (mechanism)

- Sidebar radio bound to session state: `st.sidebar.radio("Mode", ["Ask", "Build board"],
  key="mode")`.
- Programmatic switch: button handlers set `st.session_state["mode"]` + the relevant seed, then
  `st.rerun()` (set-before-widget-creation, so the next run's radio/text_input read the new
  values).
- Seed consumption: at the top of each mode, `seed = st.session_state.pop("seed_*", None)`; if
  present, set the text widget's keyed default before instantiating it.
- The view stays thin — all real logic is in the tested helpers (`evidence.py`,
  `topic_extract.py`).

## 4. Acceptance criteria

- `neuro_core/evidence.py`: `EvidenceRef.key` distinguishes figure (`fig:<path>`) vs citation
  (`cite:<book>|<page>`); adapters map the three source types correctly; `record`/`other_features`
  report a figure shared across two labels and exclude the current label.
- `extract_board_topic` returns the cleaned single-line topic from a fake client and falls back to
  the question on empty output.
- `app/streamlit_app.py` compiles; the cross-flow buttons, seeds, and figure badges are wired
  through the tested helpers.
- `query.py` and `pipeline.py` are unchanged (boundary-only integration) — verified by diff.
- Full suite green: 278 (Phase 1 baseline) + new `evidence` + `topic_extract` tests.

## 5. Testing strategy

- **`evidence.py`** (unit): key for figure vs citation; `from_citation`/`from_figure`/
  `from_figure_item` field mapping and resulting key; `record` accumulates labels per key;
  `other_features` returns other labels and omits the current one; same figure under one label →
  no cross-link.
- **`topic_extract.py`** (unit, fake client): a fake `client.generate` returning `"MCA aneurysm
  clipping\n"` → returns `"MCA aneurysm clipping"`; returning `""` → returns the raw question; the
  `user` argument passed to the client contains the question.
- **Streamlit app**: `py_compile` only (logic lives in the helpers; no browser test).
- Full suite after each task.

## 6. Risks & mitigations

- **Streamlit session-state/widget-key gotcha** (can't mutate a widget-backed key after the widget
  is created) → set `mode`/seeds in button handlers *before* `st.rerun()`; consume seeds at the top
  of the run before widget creation. Documented pattern in the plan.
- **LLM topic mis-extraction** → topic is **editable** before Build, and extraction is wrapped in
  try/except with a raw-question fallback, so the flow never breaks.
- **Vertex client unconfigured in some envs** → the default client construction is lazy and the
  app wraps the call; on failure it seeds the raw question. Unit tests inject a fake client and
  never hit the network.
- **Cross-link false negatives** → both Q&A figures and board figures derive `figure_path` from the
  same `figures.lance` rows, so the identity is stable; if a path ever diverged the badge simply
  wouldn't show (no false positive).

## 7. Out of scope (Phase 2)

- Citation-level (text) cross-link **UI** — the model supports it (`cite:` key), but Phase 2
  surfaces badges on figures only.
- Persisting session evidence beyond the in-memory Streamlit session.
- Carrying Q&A evidence *into* the board pipeline as seed evidence (the board's audited explorer
  generates its own evidence).
- Modifying caseprep, `query.py`, or `pipeline.py`.
- Multi-user, accounts, deploy, renaming.

## 8. Resolved decisions

- Depth: **flows + shared evidence model**.
- Model: neutral typed **`neuro_core.evidence.EvidenceRef`**; adapt at the **app boundary**;
  engines untouched.
- Answer→board: **LLM-extract** a clean topic (Vertex synth client), editable pre-fill.
- Cross-links: **inline badge**, figures only this phase (model is text-capable for later).
- App stays a thin view; logic in tested helpers.
