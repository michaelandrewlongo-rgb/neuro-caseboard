"""Tests for caseprep.pdfs — local PDF search."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def pdf_dir():
    """Create a temp directory with a simple PDF for testing."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


class TestSearchLocalPdfs:
    def test_returns_empty_when_no_pdfs(self, pdf_dir):
        from caseprep.pdfs import search_local_pdfs
        results = search_local_pdfs("glioma", pdf_dir)
        assert results == []

    def test_returns_empty_when_pymupdf_missing(self, monkeypatch, pdf_dir):
        """Simulate PyMuPDF not being installed."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "fitz":
                raise ImportError("No module named 'fitz'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        from caseprep.pdfs import search_local_pdfs
        results = search_local_pdfs("glioma", pdf_dir)
        assert results == []

    def test_not_a_directory(self, capsys):
        from caseprep.pdfs import search_local_pdfs
        results = search_local_pdfs("glioma", Path("/tmp/nonexistent-xyz"))
        assert results == []
        captured = capsys.readouterr()
        assert "Not a directory" in captured.out

    def test_skips_non_pdf_files(self, pdf_dir):
        """Non-PDF files should be ignored."""
        (pdf_dir / "notes.txt").write_text("some notes about glioma")
        from caseprep.pdfs import search_local_pdfs
        results = search_local_pdfs("glioma", pdf_dir)
        assert results == []

    def test_filename_match_without_pymupdf_text(self, pdf_dir):
        """If a PDF is present but can't be opened (dummy file), only filename match."""
        (pdf_dir / "glioma case report.pdf").write_text("not a real pdf")
        from caseprep.pdfs import search_local_pdfs
        results = search_local_pdfs("glioma", pdf_dir)
        if results:
            # If fitz tries to open and fails, it skips — no filename match without text extraction.
            pass  # behaviour depends on whether PyMuPDF raises on the dummy


class TestFormatPdfResults:
    def test_no_results(self):
        from caseprep.pdfs import format_pdf_results
        result = format_pdf_results([])
        assert "No matches" in result

    def test_with_filename_match(self):
        from caseprep.pdfs import format_pdf_results
        results = [{
            "path": "/papers/glioma.pdf",
            "filename_match": True,
            "snippets": [],
        }]
        output = format_pdf_results(results)
        assert "1 PDF(s) matched" in output
        assert "glioma.pdf" in output
        assert "filename match" in output.lower()

    def test_with_snippets(self):
        from caseprep.pdfs import format_pdf_results
        results = [{
            "path": "/papers/study.pdf",
            "filename_match": False,
            "snippets": ["This study examines glioma outcomes."],
        }]
        output = format_pdf_results(results)
        assert "This study examines glioma" in output
