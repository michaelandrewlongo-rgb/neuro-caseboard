"""End-to-end CLI artifact smoke.

Shells out to the real `caseboard` entry point and proves the OFFLINE default path —
`caseboard build --no-llm --pdf` — produces a valid Markdown + PDF dossier with NO
dependence on API keys, a textbook corpus, a GPU, or any external service. This is the
artifact-generation sanity check the rendering/export surface most needs protected.

Marked `smoke` so it can be selected (`-m smoke`) or skipped (`-m 'not smoke'`).
"""

import os
import shutil
import subprocess
import sys

import pytest

# The whole pipeline imports caseprep at module top; skip cleanly (rather than failing in a
# subprocess) if it isn't installed in this environment.
pytest.importorskip("caseprep")

pytestmark = pytest.mark.smoke

# Environment variables that, if leaked in, could let a real LLM/corpus/online lane engage.
# We strip them so the smoke proves the deterministic offline fallback truly stands alone.
_SCRUB = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "OPENROUTER_API_KEY",
    "GOOGLE_CLOUD_PROJECT",
    "CASEBOARD_LLM_PROVIDER",
    "CASEBOARD_LLM",
    "CASEPREP_TEXTBOOK",
)


def _caseboard_argv():
    """Prefer the installed console script (proves the entry point); fall back to running
    the module so the test still works from a source checkout without a console script."""
    exe = shutil.which("caseboard")
    if exe:
        return [exe]
    return [sys.executable, "-m", "neuro_caseboard.cli"]


def test_caseboard_build_offline_produces_md_and_pdf(tmp_path):
    out = tmp_path / "board"
    env = {k: v for k, v in os.environ.items() if k not in _SCRUB}

    proc = subprocess.run(
        [*_caseboard_argv(), "build", "C5-6 corpectomy", "--no-llm", "--pdf", "-o", str(out)],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert proc.returncode == 0, f"caseboard build failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    md = out / "case-board.md"
    pdf = out / "case-board.pdf"
    assert md.is_file(), f"missing markdown; stdout was:\n{proc.stdout}"
    assert pdf.is_file(), f"missing pdf; stdout was:\n{proc.stdout}"

    # The CLI reports what it wrote and a deterministic offline summary.
    assert "Wrote" in proc.stdout
    assert "to verify" in proc.stdout  # offline path => cards land in the 'to verify' bucket

    # The Markdown has the corrected report structure (topic title, marker legend, sections).
    text = md.read_text(encoding="utf-8")
    assert "Case Board" in text
    assert "Anatomy at Risk" in text
    assert "Markers:" in text  # the one-line colour-coded legend (defect #4 fix)

    # The PDF is a real PDF, not an empty/HTML stub.
    head = pdf.read_bytes()[:5]
    assert head.startswith(b"%PDF"), f"not a PDF: {head!r}"
    assert pdf.stat().st_size > 10_000, "PDF suspiciously small (font embedding likely failed)"
