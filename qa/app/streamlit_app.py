import os
import sys
from pathlib import Path

# `streamlit run app/streamlit_app.py` puts app/ on sys.path, not the repo root,
# so make `engine` importable regardless of how this script is launched.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from engine.query import query

st.set_page_config(page_title="Neuro Textbook RAG", layout="wide")

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

st.title("Neurosurgery Textbook RAG")
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
                st.image(
                    f.image_path,
                    caption=f"[{f.source_n}] {f.book}, p.{f.page} — {f.caption}",
                    use_container_width=True,
                )

    st.subheader("Sources")
    for c in result.citations:
        loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
        st.write(f"[{c.n}] {loc}")
