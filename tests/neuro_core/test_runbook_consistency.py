import importlib
import pathlib

# Resolve from this file's location (repo_root/tests/neuro_core/), not the process cwd, so the
# test passes regardless of the directory pytest is invoked from.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_runbook_referenced_modules_import():
    for m in ("neuro_core.scripts.probe_book", "neuro_core.scripts.build_index",
              "neuro_core.scripts.build_visual_index"):
        importlib.import_module(m)


def test_runbook_mentions_key_steps():
    doc = (REPO_ROOT / "docs/runbooks/integrating-a-textbook.md").read_text()
    for token in ("probe_book", "build_index", "build_visual_index", "CORPUS_DIR", "to_arrow"):
        assert token in doc, token
