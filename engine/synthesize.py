from dataclasses import dataclass, field

SYSTEM_PROMPT = (
    "You are a neurosurgical reference assistant. Answer ONLY from the provided "
    "textbook passages and any attached page images. Rules:\n"
    "- Cite the bracketed source number for every clinical claim, e.g. [2].\n"
    "- Some sources include an attached page image (a figure/plate). When an image "
    "is attached for a source, you may describe what the figure shows and must "
    "still cite that source number. Do not describe images that are not attached.\n"
    "- If the passages/images do not contain the answer, say "
    "\"Not found in the provided sources.\"\n"
    "- If sources disagree, state the disagreement explicitly and attribute each "
    "view to its source.\n"
    "- Be concise and clinically precise. This is decision-support, not a "
    "substitute for clinical judgment."
)


@dataclass
class Citation:
    n: int
    book: str
    chapter: str
    page: int


@dataclass
class Synthesis:
    answer: str
    citations: list = field(default_factory=list)


def _format_passages(hits):
    lines = []
    for i, h in enumerate(hits, 1):
        loc = h.book
        if h.chapter:
            loc += f", {h.chapter}"
        loc += f", p.{h.page}"
        lines.append(f"[{i}] {loc}:\n{h.text}")
    return "\n\n".join(lines)


def _figure_note(figures):
    if not figures:
        return ""
    refs = ", ".join(f"[{f.source_n}] {f.book}, p.{f.page}" for f in figures)
    return ("\n\nAttached page images (in order) correspond to these sources: "
            f"{refs}. Use them to describe the relevant figure and cite the source.")


def synthesize(question, hits, figures, images, synth_client):
    user = f"Question: {question}\n\nPassages:\n{_format_passages(hits)}"
    user += _figure_note(figures)
    answer = synth_client.generate(SYSTEM_PROMPT, user, images)
    citations = [
        Citation(n=i, book=h.book, chapter=h.chapter or "", page=h.page)
        for i, h in enumerate(hits, 1)
    ]
    return Synthesis(answer=answer, citations=citations)
