"""D7: the benchmark runner records a corpus + prompt fingerprint, and REFUSES to start without
one. Every prior run had both as None, so no run was reproducible and 'run-to-run noise' could
not be told apart from un-recorded config drift. FIX_PLAN §6.2 D7 / §6.6 C4.

Engine-free: the runner is loaded as a standalone module and every engine call is stubbed.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "evaluation" / "scripts" / "run_benchmark.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_benchmark_fp", RUNNER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


runner = _load_runner()


def _tiny_manifest(tmp_path) -> Path:
    p = tmp_path / "manifest.jsonl"
    p.write_text(json.dumps({
        "id": "Q1", "domain": "Test", "question": "test question?",
        "benchmark_version": "test:1", "enabled": True,
    }) + "\n", encoding="utf-8")
    return p


def _stub_answer(_q):
    return SimpleNamespace(answer="An answer [1].",
                           citations=[SimpleNamespace(n=1, book="B", chapter="C", page=1)],
                           figures=[], literature=None, verification=None)


# ---- the fingerprints themselves ----------------------------------------------------------------
def test_prompt_fingerprint_is_deterministic_hex():
    fp = runner.prompt_fingerprint()
    assert fp is not None and len(fp) == 16 and all(c in "0123456789abcdef" for c in fp)
    assert fp == runner.prompt_fingerprint()  # deterministic


def test_corpus_fingerprint_none_when_index_absent(monkeypatch, tmp_path):
    # Fail-safe: an unreadable index yields None (which the guard turns into a hard stop).
    monkeypatch.setenv("INDEX_DIR", str(tmp_path / "no-such-index"))
    assert runner.corpus_fingerprint() is None


def test_build_run_config_carries_both_keys():
    cfg = runner.build_run_config("rid", [{"benchmark_version": "test:1"}])
    assert "corpus_fingerprint" in cfg and "prompt_fingerprint" in cfg


# ---- the start guard ----------------------------------------------------------------------------
def test_runner_refuses_to_start_without_corpus_fingerprint(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "corpus_fingerprint", lambda: None)
    monkeypatch.setattr(runner, "prompt_fingerprint", lambda: "abc123def456abcd")
    with pytest.raises(SystemExit, match="corpus_fingerprint"):
        runner.run_benchmark(tmp_path / "run", answer_fn=_stub_answer,
                             manifest_path=_tiny_manifest(tmp_path))


def test_runner_refuses_to_start_without_prompt_fingerprint(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "corpus_fingerprint", lambda: "abcd1234abcd1234")
    monkeypatch.setattr(runner, "prompt_fingerprint", lambda: None)
    with pytest.raises(SystemExit, match="prompt_fingerprint"):
        runner.run_benchmark(tmp_path / "run", answer_fn=_stub_answer,
                             manifest_path=_tiny_manifest(tmp_path))


def test_runner_runs_and_persists_fingerprints_when_present(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "corpus_fingerprint", lambda: "cafebabecafebabe")
    monkeypatch.setattr(runner, "prompt_fingerprint", lambda: "0123456789abcdef")
    run_dir = tmp_path / "run"
    produced = runner.run_benchmark(run_dir, answer_fn=_stub_answer,
                                    manifest_path=_tiny_manifest(tmp_path))
    assert len(produced) == 1
    cfg = json.loads((run_dir / "run-config.json").read_text())
    assert cfg["corpus_fingerprint"] == "cafebabecafebabe"
    assert cfg["prompt_fingerprint"] == "0123456789abcdef"


def test_resume_of_legacy_config_without_fingerprints_is_refused(monkeypatch, tmp_path):
    # A pre-fingerprint run-config on --resume must also be rejected, not silently continued.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run-config.json").write_text(json.dumps({
        "run_id": "legacy", "corpus_fingerprint": None, "prompt_fingerprint": None,
    }), encoding="utf-8")
    with pytest.raises(SystemExit):
        runner.run_benchmark(run_dir, answer_fn=_stub_answer, resume=True,
                             manifest_path=_tiny_manifest(tmp_path))
