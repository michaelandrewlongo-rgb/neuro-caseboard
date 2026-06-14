# Phase 1 — Unified Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose both Q&A and board generation through one CLI (`caseboard ask` / `caseboard build`) and one local Streamlit app (Ask / Build modes) over the shared `neuro_core`, deleting the duplicate FastAPI + static-JS Q&A surface.

**Architecture:** Thin, pure-plumbing. No retrieval/synthesis/board-content changes. Board generation runs **in-process** behind a spinner (local single-user). The only real new logic is a pure, unit-tested `board_view` presenter that turns an in-memory `Dossier` into (markdown body, de-duped figures, summary) for the web Build view; the Streamlit script and CLI stay logic-free views over tested code.

**Tech Stack:** Python 3.10+, argparse (CLI), Streamlit (web), existing `neuro_caseboard` renderers (`render_md`, `render_pdf`), `neuro_core.query` (Q&A), pytest.

**Spec:** `docs/superpowers/specs/2026-06-14-phase1-unified-surface-design.md`

**Branch:** Execute on a new branch `phase1-unified-surface` (do not implement on `master`). The controller creates it before Task 1.

**Baseline:** `master` @ `e6db048`, 290 tests passing. After this plan: 290 − 17 (deleted server/auth tests) + 5 (new presenter/CLI tests) = **278** passing.

---

## File Structure

- **Create** `neuro_caseboard/board_view.py` — pure presenter (`Dossier → BoardView`), no I/O.
- **Create** `tests/test_board_view.py` — presenter unit tests.
- **Modify** `neuro_caseboard/cli.py` — add `ask` subcommand beside `build`; split handlers.
- **Create** `tests/test_cli.py` — CLI dispatch tests (ask + build).
- **Create** `app/streamlit_app.py` — single web app, Ask + Build modes (replaces `qa/app/`).
- **Delete** `qa/` (the whole package: `cli/`, `server/`, `app/`, `web/`, `__init__.py`).
- **Delete** `tests/neuro_core/test_server.py`, `tests/neuro_core/test_auth.py`.
- **Modify** `pyproject.toml` — drop `qa*` from `packages.find`.
- **Modify** `README.md` — document the three entry points; update the Layout block.

---

## Task 1: Board-view presenter (pure, tested)

**Files:**
- Create: `neuro_caseboard/board_view.py`
- Test: `tests/test_board_view.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_board_view.py`:

```python
from neuro_caseboard.board_view import board_view, BoardView
from neuro_caseboard.model import Dossier, Section, FigureItem, EvidenceSummary


def _fig(path, fid):
    return FigureItem(fig_id=fid, image_path=path, caption=f"caption {fid}",
                      citation="Book, p.1")


def test_board_view_dedups_figures_by_path_in_first_seen_order():
    d = Dossier(
        title="C5-6 ACDF",
        summary=EvidenceSummary(supported=3, to_verify=1, quarantined=0),
        sections=[
            Section(heading="Approach", figures=[_fig("/x/p1.png", "F1"),
                                                 _fig("/x/p2.png", "F2")]),
            Section(heading="Anatomy", figures=[_fig("/x/p1.png", "F1b"),  # same path
                                                _fig("/x/p3.png", "F3")]),
        ],
    )
    v = board_view(d)
    assert isinstance(v, BoardView)
    assert v.title == "C5-6 ACDF"
    assert [f.image_path for f in v.figures] == ["/x/p1.png", "/x/p2.png", "/x/p3.png"]
    assert v.summary.supported == 3 and v.summary.to_verify == 1


def test_board_view_markdown_keeps_body_but_strips_inline_images():
    d = Dossier(
        title="T", summary=EvidenceSummary(),
        sections=[Section(heading="Approach", intro="midline exposure",
                          figures=[_fig("/x/p1.png", "F1")])],
    )
    v = board_view(d)
    assert "Approach" in v.markdown            # body retained
    assert "midline exposure" in v.markdown    # intro retained
    assert "![" not in v.markdown              # inline image embeds stripped
    assert [f.image_path for f in v.figures] == ["/x/p1.png"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_board_view.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'neuro_caseboard.board_view'`

- [ ] **Step 3: Write the implementation**

Create `neuro_caseboard/board_view.py`:

