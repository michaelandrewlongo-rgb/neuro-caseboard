# Ask Knob-Sweep Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the harness that produces clean, single-variable, glm-5.2 answer-set **pairs**
(`control` vs `one knob changed`) on the bake-off 21-question set, for the user to grade by eye.

**Architecture:** Small additions to the existing in-process benchmark runner
(`evaluation/scripts/run_benchmark.py`) plus four standalone helper scripts. No grading code, no
statistics — the deliverable is answer artifacts with airtight provenance. Every arm is a fresh
process exporting a frozen env block and overriding exactly one variable; the only structural
changes are (1) letting the CLI point at a non-default manifest and (2) making `run-config.json`
record the retrieval knobs so arms are self-documenting.

**Tech Stack:** Python 3, `pytest` (the only CI gate), LanceDB (read-only), the vendored
`neuro_core` / `neuro_caseboard` engine, OpenRouter (`z-ai/glm-5.2`).

**Spec:** `docs/superpowers/specs/2026-06-26-ask-knob-sweep-design.md`

## Global Constraints

- **Frozen env block** (every run exports this verbatim, then overrides ONE var):

  ```bash
  export PYTHONPATH="$PWD:$PWD/vendor/caseprep"
  export SYNTH_PROVIDER=openrouter   OPENROUTER_MODEL=z-ai/glm-5.2
  export ANALYZE_PROVIDER=openrouter ANALYZE_MODEL=google/gemini-3.1-flash-lite
  export RETRIEVE_K=40 RERANK_K=12
  export EMBED_MODEL=BAAI/bge-large-en-v1.5  RERANK_MODEL=BAAI/bge-reranker-v2-m3
  export LITERATURE_WEAVE=true LITERATURE_K=12
  export LITERATURE_CACHE_DIR="$PWD/eval/pubmed-snapshot" LITERATURE_CACHE_TTL_DAYS=36500
  export MAX_FIGURE_IMAGES=0
  export INDEX_DIR=/home/michael/neuro-textbook-rag/index CORPUS_DIR=/home/michael/textbook_pdfs
  # OPENROUTER_API_KEY + NCBI_API_KEY auto-load from repo .env
  ```

- **One variable per arm.** Nothing else may differ between `control` and an arm.
- **Never pollute** the frozen 67-Q manifest `evaluation/inputs/benchmark-manifest.jsonl`.
- **Cost:** glm-5.2 = `$0.95/M` in, `$3.00/M` out, ≈`$0.02/answer`. Report `$` per arm.
- **Tests:** `pytest` only. Run **scoped** (`pytest tests/evaluation -q`); **never** add
  `pytest-xdist -n auto` (OOMs WSL). Guard any `streamlit` import with `pytest.importorskip`.
- **Commit cadence:** one commit per task. Branch: `eval/ask-knob-sweep`.
- **Committed vs runtime:** committed = the runner change, the 4 helper scripts, the 21-Q manifest,
  the runbook, tests. Runtime-only (NOT committed) = `eval/pubmed-snapshot/` (cache),
  `evaluation/runs/*` (answer sets), `eval/index-fingerprint.json` (provenance dump).

---

### Task 1: `--manifest` CLI flag

Lets the CLI run the standalone 21-Q manifest. `run_benchmark()` already accepts `manifest_path`;
only the CLI wiring is missing.

**Files:**
- Modify: `evaluation/scripts/run_benchmark.py` (`_parse_args` ~479-491; `main` ~494-508)
- Test: `tests/evaluation/test_runner.py`

**Interfaces:**
- Consumes: existing `run_benchmark(..., manifest_path: Path = MANIFEST)`.
- Produces: CLI flag `--manifest <path>`; `_parse_args(argv).manifest` (str, defaults to
  `str(MANIFEST)`).

- [ ] **Step 1: Write the failing tests** — append to `tests/evaluation/test_runner.py`:

