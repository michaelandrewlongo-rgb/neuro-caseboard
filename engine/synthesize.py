from dataclasses import dataclass, field

SYSTEM_PROMPT = (
    "You are a neurosurgical reference assistant. Answer ONLY from the provided "
    "textbook passages. Rules:\n"
    "- Cite the bracketed source number for every clinical claim, e.g. [2].\n"
    "- If the passages do not contain the answer, say "
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


def synthesize(question, hits, client, model):
    user = f"Question: {question}\n\nPassages:\n{_format_passages(hits)}"
    resp = client.chat.completions.create(
        model=model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
    )
    answer = resp.choices[0].message.content
    citations = [
        Citation(n=i, book=h.book, chapter=h.chapter or "", page=h.page)
        for i, h in enumerate(hits, 1)
    ]
    return Synthesis(answer=answer, citations=citations)
