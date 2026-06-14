from dataclasses import dataclass, field

# The exact abstention string the model is instructed to emit when the passages/
# images don't contain the answer. Single source of truth: used both in the prompt
# below and by is_refusal() so the instruction and the detector can never drift.
REFUSAL = "Not found in the provided sources."

SYSTEM_PROMPT = (
    "You are a neurosurgical reference assistant. Answer ONLY from the provided "
    "textbook passages and any attached page images. Rules:\n"
    "- Cite the bracketed source number for every clinical claim, e.g. [2].\n"
    "- Some sources include an attached page image (a figure/plate). When an image "
    "is attached for a source, you may describe what the figure shows and must "
    "still cite that source number. Do not describe images that are not attached.\n"
    f"- If the passages/images do not contain the answer, say \"{REFUSAL}\"\n"
    "- If sources disagree, state the disagreement explicitly and attribute each "
    "view to its source.\n"
    "- Be concise and clinically precise. This is decision-support, not a "
    "substitute for clinical judgment."
)


def is_refusal(answer: str) -> bool:
    """True when synthesis abstained (emitted REFUSAL verbatim).

    Normalizes for trailing punctuation, surrounding whitespace, and case so a
    genuine abstention still matches small model formatting wobble, but requires
    the WHOLE answer to be the refusal (equality, not substring) so a real answer
    that merely mentions the phrase is not misclassified as a refusal."""
    def norm(s: str) -> str:
        return s.strip().rstrip(".").strip().casefold()
    return norm(answer) == norm(REFUSAL)


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


def _appended_figures(hits, figures):
    k = len(hits)
    return sorted((f for f in figures if f.source_n > k),
                  key=lambda f: f.source_n)


def _format_appended(appended):
    if not appended:
        return ""
    lines = []
    for f in appended:
        loc = f.book
        if f.chapter:
            loc += f", {f.chapter}"
        loc += f", p.{f.page}"
        cap = f": {f.caption}" if f.caption else ""
        lines.append(f"[{f.source_n}] {loc} (figure){cap}")
    return "\n\nAdditional figure sources:\n" + "\n".join(lines)


def synthesize(question, hits, figures, images, synth_client, variant_directive=None):
    appended = _appended_figures(hits, figures)
    user = f"Question: {question}\n\nPassages:\n{_format_passages(hits)}"
    user += _format_appended(appended)
    user += _figure_note(figures)
    if variant_directive:
        user += "\n\n" + variant_directive
    answer = synth_client.generate(SYSTEM_PROMPT, user, images)
    citations = [
        Citation(n=i, book=h.book, chapter=h.chapter or "", page=h.page)
        for i, h in enumerate(hits, 1)
    ]
    for f in appended:
        citations.append(Citation(n=f.source_n, book=f.book,
                                  chapter=f.chapter or "", page=f.page))
    return Synthesis(answer=answer, citations=citations)
