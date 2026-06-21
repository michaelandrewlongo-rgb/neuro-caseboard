"""Pure rendering predicate shared by the Streamlit Ask view and its tests.

Woven mode carries [L#] citations with an empty narrative; separate mode carries both.
Render the Contemporary Literature panel whenever citations exist (narrative optional).
Kept in its own module so it is unit-testable without importing the full Streamlit app
(app/streamlit_app.py executes the whole page at import time)."""
from __future__ import annotations


def should_show_literature(lit) -> bool:
    return bool(lit and getattr(lit, "citations", None))
