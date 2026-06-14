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
