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
