"""Dependency-free tests for the benchmark runner.

No live engine, no network, no GPU: every test injects a stub ``answer_fn`` and uses lightweight
stand-in objects that merely mimic the QAResult / Clarification / Citation attribute shapes. We do
NOT import ``neuro_caseboard.qa`` (importing the runner must stay engine-free).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO_ROOT / "evaluation" / "scripts" / "run_benchmark.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_benchmark", RUNNER_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


runner = _load_runner()


# ---- stand-in objects mimicking the real shapes -------------------------------------------------
def make_qaresult(answer="An answer.", citations=None, figures=None, literature=None):
    cits = citations if citations is not None else [
        SimpleNamespace(n=1, book="Youmans", chapter="Ch 1", page=42)
    ]
    figs = figures if figures is not None else []
    return SimpleNamespace(answer=answer, citations=cits, figures=figs, literature=literature)


def make_clarification(variants):
    # Clarification shape: has .variants and .question, but NO .answer.
    return SimpleNamespace(
        question="Which variant?",
        variants=[SimpleNamespace(label=lbl, rewrite=rw) for lbl, rw in variants],
    )


MANIFEST_REC = {
    "id": "NIS-01",
    "domain": "Neurointerventional Surgery",
    "question": "Should MeVO occlusions undergo thrombectomy?",
    "benchmark_version": "contemporary-qs-in-neurosurgery:test",
    "enabled": True,
}

RUN_CONFIG = {
    "run_id": "testrun",
    "application_commit": "deadbeef",
    "working_tree_dirty": False,
    "corpus_fingerprint": None,
    "prompt_fingerprint": None,
    "model_configuration": {"synth_provider": "vertex"},
}


def _run_one(answer_fn, **kw):
    return runner.run_one(
        MANIFEST_REC,
        run_id="testrun",
        run_config=RUN_CONFIG,
        answer_fn=answer_fn,
        sleep_fn=lambda _s: None,
        **kw,
    )


# ---- choose_variant -----------------------------------------------------------------------------
def test_choose_variant_picks_longest_label():
    clar = make_clarification([("Short", "rw1"), ("A much longer label", "rw2"), ("Mid one", "rw3")])
    chosen = runner.choose_variant(clar)
    assert chosen.label == "A much longer label"
    assert chosen.rewrite == "rw2"


def test_choose_variant_tie_keeps_first():
    clar = make_clarification([("AAAA", "first"), ("BBBB", "second")])
    assert runner.choose_variant(clar).rewrite == "first"


def test_choose_variant_no_variants_raises():
    with pytest.raises(ValueError):
        runner.choose_variant(SimpleNamespace(variants=[]))


# ---- happy path ---------------------------------------------------------------------------------
def test_happy_path_records_completed_and_serializes():
    long_answer = "Full answer text. " * 50
    calls = []

    def stub(q):
        calls.append(q)
        return make_qaresult(answer=long_answer)

    rec = _run_one(stub)
    assert rec["status"] == "completed"
    assert rec["attempts"] == 1
    assert rec["answer"] == long_answer  # untruncated
    assert rec["selected_variant"] is None
    assert rec["citations"] == [{"n": 1, "book": "Youmans", "chapter": "Ch 1", "page": 42}]
    assert rec["raw_response"]["answer"] == long_answer
    assert rec["error_details"] is None
    assert calls == [MANIFEST_REC["question"]]
    # schema-required fields present
    for f in ("started_at", "completed_at", "latency_seconds", "run_id"):
        assert f in rec


# ---- disambiguation -----------------------------------------------------------------------------
def test_disambiguation_selects_variant_and_recalls():
    clar = make_clarification(
        [("ICA", "scope ICA"), ("Comprehensive multi-territory variant", "scope broad")]
    )
    seen = []

    def stub(q):
        seen.append(q)
        if len(seen) == 1:
            return clar
        return make_qaresult(answer="Resolved answer for the broad variant.")

    rec = _run_one(stub)
    assert rec["status"] == "completed"
    assert rec["selected_variant"] == "Comprehensive multi-territory variant"
    assert rec["answer"] == "Resolved answer for the broad variant."
    # first call original question, second call the chosen rewrite
    assert seen == [MANIFEST_REC["question"], "scope broad"]


# ---- retry ladder -------------------------------------------------------------------------------
def test_retry_succeeds_on_third_attempt():
    n = {"count": 0}
    sleeps = []

    def stub(q):
        n["count"] += 1
        if n["count"] < 3:
            raise RuntimeError("Vertex 500")
        return make_qaresult(answer="Recovered.")

    rec = runner.run_one(
        MANIFEST_REC,
        run_id="testrun",
        run_config=RUN_CONFIG,
        answer_fn=stub,
        sleep_fn=lambda s: sleeps.append(s),
    )
    assert rec["status"] == "completed"
    assert rec["attempts"] == 3
    assert rec["answer"] == "Recovered."
    assert sleeps == [runner.RETRY_BACKOFF_SECONDS]  # backoff only before the final attempt


def test_retry_exhausted_records_engine_error():
    n = {"count": 0}
    sleeps = []

    def stub(q):
        n["count"] += 1
        raise RuntimeError("persistent boom")

    rec = runner.run_one(
        MANIFEST_REC,
        run_id="testrun",
        run_config=RUN_CONFIG,
        answer_fn=stub,
        sleep_fn=lambda s: sleeps.append(s),
    )
    assert rec["status"] == "engine_error"
    assert rec["attempts"] == 3
    assert n["count"] == 3
    assert "RuntimeError: persistent boom" in rec["error_details"]
    assert rec["answer"] is None
    assert sleeps == [runner.RETRY_BACKOFF_SECONDS]  # exactly one 30s wait, and it was patched out


# ---- not_gradable -------------------------------------------------------------------------------
@pytest.mark.parametrize("empty", ["", "   ", None])
def test_empty_answer_is_not_gradable(empty):
    rec = _run_one(lambda q: make_qaresult(answer=empty))
    assert rec["status"] == "not_gradable"
    assert rec["attempts"] == 1
    assert rec["error_details"]


# ---- timeout ------------------------------------------------------------------------------------
def test_timeout_records_timeout_status():
    import time as _time

    def slow(q):
        _time.sleep(5)
        return make_qaresult()

    rec = _run_one(slow, timeout=0.05)
    assert rec["status"] == "timeout"
    assert rec["error_details"]


# ---- resume + atomic writes ---------------------------------------------------------------------
def test_resume_skips_completed_questions(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    run_jsonl = run_dir / "run.jsonl"
    # pre-seed one completed id
    seeded = {"question_id": "NIS-01", "status": "completed", "answer": "x"}
    run_jsonl.write_text(json.dumps(seeded) + "\n", encoding="utf-8")

    calls = []

    def stub(q):
        calls.append(q)
        return make_qaresult(answer="fresh")

    produced = runner.run_benchmark(
        run_dir,
        answer_fn=stub,
        end_id="NIS-03",  # would normally run NIS-01..03
        resume=True,
        sleep_fn=lambda _s: None,
    )
    produced_ids = {r["question_id"] for r in produced}
    assert "NIS-01" not in produced_ids  # skipped via resume
    assert "NIS-02" in produced_ids and "NIS-03" in produced_ids
    assert len(calls) == 2  # NIS-01 not re-invoked


def test_run_benchmark_writes_config_and_appends(tmp_path):
    run_dir = tmp_path / "run"

    produced = runner.run_benchmark(
        run_dir,
        answer_fn=lambda q: make_qaresult(answer="ok"),
        start_id="NIS-01",
        end_id="NIS-02",
        sleep_fn=lambda _s: None,
    )
    assert len(produced) == 2
    cfg = json.loads((run_dir / "run-config.json").read_text(encoding="utf-8"))
    assert cfg["run_id"]
    assert "model_configuration" in cfg
    lines = (run_dir / "run.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:  # every appended line is valid JSON
        json.loads(line)


def test_run_id_stable_across_resume(tmp_path):
    run_dir = tmp_path / "run"
    runner.run_benchmark(
        run_dir, answer_fn=lambda q: make_qaresult(), start_id="NIS-01", end_id="NIS-01",
        sleep_fn=lambda _s: None,
    )
    cfg1 = json.loads((run_dir / "run-config.json").read_text(encoding="utf-8"))
    runner.run_benchmark(
        run_dir, answer_fn=lambda q: make_qaresult(), end_id="NIS-02", resume=True,
        sleep_fn=lambda _s: None,
    )
    cfg2 = json.loads((run_dir / "run-config.json").read_text(encoding="utf-8"))
    assert cfg1["run_id"] == cfg2["run_id"]