```python
def test_parse_args_accepts_manifest_with_default():
    ns = runner._parse_args(["--run-dir", "r"])
    assert Path(ns.manifest) == runner.MANIFEST
    ns2 = runner._parse_args(["--run-dir", "r", "--manifest", "eval/x.jsonl"])
    assert ns2.manifest == "eval/x.jsonl"


def test_run_benchmark_honors_custom_manifest(tmp_path):
    manifest = tmp_path / "mini.jsonl"
    manifest.write_text(
        json.dumps({"id": "Q-1", "domain": "Test", "question": "What?",
                    "benchmark_version": "x", "enabled": True}) + "\n",
        encoding="utf-8",
    )
    produced = runner.run_benchmark(
        tmp_path / "run", answer_fn=lambda q: make_qaresult(answer="ok"),
        manifest_path=manifest, sleep_fn=lambda _s: None,
    )
    assert [r["question_id"] for r in produced] == ["Q-1"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/evaluation/test_runner.py::test_parse_args_accepts_manifest_with_default -q`
Expected: FAIL — `AttributeError: 'Namespace' object has no attribute 'manifest'`.

- [ ] **Step 3: Add the flag** — in `_parse_args`, after the `--resume` line:

```python
    p.add_argument(
        "--manifest",
        default=str(MANIFEST),
        help="Manifest JSONL to run (default: the frozen 67-Q benchmark).",
    )
```

- [ ] **Step 4: Thread it through `main`** — in `main`, pass it to `run_benchmark`:

```python
    produced = run_benchmark(
        args.run_dir,
        start_id=args.start_id,
        end_id=args.end_id,
        timeout=args.timeout,
        resume=args.resume,
        manifest_path=Path(args.manifest),
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/evaluation/test_runner.py -q`
Expected: PASS (all, including the two new tests).

- [ ] **Step 6: Commit**

```bash
git add evaluation/scripts/run_benchmark.py tests/evaluation/test_runner.py
git commit -m "feat(eval): --manifest flag on run_benchmark CLI (run a non-default manifest)"
```

---

### Task 2: Auto-provenance in `model_configuration()`

Make `run-config.json` record the true provider + retrieval knobs, so every arm self-documents
(replaces manual stamping). Keep the function engine-free (no `neuro_core` import).

**Files:**
- Modify: `evaluation/scripts/run_benchmark.py` (`model_configuration` 163-184)
- Test: `tests/evaluation/test_runner.py`

**Interfaces:**
- Produces: `model_configuration()` dict gains keys `openrouter_model, analyze_provider,
  analyze_model, retrieve_k, rerank_k, rerank_model, embed_model, literature_weave, literature_k,
  max_figure_images`; `synth_provider` default flips `vertex`→`openrouter`.

- [ ] **Step 1: Write the failing test** — append to `tests/evaluation/test_runner.py`:

```python
def test_model_configuration_records_provider_and_retrieval_knobs(monkeypatch):
    for k in ("SYNTH_PROVIDER", "OPENROUTER_MODEL", "ANALYZE_MODEL", "RETRIEVE_K",
              "RERANK_K", "RERANK_MODEL", "EMBED_MODEL", "LITERATURE_WEAVE",
              "LITERATURE_K", "MAX_FIGURE_IMAGES"):
        monkeypatch.delenv(k, raising=False)
    # defaults reflect the PR-80 engine, NOT a stale "vertex"
    cfg = runner.model_configuration()
    assert cfg["synth_provider"] == "openrouter"
    assert cfg["openrouter_model"] == "z-ai/glm-5.2"
    assert cfg["retrieve_k"] == "40"
    assert cfg["rerank_k"] == "12"
    assert cfg["embed_model"] == "BAAI/bge-large-en-v1.5"
    # env overrides win
    monkeypatch.setenv("RERANK_K", "20")
    monkeypatch.setenv("SYNTH_PROVIDER", "openrouter")
    assert runner.model_configuration()["rerank_k"] == "20"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/evaluation/test_runner.py::test_model_configuration_records_provider_and_retrieval_knobs -q`
Expected: FAIL — `KeyError: 'openrouter_model'` (and `synth_provider == "vertex"`).

- [ ] **Step 3: Replace `model_configuration()`** with:

```python
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
```

- [ ] **Step 4: Guard against a strict schema** — confirm no run-config schema rejects extra keys:

Run: `grep -rl "synth_provider\|model_configuration" evaluation/schemas/ || echo "no run-config schema"`
Expected: either "no run-config schema", or a schema file. If a schema exists AND contains
`"additionalProperties": false` under `model_configuration`, delete that line (additive keys must
be allowed). Otherwise no action.

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/evaluation/test_runner.py -q`
Expected: PASS (new test + the existing `test_run_benchmark_writes_config_and_appends` still green).

- [ ] **Step 6: Commit**

```bash
git add evaluation/scripts/run_benchmark.py tests/evaluation/test_runner.py
git commit -m "feat(eval): run-config.json records provider + retrieval knobs (arm self-provenance)"
```

---

### Task 3: The 21-question bake-off manifest

A standalone manifest (10 hard benchmark qids byte-identical to the frozen 67 + 10 easy + 1 custom),
plus tests that pin its shape and the hard-qid identity.

**Files:**
- Create: `evaluation/inputs/bakeoff-21.manifest.jsonl`
- Test: `tests/evaluation/test_bakeoff_manifest.py`

**Interfaces:**
- Produces: a 21-row JSONL conforming to `evaluation/schemas/benchmark-manifest.schema.json`
  (keys `id, domain, question, benchmark_version, enabled`).

- [ ] **Step 1: Build the manifest file.** Compose `evaluation/inputs/bakeoff-21.manifest.jsonl`:
  1. **10 hard rows** — copy the rows for `NIS-02, OPEN-CV-04, OPEN-CV-07, TUMOR-01, TUMOR-05,
     SPINE-01, SPINE-06, FUNCTIONAL-02, TRAUMA-02, GENERAL-01` **verbatim** from
     `evaluation/inputs/benchmark-manifest.jsonl` (same `id`, `domain`, `question`).
  2. **10 easy rows** — `id` `EASY-01`..`EASY-10`, `domain "Board-style"`, `question` transcribed
     **verbatim** from `~/Downloads/neuro-caseboard-ask-glm-5.2_2026-06-26.pdf` (the 10 numbered
     board-style questions; read it with the Read tool).
  3. **1 custom row** — `id "CUSTOM-11"`, `domain "Open Cerebrovascular Surgery"`, `question`
     transcribed from `~/Downloads/neuro-caseboard-ask-HARD-glm-5.2_2026-06-26.pdf` (the ruptured
     right-M2 aneurysm operative-technique question).
  - All rows: `"benchmark_version": "bakeoff-21:2026-06-26"`, `"enabled": true`.

- [ ] **Step 2: Write the validation tests** — `tests/evaluation/test_bakeoff_manifest.py`:

```python
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
M21 = REPO / "evaluation" / "inputs" / "bakeoff-21.manifest.jsonl"
M67 = REPO / "evaluation" / "inputs" / "benchmark-manifest.jsonl"
HARD = {"NIS-02", "OPEN-CV-04", "OPEN-CV-07", "TUMOR-01", "TUMOR-05",
        "SPINE-01", "SPINE-06", "FUNCTIONAL-02", "TRAUMA-02", "GENERAL-01"}


