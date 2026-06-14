# Local Quantized Synthesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `local` synthesis provider so the RAG pipeline answers via a local quantized LLM (Ollama) on the user's GPU, gated by a per-query GPU readiness guard, with zero cloud spend.

**Architecture:** A new `LocalSynthClient` (OpenAI-compatible, pointed at Ollama) joins the existing `vertex`/`openrouter` providers behind `make_synth_client`. It is text-only (figure sources/captions stay in the prompt text). A new `engine/gpu_guard.py` runs before every query via the shared `engine.query.query()` entrypoint (used by both CLI and server); if another process is using the GPU or free VRAM is below budget, it aborts with a clear message.

**Tech Stack:** Python, `openai` client (OpenAI-compatible), Ollama runtime, `qwen2.5:7b` GGUF, `nvidia-smi` for GPU inspection, pytest with dependency-injection fakes.

---

## File Structure

- `engine/config.py` (modify) — add `LOCAL_BASE_URL`, `LOCAL_MODEL`, `GPU_GUARD`, `GPU_MIN_FREE_MIB` config keys.
- `engine/synth_clients.py` (modify) — add `LocalSynthClient` (text-only) + route `local` in `make_synth_client`.
- `engine/gpu_guard.py` (create) — GPU inspection + readiness evaluation + `ensure_gpu_ready`.
- `engine/query.py` (modify) — call the guard at the start of `query()` for the `local` provider; add `force` passthrough.
- `cli/ask.py` (modify) — `--force` flag + friendly `GpuNotReadyError` handling.
- `.env.example` (modify) — document the new keys.
- `tests/test_config.py`, `tests/test_synth_clients.py`, `tests/test_gpu_guard.py` (create), `tests/test_query.py` — unit coverage.

Operational (no code): install Ollama, build a `num_ctx`-tuned model, verify end-to-end.

---

### Task 1: Config keys for local provider + GPU guard

**Files:**
- Modify: `engine/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_local_provider_defaults(tmp_path, monkeypatch):
    for k in ("LOCAL_BASE_URL", "LOCAL_MODEL"):
        monkeypatch.delenv(k, raising=False)
    cfg = load_config(env_file=str(tmp_path / "missing.env"))
    assert cfg.local_base_url == "http://localhost:11434/v1"
    assert cfg.local_model == "qwen2.5:7b"


def test_gpu_guard_defaults(tmp_path, monkeypatch):
    for k in ("GPU_GUARD", "GPU_MIN_FREE_MIB"):
        monkeypatch.delenv(k, raising=False)
    cfg = load_config(env_file=str(tmp_path / "missing.env"))
    assert cfg.gpu_guard is True
    assert cfg.gpu_min_free_mib == 10000


def test_gpu_guard_toggle_off(tmp_path):
    env = tmp_path / ".env"
    env.write_text("GPU_GUARD=off\nGPU_MIN_FREE_MIB=8000\n")
    cfg = load_config(env_file=str(env))
    assert cfg.gpu_guard is False
    assert cfg.gpu_min_free_mib == 8000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/michael/neuro-textbook-rag && python -m pytest tests/test_config.py -q`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'local_base_url'` (and similar).

- [ ] **Step 3: Add the four keys to `DEFAULTS`**

In `engine/config.py`, change the `DEFAULTS` block. Replace:

```python
    "OPENROUTER_MODEL": "anthropic/claude-sonnet-4.6",
    "OPENROUTER_API_KEY": "",
```

with:

```python
    "OPENROUTER_MODEL": "anthropic/claude-sonnet-4.6",
    "OPENROUTER_API_KEY": "",
    "LOCAL_BASE_URL": "http://localhost:11434/v1",
    "LOCAL_MODEL": "qwen2.5:7b",
    "GPU_GUARD": "true",
    "GPU_MIN_FREE_MIB": "10000",
```

- [ ] **Step 4: Add the fields to the `Config` dataclass**

In `engine/config.py`, replace:

```python
    openrouter_model: str
    openrouter_api_key: str
```

with:

```python
    openrouter_model: str
    openrouter_api_key: str
    local_base_url: str
    local_model: str
    gpu_guard: bool
    gpu_min_free_mib: int
