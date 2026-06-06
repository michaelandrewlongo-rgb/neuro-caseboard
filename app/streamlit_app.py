import streamlit as st

from engine.query import query

st.set_page_config(page_title="Neuro Textbook RAG", layout="wide")
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