def _rows(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_manifest_has_21_unique_enabled_rows():
    rows = _rows(M21)
    assert len(rows) == 21
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == 21
    assert all(r["enabled"] for r in rows)
    for r in rows:
        assert r["question"].strip()
        for f in ("id", "domain", "question", "benchmark_version", "enabled"):
            assert f in r


def test_hard_qids_are_byte_identical_to_frozen_benchmark():
    committed = {r["id"]: r["question"] for r in _rows(M67)}
    got = {r["id"]: r["question"] for r in _rows(M21)}
    assert HARD.issubset(set(got))
    for qid in HARD:
        assert got[qid] == committed[qid], f"{qid} text drifted from the frozen benchmark"
```

- [ ] **Step 3: Run to verify pass**

Run: `pytest tests/evaluation/test_bakeoff_manifest.py -q`
Expected: PASS. If `test_hard_qids...` fails, a hard row was not copied verbatim — fix the manifest.

- [ ] **Step 4: Commit**

```bash
git add evaluation/inputs/bakeoff-21.manifest.jsonl tests/evaluation/test_bakeoff_manifest.py
git commit -m "test(eval): bake-off 21-Q manifest (hard qids pinned to the frozen benchmark)"
```

---

### Task 4: Index fingerprint script

Records row counts + an order-independent id-hash per LanceDB table, so the index state is anchored
before the sweep and re-checkable after the embedder re-index.

**Files:**
- Create: `evaluation/scripts/index_fingerprint.py`
- Test: `tests/evaluation/test_index_fingerprint.py`

**Interfaces:**
- Produces: `fingerprint_ids(rows: int, ids: list[str], schema: list[str]) -> dict` (pure);
  `fingerprint_index(index_dir: str, tables=("chunks","figures","cards")) -> dict` (LanceDB).

- [ ] **Step 1: Write the failing tests** — `tests/evaluation/test_index_fingerprint.py`:

```python
import hashlib
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "index_fingerprint", REPO / "evaluation" / "scripts" / "index_fingerprint.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_fingerprint_ids_is_order_independent():
    a = mod.fingerprint_ids(3, ["c", "a", "b"], ["text", "id"])
    b = mod.fingerprint_ids(3, ["a", "b", "c"], ["id", "text"])
    assert a == b
    assert a["rows"] == 3
    assert a["schema"] == ["id", "text"]
    assert a["id_sha256"] == hashlib.sha256("a\nb\nc".encode()).hexdigest()


def test_fingerprint_ids_changes_on_content():
    a = mod.fingerprint_ids(3, ["a", "b", "c"], ["id"])
    b = mod.fingerprint_ids(3, ["a", "b", "d"], ["id"])
    assert a["id_sha256"] != b["id_sha256"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/evaluation/test_index_fingerprint.py -q`
Expected: FAIL — `ModuleNotFoundError` / file not found (script doesn't exist yet).

- [ ] **Step 3: Write the script** — `evaluation/scripts/index_fingerprint.py`:

```python
#!/usr/bin/env python3
"""Row counts + order-independent id-hash per LanceDB table (read-only index provenance)."""
from __future__ import annotations

import hashlib
import json
import os
import sys


def fingerprint_ids(rows: int, ids: list[str], schema: list[str]) -> dict:
    h = hashlib.sha256("\n".join(sorted(map(str, ids))).encode("utf-8")).hexdigest()
    return {"rows": rows, "schema": sorted(schema), "id_sha256": h}


def fingerprint_index(index_dir: str, tables=("chunks", "figures", "cards")) -> dict:
    import lancedb

    db = lancedb.connect(index_dir)
    out: dict = {}
    for name in tables:
        t = db.open_table(name)
        df = t.to_pandas()
        idcol = "id" if "id" in df.columns else df.columns[0]
        out[name] = fingerprint_ids(
            int(t.count_rows()),
            df[idcol].astype(str).tolist(),
            [f.name for f in t.schema],
        )
    return out


if __name__ == "__main__":
    idx = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "INDEX_DIR", "/home/michael/neuro-textbook-rag/index")
    print(json.dumps({"index_dir": idx, "tables": fingerprint_index(idx)}, indent=2))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/evaluation/test_index_fingerprint.py -q`
Expected: PASS (pure-function tests).

- [ ] **Step 5: Smoke against the live index**

Run: `python3 evaluation/scripts/index_fingerprint.py /home/michael/neuro-textbook-rag/index`
Expected: JSON with `chunks`/`figures`/`cards` row counts > 0 and a 64-char `id_sha256` each.

- [ ] **Step 6: Commit**

```bash
git add evaluation/scripts/index_fingerprint.py tests/evaluation/test_index_fingerprint.py
git commit -m "feat(eval): index fingerprint script (row counts + id-hash per LanceDB table)"
```

---

### Task 5: PubMed literature-only warm script

Populates the frozen PubMed cache over the 21 questions (fetch + cheap rewrite, no synthesis), so
every textbook arm hits byte-identical literature.

**Files:**
- Create: `evaluation/scripts/warm_pubmed.py`
- Test: `tests/evaluation/test_warm_pubmed.py`

**Interfaces:**
- Produces: `warm(questions: list[tuple[str, str]], retrieve_fn) -> list[tuple[str, int, bool]]`
  (pure loop; each entry is `(qid, n_records, ok)`).

- [ ] **Step 1: Write the failing test** — `tests/evaluation/test_warm_pubmed.py`:

```python
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "warm_pubmed", REPO / "evaluation" / "scripts" / "warm_pubmed.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_warm_calls_retrieve_for_each_and_tolerates_failure():
    calls = []

    def rf(q):
        calls.append(q)
        if q == "boom":
            raise RuntimeError("ncbi down")
        return (["r1", "r2"], "search query")

    res = mod.warm([("A", "qa"), ("B", "boom"), ("C", "qc")], rf)
    assert calls == ["qa", "boom", "qc"]          # every question attempted, in order
    assert res == [("A", 2, True), ("B", 0, False), ("C", 2, True)]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/evaluation/test_warm_pubmed.py -q`
Expected: FAIL — file not found.

- [ ] **Step 3: Write the script** — `evaluation/scripts/warm_pubmed.py`:

```python
#!/usr/bin/env python3
"""Warm the frozen PubMed cache over a manifest (Lane-B retrieval only; no synthesis).

retrieve_records() fetches + caches under the deterministic build_query_terms key, so a later
cache hit during the actual runs skips the LLM rewrite entirely — literature stays frozen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def warm(questions, retrieve_fn):
    """Call retrieve_fn(question) for each (qid, question); return [(qid, n_records, ok)]."""
    out = []
    for qid, q in questions:
        try:
            recs, _ = retrieve_fn(q)
            out.append((qid, len(recs), True))
        except Exception:  # noqa: BLE001 — one bad question must not abort warming
            out.append((qid, 0, False))
    return out


def _load_questions(manifest_path):
    rows = [json.loads(l) for l in Path(manifest_path).read_text(encoding="utf-8").splitlines()
            if l.strip()]
    return [(r["id"], r["question"]) for r in rows if r.get("enabled", True)]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    manifest = argv[0] if argv else str(REPO / "evaluation" / "inputs" / "bakeoff-21.manifest.jsonl")

    from neuro_caseboard.literature.config import load_literature_config
    from neuro_caseboard.qa import retrieve_records
    from neuro_core.config import load_config
    from neuro_core.synth_clients import make_synth_client

    lit_config = load_literature_config()
    synth_client = make_synth_client(load_config())

    def retrieve_fn(q):
        return retrieve_records(q, lit_config=lit_config, synth_client=synth_client)

    results = warm(_load_questions(manifest), retrieve_fn)
    ok = sum(1 for _, _, good in results if good)
    print(f"[warm_pubmed] cache_dir={lit_config.cache_dir} ttl_days={lit_config.cache_ttl_days}")
    for qid, n, good in results:
        print(f"  {qid:<12} records={n:<3} {'ok' if good else 'FAILED'}")
    print(f"[warm_pubmed] {ok}/{len(results)} warmed")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/evaluation/test_warm_pubmed.py -q`
Expected: PASS (pure-loop test; no network).

- [ ] **Step 5: Commit**

```bash
git add evaluation/scripts/warm_pubmed.py tests/evaluation/test_warm_pubmed.py
git commit -m "feat(eval): PubMed warm script (freeze Lane-B records over the 21-Q manifest)"
```

---

### Task 6: Run-pair diff emitter

Joins a control `run.jsonl` and an arm `run.jsonl` by question id into one `baseline-vs-<knob>.md`,
hard questions first, for the user to grade.

**Files:**
- Create: `evaluation/scripts/make_pair.py`
- Test: `tests/evaluation/test_make_pair.py`

**Interfaces:**
- Produces: `render_pair(control: dict, arm: dict, hard_ids: set, knob_label: str) -> str`
  where `control`/`arm` map `qid -> {"question","answer"}`.

- [ ] **Step 1: Write the failing test** — `tests/evaluation/test_make_pair.py`:

```python
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "make_pair", REPO / "evaluation" / "scripts" / "make_pair.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_render_pair_orders_hard_first_and_includes_both_answers():
    control = {"EASY-01": {"question": "qe", "answer": "ctrl easy"},
               "NIS-02": {"question": "qh", "answer": "ctrl hard"}}
    arm = {"EASY-01": {"question": "qe", "answer": "arm easy"},
           "NIS-02": {"question": "qh", "answer": "arm hard"}}
    md = mod.render_pair(control, arm, {"NIS-02"}, "RERANK_K=20")
    assert "RERANK_K=20" in md
    # hard section appears before easy section
    assert md.index("NIS-02") < md.index("EASY-01")
    # both answers present for each question
    for token in ("ctrl hard", "arm hard", "ctrl easy", "arm easy"):
        assert token in md
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/evaluation/test_make_pair.py -q`
Expected: FAIL — file not found.

- [ ] **Step 3: Write the script** — `evaluation/scripts/make_pair.py`:

```python
#!/usr/bin/env python3
"""Render a side-by-side control-vs-arm answer pair (hard questions first) for manual grading."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load_answers(run_jsonl) -> dict:
    out = {}
    for line in Path(run_jsonl).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out[r["question_id"]] = {"question": r.get("question", ""), "answer": r.get("answer") or ""}
    return out


def render_pair(control: dict, arm: dict, hard_ids: set, knob_label: str) -> str:
    qids = sorted(set(control) & set(arm), key=lambda q: (q not in hard_ids, q))
    lines = [f"# Baseline vs `{knob_label}`", ""]
    for qid in qids:
        tier = "HARD" if qid in hard_ids else "easy"
        lines += [f"## {qid} ({tier})", "", f"**Q:** {control[qid]['question']}", "",
                  "### baseline", control[qid]["answer"], "",
                  f"### {knob_label}", arm[qid]["answer"], "", "---", ""]
    return "\n".join(lines)


HARD = {"NIS-02", "OPEN-CV-04", "OPEN-CV-07", "TUMOR-01", "TUMOR-05",
        "SPINE-01", "SPINE-06", "FUNCTIONAL-02", "TRAUMA-02", "CUSTOM-11"}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 3:
        print("usage: make_pair.py CONTROL/run.jsonl ARM/run.jsonl 'KNOB=value' [out.md]")
        return 2
    control, arm, label = load_answers(argv[0]), load_answers(argv[1]), argv[2]
    md = render_pair(control, arm, HARD, label)
    out = Path(argv[3]) if len(argv) > 3 else Path(argv[1]).parent / "baseline-vs-arm.md"
    out.write_text(md, encoding="utf-8")
    print(f"[make_pair] wrote {out} ({len(set(control) & set(arm))} questions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/evaluation/test_make_pair.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evaluation/scripts/make_pair.py tests/evaluation/test_make_pair.py
git commit -m "feat(eval): make_pair.py — side-by-side control-vs-arm answer sheet"
```

---

### Task 7: The operator runbook

The single doc that drives Phase 1 (preflight) + control + the env-only arms. No code; it ties the
scripts together with copy-pasteable commands.

**Files:**
- Create: `evaluation/BAKEOFF-SWEEP-RUNBOOK.md`

- [ ] **Step 1: Write the runbook** — `evaluation/BAKEOFF-SWEEP-RUNBOOK.md`:

````markdown
# Bake-off 21-Q Knob-Sweep Runbook

Spec: `docs/superpowers/specs/2026-06-26-ask-knob-sweep-design.md`. One variable per arm; report `$`.

## 0. Frozen env block (paste into every fresh shell, then override ONE var)

```bash
cd /home/michael/PROJECTS/neuro-caseboard
export PYTHONPATH="$PWD:$PWD/vendor/caseprep"
export SYNTH_PROVIDER=openrouter   OPENROUTER_MODEL=z-ai/glm-5.2
export ANALYZE_PROVIDER=openrouter ANALYZE_MODEL=google/gemini-3.1-flash-lite
export RETRIEVE_K=40 RERANK_K=12
export EMBED_MODEL=BAAI/bge-large-en-v1.5  RERANK_MODEL=BAAI/bge-reranker-v2-m3
export LITERATURE_WEAVE=true LITERATURE_K=12
export LITERATURE_CACHE_DIR="$PWD/eval/pubmed-snapshot" LITERATURE_CACHE_TTL_DAYS=36500
export MAX_FIGURE_IMAGES=0
export INDEX_DIR=/home/michael/neuro-textbook-rag/index CORPUS_DIR=/home/michael/textbook_pdfs
printenv SYNTH_PROVIDER OPENROUTER_MODEL RERANK_K   # sanity: openrouter / z-ai/glm-5.2 / 12
```

## 1. Preflight (once)

```bash
# contamination audit — expect exit 0 / "nothing deletable"
python3 -m neuro_core.scripts.purge_contamination --index-dir "$INDEX_DIR"; echo "exit=$?"
# index fingerprint — anchor the index state
python3 evaluation/scripts/index_fingerprint.py "$INDEX_DIR" | tee eval/index-fingerprint.json
# freeze PubMed (fetch + cheap rewrite; ~$0.02 total) — populates eval/pubmed-snapshot/
python3 evaluation/scripts/warm_pubmed.py evaluation/inputs/bakeoff-21.manifest.jsonl
```

## 2. Control run (the baseline leg)

```bash
RUN=evaluation/runs/control-$(date +%Y%m%d-%H%M%S)
python3 evaluation/scripts/run_benchmark.py --run-dir "$RUN" \
    --manifest evaluation/inputs/bakeoff-21.manifest.jsonl --timeout 300
python3 evaluation/scripts/finalize_run.py --run-dir "$RUN"
# Liveness: spot-check answers resemble the bake-off glm-5.2 quality (~86 easy / ~90 hard).
echo "CONTROL=$RUN"   # save this path; every arm diffs against it
```

## 3. Env-only arms (zero code) — one var over the frozen block

```bash
# Output breadth: RERANK_K 12 -> 20
RERANK_K=20 RUN=evaluation/runs/rerank_k-20-$(date +%Y%m%d-%H%M%S) \
  python3 evaluation/scripts/run_benchmark.py --run-dir "$RUN" \
    --manifest evaluation/inputs/bakeoff-21.manifest.jsonl --timeout 300
# Candidate breadth: RETRIEVE_K 40 -> 80
RETRIEVE_K=80 RUN=evaluation/runs/retrieve_k-80-$(date +%Y%m%d-%H%M%S) \
  python3 evaluation/scripts/run_benchmark.py --run-dir "$RUN" \
    --manifest evaluation/inputs/bakeoff-21.manifest.jsonl --timeout 300
# (finalize_run.py on each; run-config.json now records the knob automatically)
```

## 4. Make the grading sheet (per arm)

```bash
python3 evaluation/scripts/make_pair.py \
    "$CONTROL/run.jsonl" "$ARM/run.jsonl" "RERANK_K=20" "$ARM/baseline-vs-rerank_k-20.md"
```

## 5. Cost

Per arm ≈ 21 × $0.02 ≈ **$0.42** (glm-5.2 $0.95/$3.00 per M). Read actual tokens from each
answer's `raw_response`; report `$` after every arm.

## Code-change arms (separate just-in-time plans)

- Reranker (RRF-only off-switch; Qwen3-0.6B scorer), PubMed rewrite (toggle `rewrite_pubmed_query`),
  embedder (Qwen3 re-index + query-prefix fix), fusion (`index.py` RRF k/weights), figures
  (`MAX_FIGURE_IMAGES>0`). Each gets its own plan when reached; see the spec §6 phases A/D/E/F.
````

- [ ] **Step 2: Commit**

```bash
git add evaluation/BAKEOFF-SWEEP-RUNBOOK.md
git commit -m "docs(eval): bake-off 21-Q knob-sweep runbook (preflight + control + env-only arms)"
```

---

## Self-Review

**1. Spec coverage:**
- Phase 0 harness honesty → Tasks 1, 2. ✓
- Phase 0 21-Q manifest → Task 3. ✓
- Phase 1 contamination audit + fingerprint + freeze → Task 4 (fingerprint), Task 5 (warm), runbook §1. ✓
- Control run + env-only arms (B, C) → runbook §2, §3. ✓
- Single-variable / frozen env / cost reporting → Global Constraints + runbook §0, §5. ✓
- Deliverable pair sheet → Task 6. ✓
- **Deferred (by design):** code-change arms A/D/E/F → separate just-in-time plans (noted in runbook
  + spec §6). Not a gap — explicit YAGNI gating.

**2. Placeholder scan:** the 11 transcribed question texts in Task 3 are a data-extraction step with
an exact procedure + source PDFs + validating tests — not a code placeholder. No "TBD"/"handle
errors" placeholders elsewhere.

**3. Type consistency:** `fingerprint_ids`/`fingerprint_index` (Task 4), `warm` (Task 5),
`render_pair`/`load_answers` (Task 6), and `--manifest`→`manifest_path` (Task 1) names match across
their tests and call sites. `model_configuration()` keys (Task 2) match the test assertions.