```

- [ ] **Step 5: Wire the fields in `load_config`**

In `engine/config.py`, replace:

```python
        openrouter_model=get("OPENROUTER_MODEL"),
        openrouter_api_key=get("OPENROUTER_API_KEY"),
```

with:

```python
        openrouter_model=get("OPENROUTER_MODEL"),
        openrouter_api_key=get("OPENROUTER_API_KEY"),
        local_base_url=get("LOCAL_BASE_URL"),
        local_model=get("LOCAL_MODEL"),
        gpu_guard=get("GPU_GUARD").strip().lower() in ("1", "true", "yes", "on"),
        gpu_min_free_mib=int(get("GPU_MIN_FREE_MIB")),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -q`
Expected: PASS (all config tests green).

- [ ] **Step 7: Commit**

```bash
git add engine/config.py tests/test_config.py
git commit -m "feat: config keys for local synth provider and GPU guard"
```

---

### Task 2: LocalSynthClient (text-only) + provider routing

**Files:**
- Modify: `engine/synth_clients.py`
- Test: `tests/test_synth_clients.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_synth_clients.py`, change the import line:

```python
from engine.synth_clients import OpenRouterSynthClient, make_synth_client
```

to:

```python
from engine.synth_clients import (
    LocalSynthClient,
    OpenRouterSynthClient,
    make_synth_client,
)
```

Then append:

```python
def test_make_synth_client_selects_local():
    class Cfg:
        synth_provider = "local"
        local_base_url = "http://localhost:11434/v1"
        local_model = "qwen2.5:7b"

    c = make_synth_client(Cfg())
    assert isinstance(c, LocalSynthClient)
    assert c.base_url == "http://localhost:11434/v1"
    assert c.model == "qwen2.5:7b"


