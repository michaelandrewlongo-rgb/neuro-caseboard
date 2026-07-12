"""The CORPUS_DIR default must not point at the stale, empty /mnt/d mount.

The real PDFs live under $HOME/textbook_pdfs; the old default silently produced an empty
build. FIX_PLAN §1 P1.
"""
from pathlib import Path

from neuro_core.config import DEFAULTS, load_config


def test_default_corpus_dir_is_not_the_stale_mnt_d():
    assert DEFAULTS["CORPUS_DIR"] != "/mnt/d/textbook_pdfs"
    assert "/mnt/d/" not in DEFAULTS["CORPUS_DIR"]


def test_default_corpus_dir_is_under_home():
    assert DEFAULTS["CORPUS_DIR"] == str(Path.home() / "textbook_pdfs")


def test_env_still_overrides(monkeypatch):
    monkeypatch.setenv("CORPUS_DIR", "/some/other/path")
    monkeypatch.setenv("NEURO_CASEBOARD_SKIP_DOTENV", "1")
    assert str(load_config().corpus_dir) == "/some/other/path"