```python
"""Pure presenter: turn an in-memory Dossier into what the Streamlit Build view needs —
the board body as markdown, a de-duped figure list, and the evidence summary — with no disk
access. Keeping this out of the Streamlit script makes the Build logic unit-testable.

render_md embeds figures as ``![Fig](local/path)`` lines, which Streamlit's ``st.markdown``
cannot resolve from the local filesystem; the view shows figures via ``st.image`` instead, so
this presenter strips those inline image-embed lines from the markdown body."""
from __future__ import annotations

import re
from dataclasses import dataclass

from neuro_caseboard.model import Dossier, EvidenceSummary, FigureItem
from neuro_caseboard.render_md import render_markdown

# a dedicated image-embed bullet line, e.g. "  - ![F1](/abs/p1.png)"
_IMG_LINE = re.compile(r"^\s*-?\s*!\[[^\]]*\]\([^)]*\)\s*$")


@dataclass
class BoardView:
    title: str
    markdown: str                 # board body, inline image-embed lines removed
    figures: list[FigureItem]     # de-duped by image_path, first-seen order
    summary: EvidenceSummary


def board_view(dossier: Dossier) -> BoardView:
    body = "\n".join(ln for ln in render_markdown(dossier).splitlines()
                     if not _IMG_LINE.match(ln))
    seen: set[str] = set()
    figures: list[FigureItem] = []
    for sec in dossier.sections:
        for fig in sec.figures:
            if fig.image_path in seen:
                continue
            seen.add(fig.image_path)
            figures.append(fig)
    return BoardView(title=dossier.title, markdown=body,
                     figures=figures, summary=dossier.summary)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_board_view.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/board_view.py tests/test_board_view.py
git commit -m "feat(board): board_view presenter (Dossier -> markdown/figures/summary)"
```

---

## Task 2: `caseboard ask` subcommand

**Files:**
- Modify: `neuro_caseboard/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
from neuro_caseboard import cli


class _Cite:
    def __init__(self, n, book, chapter, page):
        self.n, self.book, self.chapter, self.page = n, book, chapter, page


class _Fig:
    def __init__(self, source_n, book, page, image_path):
        self.source_n, self.book, self.page, self.image_path = source_n, book, page, image_path


class _Result:
    answer = "The facial nerve runs anterior to the tumor."
    citations = [_Cite(1, "Greenberg", "Tumors", 792)]
    figures = [_Fig(1, "Rhoton", 538, "/x/p538.png")]


def test_cli_ask_prints_answer_sources_and_figures(capsys, monkeypatch):
    monkeypatch.setattr("neuro_core.query.query", lambda q, force=False: _Result())
    rc = cli.main(["ask", "facial nerve schwannoma"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "facial nerve runs anterior" in out
    assert "[1] Greenberg, Tumors, p.792" in out
    assert "[1] Rhoton, p.538 -> /x/p538.png" in out


def test_cli_ask_gpu_not_ready_exits_1(capsys, monkeypatch):
    from neuro_core.gpu_guard import GpuNotReadyError

    def _boom(q, force=False):
        raise GpuNotReadyError("no cuda")

    monkeypatch.setattr("neuro_core.query.query", _boom)
    rc = cli.main(["ask", "q"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "GPU not ready" in err


def test_cli_build_dispatches_to_generate(capsys, monkeypatch):
    class _Summary:
        supported, to_verify, quarantined = 2, 1, 0

    class _Dossier:
        sections = [object(), object()]
        summary = _Summary()

    calls = {}

    def _fake_generate(topic, *, output_dir, pdf, enrich, use_llm):
        calls.update(topic=topic, output_dir=output_dir, pdf=pdf, enrich=enrich, use_llm=use_llm)
        return _Dossier(), {"markdown": "out/case-board.md"}

    monkeypatch.setattr(cli, "generate", _fake_generate)
    rc = cli.main(["build", "C5-6 ACDF", "-o", "out", "--no-llm"])
    out = capsys.readouterr().out
    assert rc == 0
    assert calls["topic"] == "C5-6 ACDF" and calls["use_llm"] is False and calls["enrich"] is True
    assert "Wrote out/case-board.md" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: FAIL — `test_cli_ask_*` fail (no `ask` subcommand: argparse `SystemExit`/error). `test_cli_build_dispatches_to_generate` may already pass.

- [ ] **Step 3: Rewrite `neuro_caseboard/cli.py`**

Replace the entire file with:

```python
"""`caseboard` command-line entry point: ask cited questions and build pre-op dossiers."""

from __future__ import annotations

import argparse
import sys

from neuro_caseboard.pipeline import generate, _slug


def _run_ask(args) -> int:
    from neuro_core.gpu_guard import GpuNotReadyError
    from neuro_core.query import query
    try:
        result = query(args.question, force=args.force)
    except GpuNotReadyError as e:
        print(f"GPU not ready: {e}", file=sys.stderr)
        return 1
    print(result.answer)
    print("\nSources:")
    for c in result.citations:
        loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
        print(f"  [{c.n}] {loc}")
    if result.figures:
        print("\nFigures:")
        for f in result.figures:
            print(f"  [{f.source_n}] {f.book}, p.{f.page} -> {f.image_path}")
    return 0