def test_local_is_text_only_even_with_images():
    # Text-only by design: figure images are dropped, the user prompt is sent as a
    # plain string (no image_url parts), citations come from the prompt text.
    fake = FakeOpenAI()
    c = LocalSynthClient(base_url="http://x/v1", model="m", client=fake)
    out = c.generate("SYS", "USER", images=[b"PNGBYTES"])
    assert out == "answer text"
    msgs = fake.captured["messages"]
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[1] == {"role": "user", "content": "USER"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_synth_clients.py -q`
Expected: FAIL — `ImportError: cannot import name 'LocalSynthClient'`.

- [ ] **Step 3: Implement `LocalSynthClient` and route it**

In `engine/synth_clients.py`, insert this class immediately after the `OpenRouterSynthClient` class (before `class VertexSynthClient`):

```python
class LocalSynthClient(OpenRouterSynthClient):
    """Local OpenAI-compatible backend (Ollama / llama.cpp). Runs on your own GPU:
    no passages/figures leave the machine, no cloud spend. Text-only by design — a
    local text model can't use figure images, but the figure sources/captions are
    already in the prompt text, so citations are unaffected. api_key is a dummy the
    local server ignores (the openai client requires a non-empty value)."""

    def __init__(self, base_url, model, api_key="local", client=None):
        super().__init__(api_key=api_key, model=model, client=client)
        self.base_url = base_url

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def generate(self, system, user, images):
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""
```

Then, in `make_synth_client`, add the `local` branch as the first check:

```python
def make_synth_client(config):
    if config.synth_provider == "local":
        return LocalSynthClient(config.local_base_url, config.local_model)
    if config.synth_provider == "openrouter":
        return OpenRouterSynthClient(config.openrouter_api_key,
                                     config.openrouter_model)
    return VertexSynthClient(config.google_cloud_project,
                             config.google_cloud_location,
                             config.vertex_model)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_synth_clients.py -q`
Expected: PASS (new local tests green; existing openrouter tests still green).

- [ ] **Step 5: Commit**

```bash
git add engine/synth_clients.py tests/test_synth_clients.py
git commit -m "feat: text-only LocalSynthClient and local provider routing"
```

---

### Task 3: GPU readiness guard module

**Files:**
- Create: `engine/gpu_guard.py`
- Test: `tests/test_gpu_guard.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gpu_guard.py`:

```python
import pytest

from engine.gpu_guard import (
    GpuNotReadyError,
    GpuProcess,
    GpuState,
    ensure_gpu_ready,
    evaluate_readiness,
    query_gpu_state,
)


def _runner(mem, procs):
    """Fake nvidia-smi: returns `mem` for the memory query, `procs` otherwise."""
    def run(args):
        if any("memory.total" in a for a in args):
            return mem
        return procs
    return run


class _Cfg:
    gpu_min_free_mib = 10000


def test_query_gpu_state_parses_memory_and_processes():
    runner = _runner("12227, 11944\n",
                     "1234, /usr/bin/python3, 4096\n5678, ollama, 5000\n")
    state = query_gpu_state(runner)
    assert state.total_mib == 12227
    assert state.free_mib == 11944
    assert state.processes == [
        GpuProcess(1234, "/usr/bin/python3", 4096),
        GpuProcess(5678, "ollama", 5000),
    ]


def test_query_gpu_state_empty_process_list():
    state = query_gpu_state(_runner("12227, 11944\n", "\n"))
    assert state.processes == []


def test_ready_when_clear_and_enough_free():
    state = GpuState(12227, 11944, [])
    ok, _ = evaluate_readiness(state, min_free_mib=10000, our_pid=999)
    assert ok is True


def test_not_ready_when_foreign_process_present():
    state = GpuState(12227, 6000, [GpuProcess(1234, "comfyui-python", 6000)])
    ok, msg = evaluate_readiness(state, min_free_mib=10000, our_pid=999)
    assert ok is False
    assert "1234" in msg


def test_our_ollama_counts_as_available():
    # Ollama holds the warm model (ours): free is low but effective free is fine.
    state = GpuState(12227, 6900, [GpuProcess(4321, "ollama", 5000)])
    ok, _ = evaluate_readiness(state, min_free_mib=10000, our_pid=999)
    assert ok is True  # 6900 + 5000 = 11900 >= 10000


def test_not_ready_when_insufficient_free():
    state = GpuState(12227, 8000, [])
    ok, msg = evaluate_readiness(state, min_free_mib=10000, our_pid=999)
    assert ok is False
    assert "8000" in msg


def test_ensure_raises_when_not_ready():
    runner = _runner("12227, 6000\n", "1234, comfyui, 6000\n")
    with pytest.raises(GpuNotReadyError):
        ensure_gpu_ready(_Cfg(), runner=runner, our_pid=999)


def test_ensure_force_bypasses_check():
    def boom(args):
        raise AssertionError("runner must not be called when force=True")
    ensure_gpu_ready(_Cfg(), runner=boom, our_pid=999, force=True)  # no raise


def test_ensure_skips_when_no_nvidia_smi():
    def missing(args):
        raise FileNotFoundError("nvidia-smi")
    ensure_gpu_ready(_Cfg(), runner=missing, our_pid=999)  # no raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_gpu_guard.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.gpu_guard'`.

- [ ] **Step 3: Implement the guard**

Create `engine/gpu_guard.py`:

```python
import os
import subprocess
from dataclasses import dataclass


class GpuNotReadyError(RuntimeError):
    """Raised when the GPU is busy with another process or lacks free VRAM."""


@dataclass
class GpuProcess:
    pid: int
    name: str
    used_mib: int


@dataclass
class GpuState:
    total_mib: int
    free_mib: int
    processes: list  # list[GpuProcess]


def _default_runner(args):
    return subprocess.run(["nvidia-smi", *args], capture_output=True,
                          text=True, check=True).stdout


def query_gpu_state(runner=_default_runner):
    mem = runner(["--query-gpu=memory.total,memory.free",
                  "--format=csv,noheader,nounits"])
    total_s, free_s = (x.strip() for x in mem.strip().splitlines()[0].split(","))
    procs_out = runner(["--query-compute-apps=pid,process_name,used_memory",
                        "--format=csv,noheader,nounits"])
    processes = []
    for line in procs_out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3 or not parts[0].isdigit():
            continue
        pid_s, name, used_s = parts
        processes.append(GpuProcess(pid=int(pid_s), name=name,
                                    used_mib=int(used_s) if used_s.isdigit() else 0))
    return GpuState(total_mib=int(total_s), free_mib=int(free_s),
                    processes=processes)


def _is_ours(proc, our_pid, ours_name_substrings):
    if proc.pid == our_pid:
        return True
    low = proc.name.lower()
    return any(s in low for s in ours_name_substrings)


def evaluate_readiness(state, min_free_mib, our_pid,
                       ours_name_substrings=("ollama",), foreign_floor_mib=300):
    """Pure check. Returns (ok, message). 'ours' = this process or Ollama; their
    VRAM counts as available because we reuse it. A foreign process holding more
    than `foreign_floor_mib` (ignores tiny display usage) means the GPU isn't
    clear; otherwise we need effective free VRAM >= min_free_mib."""
    foreign = [p for p in state.processes
               if not _is_ours(p, our_pid, ours_name_substrings)]
    ours_used = sum(p.used_mib for p in state.processes
                    if _is_ours(p, our_pid, ours_name_substrings))
    foreign_used = sum(p.used_mib for p in foreign)
    effective_free = state.free_mib + ours_used

    if foreign_used > foreign_floor_mib:
        procs = ", ".join(f"{p.name} (pid {p.pid}, {p.used_mib} MiB)"
                          for p in foreign)
        return False, (f"GPU is in use by another process: {procs}. Free it (or "
                       f"re-run with --force) before a local-model query.")
    if effective_free < min_free_mib:
        return False, (f"GPU has only {effective_free} MiB available but this query "
                       f"needs >= {min_free_mib} MiB. Close other GPU work, or lower "
                       f"GPU_MIN_FREE_MIB / use a smaller model.")
    return True, (f"GPU ready: {effective_free} MiB available "
                  f"(need {min_free_mib} MiB).")


def ensure_gpu_ready(config, runner=_default_runner, our_pid=None, force=False):
    """Raise GpuNotReadyError unless the GPU is clear and has budget. `force`
    skips the check; a missing nvidia-smi (no NVIDIA GPU) also skips it."""
    if force:
        return
    our_pid = os.getpid() if our_pid is None else our_pid
    try:
        state = query_gpu_state(runner)
    except FileNotFoundError:
        return
    ok, message = evaluate_readiness(state, config.gpu_min_free_mib, our_pid)
    if not ok:
        raise GpuNotReadyError(message)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_gpu_guard.py -q`
Expected: PASS (all 9 tests green).

- [ ] **Step 5: Commit**

```bash
git add engine/gpu_guard.py tests/test_gpu_guard.py
git commit -m "feat: per-query GPU readiness guard"
```

---

### Task 4: Wire the guard into the query path + CLI `--force`

**Files:**
- Modify: `engine/query.py`
- Modify: `cli/ask.py`
- Test: `tests/test_query.py`

- [ ] **Step 1: Write the failing wiring tests**

Append to `tests/test_query.py`:

```python
import engine.query as q


def _stub_engine(_config):
    class _E:
        def query(self, question):
            return f"ANS:{question}"
    return _E()


def test_query_runs_guard_for_local_provider(monkeypatch):
    calls = {}

    class Cfg:
        synth_provider = "local"
        gpu_guard = True

    monkeypatch.setattr(q, "ensure_gpu_ready",
                        lambda config, force=False: calls.__setitem__("force", force))
    monkeypatch.setattr(q, "get_engine", _stub_engine)
    out = q.query("hi", config=Cfg(), force=True)
    assert out == "ANS:hi"
    assert calls["force"] is True  # force propagated to the guard


def test_query_skips_guard_for_non_local(monkeypatch):
    calls = {}

    class Cfg:
        synth_provider = "vertex"
        gpu_guard = True

    monkeypatch.setattr(q, "ensure_gpu_ready",
                        lambda config, force=False: calls.__setitem__("ran", True))
    monkeypatch.setattr(q, "get_engine", _stub_engine)
    q.query("hi", config=Cfg())
    assert "ran" not in calls


def test_query_skips_guard_when_disabled(monkeypatch):
    calls = {}

    class Cfg:
        synth_provider = "local"
        gpu_guard = False

    monkeypatch.setattr(q, "ensure_gpu_ready",
                        lambda config, force=False: calls.__setitem__("ran", True))
    monkeypatch.setattr(q, "get_engine", _stub_engine)
    q.query("hi", config=Cfg())
    assert "ran" not in calls
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_query.py -q`
Expected: FAIL — `AttributeError: module 'engine.query' has no attribute 'ensure_gpu_ready'` (and `query()` rejects the `force` kwarg).

- [ ] **Step 3: Add the guard import and call in `engine/query.py`**

In `engine/query.py`, add to the imports near the top (after `from .synth_clients import make_synth_client`):

```python
from .gpu_guard import ensure_gpu_ready
```

Then replace the module-level `query` function at the bottom:

```python
def query(question, config=None):
    return get_engine(config).query(question)
```

with:

```python
def query(question, config=None, force=False):
    config = config or load_config()
    if config.synth_provider == "local" and config.gpu_guard:
        ensure_gpu_ready(config, force=force)
    return get_engine(config).query(question)
```

- [ ] **Step 4: Run wiring tests to verify they pass**

Run: `python -m pytest tests/test_query.py -q`
Expected: PASS.

- [ ] **Step 5: Add `--force` and friendly error handling to the CLI**

Replace the entire contents of `cli/ask.py` with:

```python
import argparse
import sys

from engine.gpu_guard import GpuNotReadyError
from engine.query import query


def main():
    ap = argparse.ArgumentParser(
        description="Ask the neurosurgery textbook RAG a clinical question.")
    ap.add_argument("question", help="The clinical question, in quotes")
    ap.add_argument("--force", action="store_true",
                    help="Run even if the GPU readiness guard fails.")
    args = ap.parse_args()

    try:
        result = query(args.question, force=args.force)
    except GpuNotReadyError as e:
        print(f"GPU not ready: {e}", file=sys.stderr)
        sys.exit(1)

    print(result.answer)
    print("\nSources:")
    for c in result.citations:
        loc = c.book + (f", {c.chapter}" if c.chapter else "") + f", p.{c.page}"
        print(f"  [{c.n}] {loc}")
    if result.figures:
        print("\nFigures:")
        for f in result.figures:
            print(f"  [{f.source_n}] {f.book}, p.{f.page} -> {f.image_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the full suite to confirm nothing regressed**

Run: `python -m pytest -q`
Expected: PASS (entire suite green).

- [ ] **Step 7: Commit**

```bash
git add engine/query.py cli/ask.py tests/test_query.py
git commit -m "feat: run GPU guard before local queries; add --force"
```

---

### Task 5: Document the new env keys

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Update the SYNTH_PROVIDER comment and append the local block**

In `.env.example`, change:

```
SYNTH_PROVIDER=vertex
```

to:

```
SYNTH_PROVIDER=vertex          # vertex | openrouter | local
```

Then append at the end of the file:

```
# Local synthesis (Ollama) — runs on your own GPU; zero cloud spend, text-only.
# To use: set SYNTH_PROVIDER=local above, start Ollama, build the num_ctx model
# (see docs/superpowers/plans/2026-06-09-local-quantized-synthesis.md Task 6),
# then point LOCAL_MODEL at it.
LOCAL_BASE_URL=http://localhost:11434/v1
LOCAL_MODEL=qwen2.5:7b

# GPU readiness guard — checked before each local-model query. Aborts (with a
# clear message) if another process is using the GPU or effective free VRAM is
# below GPU_MIN_FREE_MIB. Our own warm Ollama model counts as available.
GPU_GUARD=true
GPU_MIN_FREE_MIB=10000
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: document local provider and GPU guard env keys"
```

---

### Task 6: Install Ollama and build the context-tuned model (operational)

No code; verify each command's output before moving on. If a command's output differs from "Expected," stop and resolve it.

- [ ] **Step 1: Install Ollama**

Run: `curl -fsSL https://ollama.com/install.sh | sh`  (may prompt for sudo)
Expected: installs the `ollama` binary. Verify: `ollama --version` prints a version string.

- [ ] **Step 2: Start the Ollama server (WSL2 may lack systemd)**

Run (background): `ollama serve > /tmp/ollama.log 2>&1 &`
Then verify: `curl -s http://localhost:11434/api/tags`
Expected: JSON (e.g. `{"models":[]}`) — server reachable. (If a systemd service already started it, the curl still succeeds; skip the manual start.)

- [ ] **Step 3: Pull the base model**

Run: `ollama pull qwen2.5:7b`
Expected: downloads ~4.7 GB and finishes with `success`. (GPU placement is verified in Step 5.)

- [ ] **Step 4: Build a context-tuned model so passages aren't truncated**

Create `~/neuro-textbook-rag/Modelfile.local` with:

```
FROM qwen2.5:7b
PARAMETER num_ctx 8192
PARAMETER temperature 0.1
```

Run: `ollama create qwen2.5-7b-rag -f /home/michael/neuro-textbook-rag/Modelfile.local`
Expected: prints layer creation steps then `success`.

- [ ] **Step 5: Verify the model loads 100% on GPU (no CPU offload)**

Run: `ollama run qwen2.5-7b-rag "Reply with the single word: ok"`
Expected: prints `ok` (or similar) — first run loads the model.
Run: `ollama ps`
Expected: a row for `qwen2.5-7b-rag` whose PROCESSOR column reads **`100% GPU`**. If it shows any `% CPU`, lower `num_ctx` (e.g. 6144) and rebuild, or use a smaller quant, until it reads 100% GPU.

- [ ] **Step 6: Smoke-test the OpenAI-compatible endpoint**

Run:

```bash
curl -s http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-7b-rag","messages":[{"role":"user","content":"Reply with: pong"}]}' \
  | head -c 400
```

Expected: a JSON chat-completion whose message content contains `pong`. This is the exact path `LocalSynthClient` uses.

---

### Task 7: End-to-end verification (validate before integration)

**Files:**
- Modify (local only, not committed): `.env`

- [ ] **Step 1: Point the app at the local provider**

Edit `/home/michael/neuro-textbook-rag/.env` to set (add or change these lines):

```
SYNTH_PROVIDER=local
LOCAL_MODEL=qwen2.5-7b-rag
GPU_GUARD=true
GPU_MIN_FREE_MIB=10000
```

- [ ] **Step 2: In-corpus question returns a cited answer**

Run: `cd /home/michael/neuro-textbook-rag && python -m cli.ask "What are the surgical approaches to a vestibular schwannoma?"`
Expected: a concise answer containing at least one bracketed citation like `[2]`, followed by a `Sources:` list. (Substitute any question you know the corpus covers.)

- [ ] **Step 3: Out-of-corpus question refuses**

Run: `python -m cli.ask "What is the capital of France?"`
Expected: prints exactly `Not found in the provided sources.` with no `Sources:` entries.

- [ ] **Step 4: Confirm the model stayed 100% on GPU during the real query**

Run: `ollama ps`
Expected: `qwen2.5-7b-rag` still `100% GPU`. (Run this right after Step 2/3 while the model is warm.)

- [ ] **Step 5: The guard trips when the GPU can't handle the workload**

Temporarily force the budget above total VRAM to simulate a busy GPU:
Run: `GPU_MIN_FREE_MIB=99999 python -m cli.ask "anything"`
Expected: exits non-zero and prints `GPU not ready: GPU has only <N> MiB available but this query needs >= 99999 MiB ...` — no traceback, no synthesis attempted.
Then confirm the override works:
Run: `GPU_MIN_FREE_MIB=99999 python -m cli.ask "anything" --force`
Expected: the guard is skipped and the query runs (or fails later for unrelated reasons), proving `--force` bypasses the guard.

- [ ] **Step 6: Full test suite green**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 7: Final commit (any remaining tracked changes)**

```bash
git add -A
git commit -m "chore: local quantized synthesis verified end-to-end" || echo "nothing to commit"
```

(Note: `.env` is git-ignored, so it is not committed — only tracked code/docs are.)

---

## Done criteria

- `SYNTH_PROVIDER=local` answers an in-corpus question with citations and refuses out-of-corpus.
- The model runs 100% on GPU (`ollama ps`) with no CPU offload.
- The per-query guard aborts with a clear message when the GPU is busy / under budget, and `--force` overrides it.
- Full `pytest` suite is green.
