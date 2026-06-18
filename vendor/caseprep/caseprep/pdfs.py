"""Search local PDF files for topic matches using PyMuPDF."""

from pathlib import Path


def _stripped_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def search_local_pdfs(topic: str, pdf_dir: Path) -> list[dict]:
    """Walk *pdf_dir*, opening .pdf files and searching for *topic*.

    For each matching PDF, returns a dict with:
      - path: absolute path to the file
      - filename_match: True if topic appears in the filename
      - snippets: list of text snippets containing the topic (first 3 pages only)

    Requires PyMuPDF (fitz).  Returns an empty list if PyMuPDF is not installed.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("PyMuPDF (fitz) is not installed. Install with: pip install PyMuPDF")
        return []

    pdf_dir = Path(pdf_dir).expanduser().resolve()
    if not pdf_dir.is_dir():
        print(f"Not a directory: {pdf_dir}")
        return []

    topic_lower = topic.strip().lower()
    results: list[dict] = []

    for pdf_path in sorted(pdf_dir.rglob("*.pdf")):
        path_str = str(pdf_path)

        try:
            doc = fitz.open(pdf_path)
        except Exception:
            continue  # skip corrupt/unreadable PDFs

        filename_match = topic_lower in pdf_path.name.lower()
        snippets: list[str] = []

        # Search first 3 pages only for performance
        for page in doc.pages(0, 3):
            text = page.get_text("text")
            if not text:
                continue
            for line in _stripped_lines(text):
                if topic_lower in line.lower():
                    # Trim long lines to a reasonable snippet length
                    snippet = line[:300] + ("…" if len(line) > 300 else "")
                    snippets.append(snippet)

        doc.close()

        if filename_match or snippets:
            results.append({
                "path": path_str,
                "filename_match": filename_match,
                "snippets": snippets,
            })

    return results


def format_pdf_results(results: list[dict]) -> str:
    """Return a human-readable string summarising PDF search results."""
    if not results:
        return "No matches in local PDFs."

    lines = [f"{len(results)} PDF(s) matched:\n"]
    for r in results:
        flag = " [filename match]" if r["filename_match"] else ""
        lines.append(f"  {r['path']}{flag}")
        for snippet in r["snippets"]:
            lines.append(f"    → {snippet}")
        lines.append("")
    return "\n".join(lines)
