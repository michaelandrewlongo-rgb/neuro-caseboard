import importlib
import pathlib


def test_runbook_referenced_modules_import():
    for m in ("neuro_core.scripts.probe_book", "neuro_core.scripts.build_index",
              "neuro_core.scripts.build_visual_index"):
        importlib.import_module(m)


def test_runbook_mentions_key_steps():
    doc = pathlib.Path("docs/runbooks/integrating-a-textbook.md").read_text()
    for token in ("probe_book", "build_index", "build_visual_index", "CORPUS_DIR", "to_arrow"):
        assert token in doc, token
