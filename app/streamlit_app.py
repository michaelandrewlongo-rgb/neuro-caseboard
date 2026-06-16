"""Neuro·Caseboard — single local console for citation-grounded Q&A and pre-op board building,
over one shared engine, with cross-feature flows (answer -> build a board; board card -> ask a
follow-up) and inline cross-link badges backed by neuro_core.evidence.

The presentation layer is the "Executive Navy" design system (app/signal_theme.py): a deep-navy
nav rail over a bright report plane, a three-font role split (Archivo UI / Source Serif 4 reading
column / IBM Plex Mono micro-labels) and a single deep-teal accent. The case-board PDF
(neuro_caseboard/caseboard_pdf.py) renders the same identity for print, so every surface of the
product reads as one brand.

Run: `streamlit run app/streamlit_app.py`. Set APP_PASSWORD to gate access (no gate locally)."""
import html
import os
import tempfile
from pathlib import Path

import streamlit as st

import signal_theme as sig
from neuro_caseboard.board_view import board_view
from neuro_caseboard.pipeline import build_dossier, render_case_pdf, render_ask_pdf
from neuro_caseboard.topic_extract import extract_board_topic
from neuro_core.evidence import from_figure, from_figure_item, other_features, record
from neuro_caseboard.qa import answer_question

st.set_page_config(page_title="Neuro·Caseboard — Signal", page_icon="◈", layout="wide",
                   initial_sidebar_state="expanded")
sig.apply_theme()

# Optional passcode gate: set APP_PASSWORD in the deployment env. No gate locally.
_pw = os.environ.get("APP_PASSWORD", "")
if _pw and not st.session_state.get("authed"):
    sig.hero("Restricted console", "Enter the access passcode to continue.",
             eyebrow="Neurosurgery Signal · Locked")
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

# --- Sidebar: branded console rail -------------------------------------------------------------
sig.sidebar_brand()
sig.sidebar_label("Lane")
mode = st.sidebar.radio("Mode", ["Ask", "Build board", "Cards"], key="mode",
                        label_visibility="collapsed")


def _badge(key, current_label):
    notes = other_features(_store, key, current_label)
    if notes:
        sig.xref(f"also in {notes[0]}")


if mode == "Ask":
    sig.hero("Ask the corpus", "Citation-grounded answers from your neurosurgery textbooks, "
             "augmented with contemporary PubMed literature.",
             eyebrow="Ask · Citation-grounded",
             disclaimer="Decision-support only · not a substitute for clinical judgement")
    q = st.text_input("Ask a clinical or anatomy question", key="ask_q",
                      placeholder='e.g. "blood supply of the lateral medulla"')
    if not q:
        sig.example_hints(["blood supply of the lateral medulla", "Wallenberg syndrome findings",
                           "borders of the cavernous sinus", "watershed infarct territories"])
    if q:
        with st.spinner("Searching textbooks + recent literature…"):
            result = answer_question(q)
        from neuro_core.query import Clarification
        if isinstance(result, Clarification):
            st.warning("This question maps to several distinct topics. Re-ask naming one variant:")
            sig.variants([v.label for v in result.variants])
            st.stop()
        label = f'answer: "{q}"'
        record(_store, [from_figure(f) for f in result.figures], label)
        st.markdown(sig.citation_chips(result.answer), unsafe_allow_html=True)
        if result.figures:
            sig.section("Figures", "FIG")
            cols = st.columns(min(3, len(result.figures)))
            for col, f in zip(cols, result.figures):
                with col:
                    st.image(f.image_path,
                             caption=f"[{f.source_n}] {f.book}, p.{f.page} — {f.caption}",
                             use_container_width=True)
                    _badge(from_figure(f).key, label)
        sig.section("Sources", "SRC")
        sig.sources_panel(result.citations)
        if result.literature and result.literature.narrative:
            sig.section("Contemporary Literature", "LIT")
            st.markdown(sig.citation_chips(result.literature.narrative), unsafe_allow_html=True)
            sig.literature_panel(result.literature.citations)
        from neuro_caseboard.pipeline import _slug
        if st.checkbox("Prepare PDF", help="Render this answer as an Executive-Navy PDF"):
            with st.spinner("Rendering PDF…"):
                with tempfile.TemporaryDirectory() as td:
                    pdf_path = render_ask_pdf(result, q, Path(td) / "ask.pdf")
                    pdf_bytes = Path(pdf_path).read_bytes()
            st.download_button("Download PDF", pdf_bytes,
                               file_name=f"ask-{_slug(q)}.pdf", mime="application/pdf")
        if st.button("Build a board from this", type="primary"):
            try:
                topic = extract_board_topic(q, result.answer)
            except Exception:
                topic = q
            st.session_state["seed_topic"] = topic
            st.session_state["_pending_mode"] = "Build board"
            st.rerun()

