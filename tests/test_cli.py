"""Tests for caseprep.cli — argument parsing and integration."""

import tempfile
from pathlib import Path

import pytest
from caseprep.cli import main


class TestCliBasics:
    def test_help_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "usage: caseprep" in captured.out or "usage: caseprep" in captured.err

    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0

    def test_missing_topic_exits(self):
        # With subcommands, bare `caseprep` prints help and returns 0
        # (previously raised SystemExit with positional topic)
        exit_code = main([])
        assert exit_code == 0


class TestCliGenerate:
    def test_basic_run_creates_output(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "test-case"
            exit_code = main(["brain tumor", "-o", str(out)])
            assert exit_code == 0
            assert (out / "README.md").is_file()
            assert (out / "resource-links.html").is_file()

    def test_default_output_dir_name(self):
        with tempfile.TemporaryDirectory() as d:
            import os
            orig = os.getcwd()
            try:
                os.chdir(d)
                exit_code = main(["acoustic neuroma"])
                assert exit_code == 0
                out = Path(d) / "acoustic-neuroma-caseprep"
                assert out.is_dir()
            finally:
                os.chdir(orig)

    def test_open_flag_does_not_crash(self):
        """--open calls webbrowser.open; just verify it doesn't crash."""
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "test-case"
            exit_code = main(["glioma", "-o", str(out), "--open"])
            assert exit_code == 0  # webbrowser.open is best-effort

    def test_local_pdfs_nonexistent_dir(self, capsys):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "test-case"
            exit_code = main([
                "glioma", "-o", str(out),
                "--local-pdfs", "/nonexistent/path/pdfs",
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            assert "Not a directory" in captured.out or "No matches" in captured.out
