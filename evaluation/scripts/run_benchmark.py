#!/usr/bin/env python3
"""Resumable benchmark runner for the 67-question "Ask the corpus" evaluation.

Drives ``neuro_caseboard.qa.answer_question`` IN-PROCESS (no HTTP, no browser — see
``evaluation/repository-audit.md`` §13). One JSONL record per question is appended atomically to
``<run-dir>/run.jsonl`` as it completes, so a crash never corrupts prior records and ``--resume``
can pick up exactly where it left off.

Design notes
------------
* **Engine is dependency-injected.** The heavy import of ``answer_question`` happens lazily *inside*
  the default ``answer_fn`` factory, never at module import time — so importing this module (and the
  tests) stays cheap and engine-free. Tests inject a stub ``answer_fn``.
* **Disambiguation.** If ``answer_fn`` returns a ``Clarification``-shaped object (has ``.variants``),
  ``choose_variant`` picks the most clinically comprehensive variant (longest ``.label``, first on a
  tie), the chosen label is recorded as ``selected_variant``, and the runner re-calls ``answer_fn``
  with that variant's ``.rewrite`` to obtain the final answer.
* **Retry ladder** (adapted from ``nsgy-questioner.txt``): attempt 1 immediately; on exception
  retry immediately (attempt 2); on a second failure wait 30 s and retry (attempt 3); if it still
  fails, record status ``engine_error`` and move on. The sleep is injectable (``sleep_fn``) so tests
  do not actually sleep.
* **Per-question timeout.** The in-process call runs on a worker thread joined with a timeout; on
  expiry the record is marked ``timeout``. CAVEAT: a Python thread cannot be force-killed, so the
  underlying engine call may keep running in the background until it returns on its own — the timeout
  bounds *the runner's wait*, not the engine's work. Documented limitation; acceptable because the
  record is written and the run proceeds.

CLI
---
    python3 evaluation/scripts/run_benchmark.py --run-dir RUNS/2026-06-20T12-00 \\
        [--start-id NIS-01] [--end-id TRAUMA-10] [--timeout 300] [--resume]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "evaluation" / "inputs" / "benchmark-manifest.jsonl"

DEFAULT_TIMEOUT_SECONDS = 300
RETRY_BACKOFF_SECONDS = 30.0


# --------------------------------------------------------------------------------------------------
# Manifest loading
# --------------------------------------------------------------------------------------------------
def load_manifest(path: Path = MANIFEST) -> list[dict]:
    """Load manifest records in file (= manifest) order, skipping disabled rows."""
    records: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("enabled", True):
            records.append(rec)
    return records


def select_range(records: list[dict], start_id: str | None, end_id: str | None) -> list[dict]:
    """Inclusive slice over manifest order by question id. Missing ids raise."""
    ids = [r["id"] for r in records]
    lo = ids.index(start_id) if start_id else 0
    hi = ids.index(end_id) + 1 if end_id else len(records)
    return records[lo:hi]


# --------------------------------------------------------------------------------------------------
# Disambiguation
# --------------------------------------------------------------------------------------------------
def is_clarification(obj: Any) -> bool:
    """Duck-typed: a Clarification has a ``variants`` sequence and no ``answer`` attribute."""
    return hasattr(obj, "variants") and not hasattr(obj, "answer")


def choose_variant(clarification: Any) -> Any:
    """Pick the most clinically comprehensive variant: the longest ``.label`` wins; first on a tie.

    Mirrors the questioner protocol's "most broadly applicable option". Returns the variant object
    (which carries ``.label`` and ``.rewrite``). Raises ValueError if there are no variants.
    """
    variants = list(getattr(clarification, "variants", []) or [])
    if not variants:
        raise ValueError("clarification has no variants to choose from")
    # Stable: max() keeps the first item on a length tie because we don't reorder.
    return max(variants, key=lambda v: len(getattr(v, "label", "") or ""))


# --------------------------------------------------------------------------------------------------
# Serialization helpers (Citation / Figure / QAResult -> plain dicts)
# --------------------------------------------------------------------------------------------------
def _to_plain(obj: Any) -> Any:
    """Best-effort conversion of dataclass / attr-object to a JSON-safe plain dict."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    # Generic object: pull public attrs.
    if hasattr(obj, "__dict__"):
        return {k: _to_plain(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return str(obj)


def serialize_citations(result: Any) -> list[dict]:
    return [_to_plain(c) for c in (getattr(result, "citations", None) or [])]


def serialize_figures(result: Any) -> list[dict]:
    return [_to_plain(f) for f in (getattr(result, "figures", None) or [])]


def serialize_raw_response(result: Any) -> dict:
    """Best-effort dict of the QAResult fields (answer/citations/figures/literature)."""
    raw: dict[str, Any] = {}
    for field_name in ("answer", "citations", "figures", "literature"):
        if hasattr(result, field_name):
            raw[field_name] = _to_plain(getattr(result, field_name))
    return raw


# --------------------------------------------------------------------------------------------------
# Provenance / run-config snapshot
# --------------------------------------------------------------------------------------------------
def _git(args: list[str]) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=15
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def application_commit() -> str | None:
    return _git(["rev-parse", "HEAD"])


def working_tree_dirty() -> bool | None:
    porcelain = _git(["status", "--porcelain"])
    if porcelain is None:
        return None
    return bool(porcelain.strip())


def model_configuration() -> dict:
    """Cheaply discover provider/model + retrieval knobs WITHOUT invoking the engine.

    Reads process env first (authoritative), falling back to the SAME defaults as
    neuro_core/config.py for display/provenance only. Engine-free by design (no import); the
    duplicated defaults are display strings, not the engine's source of truth.
    """
    def env(name: str, default: str) -> str:
        return os.environ.get(name, default)

    return {
        "synth_provider": env("SYNTH_PROVIDER", "openrouter"),
        "openrouter_model": env("OPENROUTER_MODEL", "z-ai/glm-5.2"),
        "analyze_provider": env("ANALYZE_PROVIDER", "openrouter"),
        "analyze_model": env("ANALYZE_MODEL", "google/gemini-3.1-flash-lite"),
        "vertex_model": env("VERTEX_MODEL", "gemini-2.5-pro"),
        "google_cloud_project": env("GOOGLE_CLOUD_PROJECT", ""),
        "google_cloud_location": env("GOOGLE_CLOUD_LOCATION", "us-central1"),
        "retrieve_k": env("RETRIEVE_K", "40"),
        "rerank_k": env("RERANK_K", "12"),
        "rerank_model": env("RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
        "embed_model": env("EMBED_MODEL", "BAAI/bge-large-en-v1.5"),
        "literature_weave": env("LITERATURE_WEAVE", "true"),
        "literature_k": env("LITERATURE_K", "12"),
        "max_figure_images": env("MAX_FIGURE_IMAGES", "5"),
    }


def _benchmark_version(records: list[dict]) -> str | None:
    versions = {r.get("benchmark_version") for r in records if r.get("benchmark_version")}
    if len(versions) == 1:
        return next(iter(versions))
    return ",".join(sorted(v for v in versions if v)) or None


def build_run_config(run_id: str, records: list[dict]) -> dict:
    return {
        "run_id": run_id,
        "created_at": _now_iso(),
        "application_commit": application_commit(),
        "working_tree_dirty": working_tree_dirty(),
        "benchmark_version": _benchmark_version(records),
        "model_configuration": model_configuration(),
        "python_version": platform.python_version(),
        "host": socket.gethostname(),
        "platform": platform.platform(),
    }


# --------------------------------------------------------------------------------------------------
# Time + atomic IO
# --------------------------------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_record(run_jsonl: Path, record: dict) -> None:
    """Append one record durably. We append-then-fsync so previously written records are never
    touched (a partial trailing line from a hard crash is the worst case, and is recoverable)."""
    run_jsonl.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with open(run_jsonl, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def write_json_atomic(path: Path, data: dict) -> None:
    """Write JSON via temp file + os.replace (atomic on POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def completed_question_ids(run_jsonl: Path) -> set[str]:
    """Question ids already present in run.jsonl (for --resume). Tolerates a partial last line."""
    done: set[str] = set()
    if not run_jsonl.exists():
        return done
    for line in run_jsonl.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # partial trailing line from a crash; ignore
        qid = rec.get("question_id")
        if qid:
            done.add(qid)
    return done


# --------------------------------------------------------------------------------------------------
# The engine call: timeout + disambiguation, single attempt
# --------------------------------------------------------------------------------------------------
class _TimeoutExpired(Exception):
    pass


def _call_with_timeout(fn: Callable[[], Any], timeout: float | None) -> Any:
    """Run ``fn()`` on a worker thread, joined with ``timeout`` seconds.

    Returns the result, re-raises any exception ``fn`` raised, or raises ``_TimeoutExpired`` if the
    thread is still running after ``timeout``. LIMITATION: the worker thread is NOT killed on
    timeout (Python has no safe thread-kill); the engine call may continue in the background.
    """
    box: dict[str, Any] = {}

    def _worker() -> None:
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 - propagate to caller thread
            box["error"] = exc

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise _TimeoutExpired(f"engine call exceeded {timeout}s")
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _resolve_answer(question: str, answer_fn: Callable[..., Any]) -> tuple[Any, str | None]:
    """One full logical call: get a result, and if it is a clarification, choose a variant and
    re-call with its rewrite. Returns (final_result, selected_variant_label_or_None)."""
    result = answer_fn(question)
    selected_variant: str | None = None
    if is_clarification(result):
        chosen = choose_variant(result)
        selected_variant = getattr(chosen, "label", None)
        # Scope the rewrite to the chosen variant: do NOT re-run the disambiguation gate, or the
        # rewrite can return a SECOND Clarification (no .answer) -> not_gradable. (double-disambig)
        result = answer_fn(getattr(chosen, "rewrite"), skip_disambiguation=True)
    return result, selected_variant


# --------------------------------------------------------------------------------------------------
# Per-question orchestration (retry ladder + status)
# --------------------------------------------------------------------------------------------------
def run_one(
    manifest_record: dict,
    *,
    run_id: str,
    run_config: dict,
    answer_fn: Callable[..., Any],
    timeout: float | None = DEFAULT_TIMEOUT_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    max_attempts: int = 3,
) -> dict:
    """Run a single benchmark question through the retry ladder and return a schema-conforming record.

    Retry ladder: attempt 1 immediate; attempt 2 immediate (on exception); attempt 3 after a
    ``RETRY_BACKOFF_SECONDS`` sleep. Timeouts short-circuit (no retry) and record ``timeout``.
    """
    question_id = manifest_record["id"]
    question = manifest_record["question"]
    domain = manifest_record.get("domain", "")

    base = {
        "question_id": question_id,
        "question": question,
        "domain": domain,
        "run_id": run_id,
        "application_commit": run_config.get("application_commit"),
        "working_tree_dirty": run_config.get("working_tree_dirty"),
        "corpus_fingerprint": run_config.get("corpus_fingerprint"),
        "prompt_fingerprint": run_config.get("prompt_fingerprint"),
        "model_configuration": run_config.get("model_configuration"),
        "selected_variant": None,
        "answer": None,
        "citations": None,
        "figures": None,
        "verification": None,
        "raw_response": None,
        "error_details": None,
    }

    started_at = _now_iso()
    t0 = time.monotonic()
    attempts = 0
    last_error: str | None = None
    status = "engine_error"
    result = None
    selected_variant = None

    while attempts < max_attempts:
        attempts += 1
        try:
            result, selected_variant = _call_with_timeout(
                lambda: _resolve_answer(question, answer_fn), timeout
            )
            status = "completed"
            last_error = None
            break
        except _TimeoutExpired as exc:
            status = "timeout"
            last_error = str(exc)
            break  # do not retry a timeout
        except Exception as exc:  # noqa: BLE001 - engine error surface
            last_error = f"{type(exc).__name__}: {exc}"
            status = "engine_error"
            if attempts >= max_attempts:
                break
            # ladder: immediate retry after attempt 1; 30s backoff before the final attempt.
            if attempts >= max_attempts - 1:
                sleep_fn(RETRY_BACKOFF_SECONDS)

    completed_at = _now_iso()
    latency = max(0.0, time.monotonic() - t0)

    record = dict(base)
    record.update(
        {
            "status": status,
            "attempts": attempts,
            "started_at": started_at,
            "completed_at": completed_at,
            "latency_seconds": latency,
            "selected_variant": selected_variant,
            "error_details": last_error,
        }
    )

    if status == "completed":
        # Lazy import keeps this module engine-free at import time (see module docstring); the
        # dict-shape helper is reused from neuro_caseboard rather than duplicated here.
        from neuro_caseboard.answer_verify import verification_to_dict

        answer_text = getattr(result, "answer", None)
        record["answer"] = answer_text
        record["citations"] = serialize_citations(result)
        record["figures"] = serialize_figures(result)
        record["verification"] = verification_to_dict(getattr(result, "verification", None))
        record["raw_response"] = serialize_raw_response(result)
        if not answer_text or not str(answer_text).strip():
            record["status"] = "not_gradable"
            record["error_details"] = "engine returned an empty/None answer"

    return record


# --------------------------------------------------------------------------------------------------
# Default engine factory (lazy import — engine-free until first call)
# --------------------------------------------------------------------------------------------------
def default_answer_fn() -> Callable[..., Any]:
    """Return a callable ``answer_fn(question) -> QAResult|Clarification`` that lazily imports the
    live engine on first use. Importing this module does NOT import the engine."""

    def _answer(question: str, skip_disambiguation: bool = False) -> Any:
        from neuro_caseboard.qa import answer_question  # heavy import, done lazily

        return answer_question(question, force=True, skip_disambiguation=skip_disambiguation)

    return _answer


# --------------------------------------------------------------------------------------------------
# Run driver
# --------------------------------------------------------------------------------------------------
def run_benchmark(
    run_dir: str | os.PathLike,
    *,
    answer_fn: Callable[..., Any] | None = None,
    start_id: str | None = None,
    end_id: str | None = None,
    timeout: float | None = DEFAULT_TIMEOUT_SECONDS,
    resume: bool = False,
    sleep_fn: Callable[[float], None] = time.sleep,
    manifest_path: Path = MANIFEST,
    run_id: str | None = None,
) -> list[dict]:
    """Run the (sub)range of the benchmark sequentially, appending records atomically.

    ``answer_fn`` defaults to the lazy live-engine factory; tests inject a stub. Returns the list of
    records produced in THIS invocation (resumed/skipped questions are not re-run or re-returned).
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    run_jsonl = run_dir / "run.jsonl"
    run_config_path = run_dir / "run-config.json"

    if answer_fn is None:
        answer_fn = default_answer_fn()

    records = load_manifest(manifest_path)
    selected = select_range(records, start_id, end_id)

    # Run-config snapshot: reuse an existing one on resume so run_id is stable.
    if resume and run_config_path.exists():
        run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
        run_id = run_config.get("run_id", run_id)
    else:
        run_id = run_id or uuid.uuid4().hex
        run_config = build_run_config(run_id, records)
        write_json_atomic(run_config_path, run_config)

    already_done = completed_question_ids(run_jsonl) if resume else set()

    produced: list[dict] = []
    for rec in selected:
        if rec["id"] in already_done:
            continue
        record = run_one(
            rec,
            run_id=run_id,
            run_config=run_config,
            answer_fn=answer_fn,
            timeout=timeout,
            sleep_fn=sleep_fn,
        )
        append_record(run_jsonl, record)
        produced.append(record)
    return produced


# --------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------
def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Resumable in-process benchmark runner.")
    p.add_argument("--run-dir", required=True, help="Immutable run directory (run.jsonl lives here).")
    p.add_argument("--start-id", default=None, help="Inclusive start question id (manifest order).")
    p.add_argument("--end-id", default=None, help="Inclusive end question id (manifest order).")
    p.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Per-question timeout in seconds (default: %(default)s).",
    )
    p.add_argument("--resume", action="store_true", help="Skip questions already in run.jsonl.")
    p.add_argument(
        "--manifest",
        default=str(MANIFEST),
        help="Manifest JSONL to run (default: the frozen 67-Q benchmark).",
    )
    return p.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    produced = run_benchmark(
        args.run_dir,
        start_id=args.start_id,
        end_id=args.end_id,
        timeout=args.timeout,
        resume=args.resume,
        manifest_path=Path(args.manifest),
    )
    by_status: dict[str, int] = {}
    for rec in produced:
        by_status[rec["status"]] = by_status.get(rec["status"], 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(by_status.items())) or "nothing to do"
    print(f"[run_benchmark] {len(produced)} record(s) written to {args.run_dir}/run.jsonl ({summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