elif mode == "Build board":
    sig.hero("Build a pre-op board", "A structured, corpus-grounded pre-operative dossier for the "
             "exact procedure — anatomy, operative steps, and risks.",
             eyebrow="Build · Pre-op dossier",
             disclaimer="Decision-support only · verify against primary sources before use")
    topic = st.text_input('Case, e.g. "C5-6 ACDF" or "left retrosigmoid vestibular schwannoma"',
                          key="build_topic",
                          placeholder='e.g. "right carotid endarterectomy"')
    if not topic:
        sig.example_hints(["C5–6 ACDF", "left retrosigmoid vestibular schwannoma",
                           "right carotid endarterectomy", "awake left temporal glioma"], label="Cases")
    c1, c2, c3 = st.columns(3)
    want_pdf = c1.checkbox("PDF download", value=True)
    enrich = c2.checkbox("Corpus enrichment", value=True)
    use_llm = c3.checkbox("LLM explorer", value=True)
    if topic and st.button("Build board", type="primary"):
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
        sig.evidence_bar(s.supported, s.to_verify, s.quarantined)
        sig.metrics([
            (len(dossier.sections), "sections", ""),
            (s.supported, "corpus-supported", "supported"),
            (s.to_verify, "to verify", "verify"),
            (s.quarantined, "quarantined", "quarantined"),
        ])
        sig.legend()
        if want_pdf:
            with tempfile.TemporaryDirectory() as td:
                pdf_path = render_case_pdf(dossier, topic, Path(td) / "case-board.pdf")
                pdf_bytes = Path(pdf_path).read_bytes()
            st.download_button("Download PDF", pdf_bytes, file_name="case-board.pdf",
                               mime="application/pdf")
        if view.figures:
            sig.section("Figures", "FIG")
            cols = st.columns(min(3, len(view.figures)))
            for col, fig in zip(cols, view.figures):
                with col:
                    st.image(fig.image_path,
                             caption=f"[{fig.fig_id}] {fig.caption} — {fig.citation}",
                             use_container_width=True)
                    _badge(from_figure_item(fig).key, label)
        st.markdown(sig.citation_chips(view.markdown), unsafe_allow_html=True)

    # Board card -> ask a follow-up (uses the most recently built board this session).
    last = st.session_state.get("last_board")
    if last and last["claims"]:
        sig.section("Follow up", "NEXT")
        sig.note(f'Drill into any card from "{html.escape(last["topic"])}" as a fresh cited question.')
        choice = st.selectbox("Pick a card", last["claims"], key="followup_choice",
                              label_visibility="collapsed")
        if st.button("Ask this", type="primary"):
            st.session_state["seed_question"] = choice
            st.session_state["_pending_mode"] = "Ask"
            st.rerun()

elif mode == "Cards":
    from neuro_core.cards_query import cards_query, flagged_tags, CardsIndexNotBuilt

    sig.hero("Board-review card bank", "Hybrid search over your SANS / ABNS deck — your personal "
             "study notes, matched but not synthesized.",
             eyebrow="Cards · Study deck",
             disclaimer="Personal notes · NOT corpus-cited or source-verified")
    sig.note("This lane is isolated from Ask / Build: results are your own flashcards, not "
             "grounded textbook answers.")
    sig.sidebar_label("Cards")
    k = st.sidebar.slider("Cards to show", 3, 20, 6)
    q = st.text_input("Search the cards", key="cards_q",
                      placeholder='e.g. "cavernous sinus contents"')
    if not q:
        sig.example_hints(["cavernous sinus contents", "Meckel cave", "spinal cord tracts",
                           "circle of Willis"])
    if q:
        res = None
        try:
            with st.spinner("Searching cards…"):
                res = cards_query(q, k=k)
        except CardsIndexNotBuilt as e:
            st.warning(str(e))
        if res is not None and not res.cards:
            st.info("No matching cards.")
        for i, c in enumerate(res.cards if res else [], 1):
            deck = c.deck_name or c.deck_full or "cards"
            flags = flagged_tags(c.tags)
            label = ("⚠ " if flags else "") + f"[{i}] {c.question_text}  —  {deck}"
            with st.expander(label, expanded=(i == 1)):
                if flags:
                    st.warning(f"Flagged in your deck as unverified "
                               f"({', '.join(flags)}) — not source-checked.")
                st.markdown(f"**Q.** {c.question_text}")
                st.markdown(f"**A.** {c.answer_text}")
                if c.tags:
                    st.caption(f"tags: {c.tags}")
                for p in c.image_paths:
                    try:
                        st.image(p, use_container_width=True)
                    except Exception:
                        st.caption(f"(image unavailable: {p})")
