"""Reusable figure card: an inline (column-width) image plus an explicit "Enlarge" control
that opens a large modal showing the image full-size. Used by every figure-rendering lane in
streamlit_app.py (Ask, Build board, Case, Cards) so anatomy can actually be read.

Imported bare (``import figure_gallery``) to match signal_theme — app/ is a script dir on
sys.path, not a package.
"""
import streamlit as st


@st.dialog("Figure", width="large")
def _enlarge_dialog(image_path: str, caption: str | None) -> None:
    """Modal body: the same image at full modal width, with its caption beneath."""
    st.image(image_path, width="stretch")
    if caption:
        st.caption(caption)


def figure_card(image_path, caption: str | None = None, *, key: str) -> None:
    """Render an inline figure with an "Enlarge" button that opens a full-size modal.

    Args:
        image_path: path (or object) accepted by ``st.image``.
        caption: optional caption shown under both the inline image and the enlarged image.
        key: caller-unique string; used to namespace the Enlarge button's widget key so
            multiple figures on one page do not collide.
    """
    st.image(image_path, caption=caption, width="stretch")
    if st.button("🔍 Enlarge", key=f"enlarge_{key}", width="stretch"):
        _enlarge_dialog(image_path, caption)