def _run_build(args) -> int:
    out = args.output or f"{_slug(args.topic)}-caseboard"
    dossier, artifacts = generate(
        args.topic, output_dir=out, pdf=args.pdf, enrich=not args.no_enrich,
        use_llm=False if args.no_llm else None)
    print(f"Wrote {artifacts['markdown']}")
    if "pdf" in artifacts:
        print(f"Wrote {artifacts['pdf']}")
    s = dossier.summary
    print(f"  {len(dossier.sections)} sections · "
          f"{s.supported} corpus-supported · {s.to_verify} to verify · "
          f"{s.quarantined} quarantined")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="caseboard",
        description="Neurosurgical case prep: ask cited questions and build pre-op dossiers.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ask", help="Ask a cited clinical/anatomy question")
    a.add_argument("question", help="The clinical question, in quotes")
    a.add_argument("--force", action="store_true",
                   help="Run even if the GPU readiness guard fails.")

    b = sub.add_parser("build", help="Build a dossier from a free-text case")
    b.add_argument("topic", help='Free-text case, e.g. "C5-6 corpectomy"')
    b.add_argument("-o", "--output", default=None, help="Output directory")
    b.add_argument("--pdf", action="store_true", help="Also export case-board.pdf")
    b.add_argument("--no-enrich", action="store_true",
                   help="Skip corpus enrichment (offline verify-only checklist)")
    b.add_argument("--no-llm", action="store_true",
                   help="Force the deterministic Explorer (skip the LLM case-specific Explorer)")

    args = parser.parse_args(argv)
    if args.cmd == "ask":
        return _run_ask(args)
    if args.cmd == "build":
        return _run_build(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add neuro_caseboard/cli.py tests/test_cli.py
git commit -m "feat(cli): add 'caseboard ask' subcommand (folds in qa.cli.ask)"
```

---

## Task 3: Unified Streamlit app (Ask + Build modes)

**Files:**
- Create: `app/streamlit_app.py`

There is no unit test for the Streamlit script (its logic lives in the tested `board_view` and `query`); verify it compiles. Do **not** delete `qa/app/` here — that happens in Task 4.

- [ ] **Step 1: Create `app/streamlit_app.py`**

```python
"""Single local app: ask cited questions OR build a pre-op board, over the shared engine.
Run: `streamlit run app/streamlit_app.py`. Set APP_PASSWORD to gate access (no gate locally)."""
import os
import tempfile
from pathlib import Path

import streamlit as st

from neuro_caseboard.board_view import board_view
from neuro_caseboard.pipeline import build_dossier
from neuro_caseboard.render_pdf import render_pdf
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

mode = st.sidebar.radio("Mode", ["Ask", "Build board"])

if mode == "Ask":
    st.title("Ask the neurosurgery corpus")
    st.caption("Citation-grounded answers from your textbook corpus. Decision-support only.")
    q = st.text_input("Ask a clinical or anatomy question")
    if q:
        with st.spinner("Searching textbooks..."):
            result = query(q)
        st.markdown(result.answer)
        if result.figures:
            st.subheader("Figures")
            cols = st.columns(min(3, len(result.figures)))
            for col, f in zip(cols, result.figures):
                with col:
                    st.image(f.image_path,
                             caption=f"[{f.source_n}] {f.book}, p.{f.page} — {f.caption}",
                             use_container_width=True)
        st.subheader("Sources")
        for c in result.citations:
            loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
            st.write(f"[{c.n}] {loc}")

else:  # Build board
    st.title("Build a pre-op case board")
    st.caption("Structured, corpus-grounded pre-operative dossier. Decision-support only.")
    topic = st.text_input('Case, e.g. "C5-6 ACDF" or "left retrosigmoid vestibular schwannoma"')
    c1, c2, c3 = st.columns(3)
    want_pdf = c1.checkbox("PDF download", value=True)
    enrich = c2.checkbox("Corpus enrichment", value=True)
    use_llm = c3.checkbox("LLM explorer", value=True)
    if topic and st.button("Build board"):
        with st.spinner("Building board…"):
            dossier = build_dossier(topic, enrich=enrich, use_llm=None if use_llm else False)
            view = board_view(dossier)
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
        st.markdown(view.markdown)
```

- [ ] **Step 2: Verify it compiles**

Run: `python3 -m py_compile app/streamlit_app.py && echo OK`
Expected: `OK` (exit 0). (Streamlit scripts run top-to-bottom on import, so a full import would render; `py_compile` is the appropriate static check.)

- [ ] **Step 3: Commit**

```bash
git add app/streamlit_app.py
git commit -m "feat(web): unified Streamlit app with Ask + Build modes"
```

---

## Task 4: Retire the FastAPI server + JS viewer; dissolve `qa/`

**Files:**
- Delete: `qa/` (entire package), `tests/neuro_core/test_server.py`, `tests/neuro_core/test_auth.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Confirm nothing imports `qa` outside the deleted tests**

Run: `grep -rn "import qa\b\|from qa\b\|from qa\.\|import qa\." --include=*.py . | grep -v __pycache__`
Expected: only matches inside `tests/neuro_core/test_server.py` and `tests/neuro_core/test_auth.py` (both being deleted). If anything else appears, STOP and report.

- [ ] **Step 2: Delete the package and its tests**

```bash
git rm -r qa
git rm tests/neuro_core/test_server.py tests/neuro_core/test_auth.py
```

- [ ] **Step 3: Drop `qa*` from packaging**

In `pyproject.toml`, change:

```toml
include = ["neuro_caseboard*", "neuro_core*", "qa*"]
```

to:

```toml
include = ["neuro_caseboard*", "neuro_core*"]
```

- [ ] **Step 4: Verify no FastAPI/qa residue and the suite is green**

Run: `grep -rniE "fastapi|uvicorn" --include=*.py . | grep -v __pycache__`
Expected: no output.

Run: `python3 -m pytest -q`
Expected: `278 passed` (290 baseline + 5 new − 17 deleted).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(web): retire FastAPI server + JS viewer; dissolve qa/ package"
```

---

## Task 5: Document the unified surface

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a Surfaces section**

In `README.md`, replace:

```markdown
hardcoded clinical phrases — so the dossier generalises across all of neurosurgery.

## Clinical depth — the Explorer
```

with:

```markdown
hardcoded clinical phrases — so the dossier generalises across all of neurosurgery.

## Surfaces

One engine, two features, exposed through one CLI and one local web app:

- **CLI** — `caseboard ask "<question>"` for a cited answer + figures, or
  `caseboard build "<topic>" [--pdf] [-o dir]` for a pre-op dossier.
- **Web** — `streamlit run app/streamlit_app.py` opens a single app with **Ask** and
  **Build board** modes over the same engine. Set `APP_PASSWORD` to gate access (no gate
  locally).

## Clinical depth — the Explorer
```

- [ ] **Step 2: Update the Layout block**

In `README.md`, replace:

```markdown
  render_pdf.py fpdf2 renderer (embedded Unicode font + ASCII fallback, inline figures)
  retrieve.py   InProcessTextbookRetriever (+ subprocess fallback)
  pipeline.py   explorer -> enricher -> auditor (reused) -> compile -> render
  cli.py        `caseboard build "<topic>" [--pdf] [-o dir]`
```

with:

```markdown
  render_pdf.py fpdf2 renderer (embedded Unicode font + ASCII fallback, inline figures)
  board_view.py presenter: Dossier -> (markdown, figures, summary) for the web Build view
  retrieve.py   InProcessTextbookRetriever (+ subprocess fallback)
  pipeline.py   explorer -> enricher -> auditor (reused) -> compile -> render
  cli.py        `caseboard ask "<q>"` · `caseboard build "<topic>" [--pdf] [-o dir]`
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document unified CLI (ask/build) + Streamlit surface"
```

---

## Task 6: Final acceptance verification

**Files:** none (verification only).

- [ ] **Step 1: Full suite**

Run: `python3 -m pytest -q`
Expected: `278 passed`.

- [ ] **Step 2: Static acceptance checks**

```bash
test ! -e qa && echo "qa-gone OK"
python3 -c "from neuro_caseboard.cli import main; print('cli import OK')"
python3 -m neuro_caseboard.cli ask --help >/dev/null && echo "ask --help OK"
python3 -m neuro_caseboard.cli build --help >/dev/null && echo "build --help OK"
python3 -m py_compile app/streamlit_app.py && echo "streamlit compile OK"
grep -rniE "fastapi|uvicorn" --include=*.py . | grep -v __pycache__ || echo "no fastapi OK"
```
Expected: each line prints its OK marker; no FastAPI matches.

- [ ] **Step 3: Hand off**

REQUIRED SUB-SKILL: Use superpowers:finishing-a-development-branch to present merge options for `phase1-unified-surface`.

---

## Self-Review (controller, before execution)

- **Spec coverage:** §3.1 CLI → Task 2; §3.2 web app + §3.2.1 presenter → Tasks 1 & 3; §3.3 retire duplication → Task 4; §3.4 packaging + docs → Tasks 4 & 5; §4 acceptance → Task 6. All covered.
- **Type consistency:** `board_view(dossier) -> BoardView(title, markdown, figures, summary)` used identically in Task 1 and Task 3. `build_dossier(topic, *, enrich, use_llm)` and `render_pdf(dossier, out_path) -> ArtifactRef(.path)` match the real signatures. CLI `_run_ask`/`_run_build` use the real `QueryResult`/`Dossier`/`EvidenceSummary` fields.
- **Placeholder scan:** none — every code step is complete.
