# Guidelines Testing Sandbox — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Tasks 3 and 5 mutate the shared live index / spend API budget — run those inline with a human checkpoint, not unattended.**

**Goal:** Hold the 42 guidelines out of the live product in a physically isolated sandbox, and stand up a one-variable A/B (guidelines on/off, on a fast/cheap DeepSeek + Vertex-flash stack) using the existing `evaluation/` harness.

**Architecture:** Two index dirs are the A/B arms — live (`…/index`, reverted to 18 textbooks) and `…/index-sandbox` (60, with guidelines), selected by `INDEX_DIR`. A new `deepseek` synth provider lets the engine run on `deepseek-v4-flash`; disambiguation moves to Vertex `gemini-2.5-flash` (already supported). The model is held fixed across both arms so the only variable is the corpus.

**Tech Stack:** Python, LanceDB, `neuro_core` engine, the `evaluation/` benchmark harness, DeepSeek direct API (OpenAI-compatible), Vertex Gemini.

## Global Constraints

- **One variable only:** both A/B arms use the identical cheap model stack (`deepseek-v4-flash` synth, Vertex `gemini-2.5-flash` analyze). The corpus is the sole difference.
- **Live config is untouched:** never edit `DEFAULTS` for `SYNTH_PROVIDER`/`OPENROUTER_MODEL`/`ANALYZE_*`. Sandbox model selection is by **env only**, sourced from `~/.config/neuro-caseboard/sandbox.env` (gitignored, `chmod 600`, holds `DEEPSEEK_API_KEY`).
- **Secret hygiene:** never commit or echo `DEEPSEEK_API_KEY`; it stays outside the repo.
- **Append/copy, never re-embed:** index ops are row copies/deletes; no re-embedding.
- **Fresh baseline:** the existing `evaluation/runs/baseline-20260620-134705` is GLM-stack — it MUST NOT be the baseline arm (would confound model + corpus). Generate a new cheap-stack 18-textbook baseline.
- Install is `pip install -e .[dev]` only; tests are pytest; fast loop: `pytest tests/neuro_core -q`.

---

### Task 1: Add a `deepseek` synth provider

**Files:**
- Modify: `neuro_core/config.py` (DEFAULTS ~5-55, `Config` ~84-122, `load_config` ~134-173)
- Modify: `neuro_core/synth_clients.py` (add class after `LocalSynthClient`; branches in `make_synth_client` ~107-115 and `make_analyze_client` ~118-134)
- Test: `tests/neuro_core/test_synth_clients.py`

**Interfaces:**
- Produces: `DeepSeekSynthClient(api_key, model, base_url="https://api.deepseek.com", client=None)`; `make_synth_client(config)` returns it when `config.synth_provider == "deepseek"`; new config fields `deepseek_api_key`, `deepseek_model`, `deepseek_base_url`.

- [ ] **Step 1: Write the failing test** — append to `tests/neuro_core/test_synth_clients.py`:

```python
def test_deepseek_client_text_only_uses_base_url():
    fake = FakeOpenAI()
    from neuro_core.synth_clients import DeepSeekSynthClient
    c = DeepSeekSynthClient(api_key="k", model="deepseek-v4-flash",
                            base_url="https://api.deepseek.com", client=fake)
    out = c.generate("sys", "user", images=[b"\x89PNG"])  # images ignored (text-only)
    assert out == "answer text"
    assert c.base_url == "https://api.deepseek.com"
    assert fake.captured["model"] == "deepseek-v4-flash"
    # text-only: messages carry a plain string, not a multimodal content list
    assert isinstance(fake.captured["messages"][1]["content"], str)


def test_make_synth_client_routes_deepseek(monkeypatch):
    from neuro_core.config import load_config
    from neuro_core.synth_clients import make_synth_client, DeepSeekSynthClient
    for k in ("SYNTH_PROVIDER", "DEEPSEEK_MODEL", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SYNTH_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    cfg = load_config(env_file="/nonexistent")
    client = make_synth_client(cfg)
    assert isinstance(client, DeepSeekSynthClient)
    assert client.model == "deepseek-v4-flash"
    assert client.base_url == "https://api.deepseek.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/neuro_core/test_synth_clients.py::test_make_synth_client_routes_deepseek -q`
Expected: FAIL (`AttributeError: 'Config' object has no attribute 'deepseek_*'` / ImportError `DeepSeekSynthClient`).

- [ ] **Step 3: Add config knobs** — in `neuro_core/config.py`:

In `DEFAULTS`, after the `OPENROUTER_API_KEY` line:
```python
    "DEEPSEEK_API_KEY": "",
    "DEEPSEEK_MODEL": "deepseek-v4-flash",
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
```
In the `Config` dataclass, after `openrouter_api_key: str`:
```python
    deepseek_api_key: str
    deepseek_model: str
    deepseek_base_url: str
```
In `load_config`'s `Config(...)` call, after `openrouter_api_key=get("OPENROUTER_API_KEY"),`:
```python
        deepseek_api_key=get("DEEPSEEK_API_KEY"),
        deepseek_model=get("DEEPSEEK_MODEL"),
        deepseek_base_url=get("DEEPSEEK_BASE_URL"),
```

- [ ] **Step 4: Add the client + routing** — in `neuro_core/synth_clients.py`, after `LocalSynthClient`:

```python
class DeepSeekSynthClient(LocalSynthClient):
    """DeepSeek direct API (OpenAI-compatible). Text-only by design — DeepSeek chat
    models don't accept image parts, and the figure sources/captions are already in the
    prompt text, so citations are unaffected (same rationale as LocalSynthClient). Used
    by the guidelines sandbox for fast/cheap synthesis."""

    def __init__(self, api_key, model, base_url="https://api.deepseek.com", client=None):
        super().__init__(base_url=base_url, model=model, api_key=api_key, client=client)
```
In `make_synth_client`, before the final `return VertexSynthClient(...)`:
```python
    if config.synth_provider == "deepseek":
        return DeepSeekSynthClient(config.deepseek_api_key, config.deepseek_model,
                                   config.deepseek_base_url)
```
In `make_analyze_client`, before its final `return VertexSynthClient(...)` (symmetry; sandbox uses vertex for analyze, but keep providers consistent):
```python
    if provider == "deepseek":
        return DeepSeekSynthClient(config.deepseek_api_key, model, config.deepseek_base_url)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/neuro_core/test_synth_clients.py -q`
Expected: PASS (all, including the two new tests).

- [ ] **Step 6: Record DeepSeek in benchmark provenance** — in `evaluation/scripts/run_benchmark.py`, in the `model_configuration()` dict (~173-188), after the `analyze_model` line add:
```python
        "deepseek_model": env("DEEPSEEK_MODEL", "deepseek-v4-flash"),
```
(Display/provenance only — the engine reads env via `load_config`; this just stamps the run config so the report shows the right synth model.)

- [ ] **Step 7: Commit**

```bash
git add neuro_core/config.py neuro_core/synth_clients.py tests/neuro_core/test_synth_clients.py evaluation/scripts/run_benchmark.py
git commit -m "feat(synth): add deepseek direct-API provider for the guidelines sandbox"
```

---

### Task 2: Sandbox env + wiring verification

**Files:**
- Create: `eval/sandbox/sandbox.env.example` (committed; documents the knobs, no secret)
- Modify: `~/.config/neuro-caseboard/sandbox.env` (NOT in repo; add model knobs alongside the existing `DEEPSEEK_API_KEY`)
- Create: `eval/sandbox/README.md` (how to source the env + run an arm)

**Interfaces:**
- Produces: a sourceable env that selects the cheap stack; `INDEX_DIR` chooses the arm.

- [ ] **Step 1: Append model knobs to the out-of-repo sandbox env** (the file already holds `DEEPSEEK_API_KEY`):

```bash
cat >> ~/.config/neuro-caseboard/sandbox.env <<'EOF'
SYNTH_PROVIDER=deepseek
DEEPSEEK_MODEL=deepseek-v4-flash
ANALYZE_PROVIDER=vertex
ANALYZE_MODEL=gemini-2.5-flash
GOOGLE_CLOUD_PROJECT=project-a20782b0-fdca-45ec-bc7
GOOGLE_CLOUD_LOCATION=us-central1
EOF
chmod 600 ~/.config/neuro-caseboard/sandbox.env
```

- [ ] **Step 2: Create the committed example (no secret)** — `eval/sandbox/sandbox.env.example`:

```bash
# Copy to ~/.config/neuro-caseboard/sandbox.env and fill DEEPSEEK_API_KEY.
# Sandbox model stack — overrides the live GLM/gemini-flash-lite defaults by ENV ONLY.
DEEPSEEK_API_KEY=sk-REPLACE_ME
SYNTH_PROVIDER=deepseek
DEEPSEEK_MODEL=deepseek-v4-flash
ANALYZE_PROVIDER=vertex
ANALYZE_MODEL=gemini-2.5-flash
GOOGLE_CLOUD_PROJECT=project-a20782b0-fdca-45ec-bc7
GOOGLE_CLOUD_LOCATION=us-central1
```

- [ ] **Step 3: Verify the engine resolves the cheap stack** (no spend — just config + client construction):

```bash
set -a; . ~/.config/neuro-caseboard/sandbox.env; set +a
python3 -c "
from neuro_core.config import load_config
from neuro_core.synth_clients import make_synth_client, make_analyze_client
c=load_config(env_file='/nonexistent')
s=make_synth_client(c); a=make_analyze_client(c)
print('synth:', type(s).__name__, s.model)
print('analyze:', type(a).__name__, a.model)
assert type(s).__name__=='DeepSeekSynthClient' and s.model=='deepseek-v4-flash'
assert type(a).__name__=='VertexSynthClient' and a.model=='gemini-2.5-flash'
print('OK cheap stack wired')
"
```
Expected: `synth: DeepSeekSynthClient deepseek-v4-flash` / `analyze: VertexSynthClient gemini-2.5-flash` / `OK cheap stack wired`.

- [ ] **Step 4: Write `eval/sandbox/README.md`** (sourcing + arm selection):

```markdown
# Guidelines sandbox

Source the cheap stack, then pick an arm via INDEX_DIR:
    set -a; . ~/.config/neuro-caseboard/sandbox.env; set +a
    export INDEX_DIR=/home/michael/neuro-textbook-rag/index           # baseline arm (18)
    export INDEX_DIR=/home/michael/neuro-textbook-rag/index-sandbox   # treatment arm (60)
Both arms use the same model stack (deepseek-v4-flash + vertex gemini-2.5-flash);
the only variable is the corpus. See docs/superpowers/specs/2026-06-29-guidelines-testing-sandbox-design.md.
```

- [ ] **Step 5: Commit** (example + README only; the real env is out-of-repo)

```bash
git add eval/sandbox/sandbox.env.example eval/sandbox/README.md
git commit -m "chore(sandbox): document cheap-stack env + arm selection"
```

---

### Task 3: Physically isolate the index (copy sandbox, revert live) — INLINE, human-checkpointed

**Files (data, not code):**
- Create: `…/neuro-textbook-rag/index-sandbox/` (copy of the 60-source `.lance` tables)
- Modify: `…/neuro-textbook-rag/index/` (delete `GUIDELINES — %` rows → 18)
- Move: 42 `…/textbook_pdfs/GUIDELINES — *.pdf` → `…/guidelines_held/`

- [ ] **Step 1: Snapshot current state** (the deltas to verify against):

```bash
python3 -c "import lancedb,collections as C; db=lancedb.connect('/home/michael/neuro-textbook-rag/index'); [print(t, len(C.Counter(db.open_table(t).to_arrow().column('book').to_pylist()))) for t in ('chunks','figures')]"
```
Expected: `chunks 60` / `figures 44`.

- [ ] **Step 2: Copy the LanceDB tables to the sandbox (backup-first)**:

```bash
SRC=/home/michael/neuro-textbook-rag/index; DST=/home/michael/neuro-textbook-rag/index-sandbox
mkdir -p "$DST"
for t in chunks.lance figures.lance books.lance cards.lance meta.lance; do cp -a "$SRC/$t" "$DST/"; done
cp -a "$SRC"/*.json "$DST/" 2>/dev/null || true
python3 -c "import lancedb,collections as C; db=lancedb.connect('/home/michael/neuro-textbook-rag/index-sandbox'); print('sandbox chunks books:', len(C.Counter(db.open_table('chunks').to_arrow().column('book').to_pylist())))"
```
Expected: `sandbox chunks books: 60`. **Checkpoint:** confirm 60 before proceeding — this copy is the backup for the destructive Step 3.

- [ ] **Step 3: Revert the LIVE index to 18 textbooks** (delete guideline rows):

```bash
python3 -c "
import lancedb, collections as C
db=lancedb.connect('/home/michael/neuro-textbook-rag/index')
for t in ('chunks','figures'):
    tb=db.open_table(t)
    tb.delete(\"book LIKE 'GUIDELINES — %'\")
    n=len(C.Counter(tb.to_arrow().column('book').to_pylist()))
    print(t, 'books now', n)
"
```
Expected: `chunks books now 18` / `figures books now 18`. If either is not 18, STOP and restore from `index-sandbox`.

- [ ] **Step 4: Move the 42 guideline PDFs out of the live corpus**:

```bash
mkdir -p /home/michael/guidelines_held
mv -f "/home/michael/textbook_pdfs/GUIDELINES — "*.pdf /home/michael/guidelines_held/
echo "live corpus pdfs: $(ls -1 /home/michael/textbook_pdfs/*.pdf | grep -v '.bak' | wc -l)  (expect 18)"
echo "held guidelines: $(ls -1 /home/michael/guidelines_held/*.pdf | wc -l)  (expect 42)"
```
Expected: `live corpus pdfs: 18` / `held guidelines: 42`.

- [ ] **Step 5: Verify live is clean + figures still resolve in sandbox**:

```bash
python3 -c "
import lancedb,os
live=set(lancedb.connect('/home/michael/neuro-textbook-rag/index').open_table('chunks').to_arrow().column('book').to_pylist())
assert not any(b.startswith('GUIDELINES — ') for b in live), 'live still has guidelines!'
print('live clean: 0 guideline books,', len(live), 'total')
fb=lancedb.connect('/home/michael/neuro-textbook-rag/index-sandbox').open_table('figures').to_arrow()
fp=fb.column('figure_path')[0].as_py(); print('sandbox figure resolves:', os.path.exists(fp))
"
```
Expected: `live clean: 0 guideline books, 18 total` / `sandbox figure resolves: True`.

- [ ] **Step 6: Confirm live still passes its gate** (the revert restored the prior baseline):

```bash
python3 -m eval.run_eval 2>&1 | tail -5
```
Expected: gate PASS (no regression vs the 18-textbook baseline). If it references guideline sources as expected hits, that's a stale gate fixture — note it, don't edit to force-pass.

- [ ] **Step 7: Commit the run log** (index/assets are gitignored; only a log is tracked) — write `eval/sandbox/RUNLOG-index-isolation.md` recording the Step-1/3/4 counts, then:

```bash
git add eval/sandbox/RUNLOG-index-isolation.md
git commit -m "chore(sandbox): isolate index (sandbox=60, live reverted to 18, 42 guidelines held)"
```

---

### Task 4: Benchmark coverage check (+ frozen guideline question set if needed)

**Files:**
- Read: `evaluation/inputs/benchmark-manifest.jsonl`
- Conditionally create: `evaluation/inputs/guidelines-questions.manifest.jsonl` (frozen, guideline-sensitive)

- [ ] **Step 1: Inspect the frozen benchmark's domain/topic coverage**:

```bash
python3 -c "
import json,collections
rows=[json.loads(l) for l in open('evaluation/inputs/benchmark-manifest.jsonl') if l.strip()]
print('questions:', len(rows))
print('keys:', sorted(rows[0].keys()))
dom=collections.Counter(r.get('domain') or r.get('subspecialty') for r in rows)
print('domains:', dict(dom))
for r in rows[:8]: print(' -', (r.get('question') or r.get('prompt') or '')[:90])
"
```

- [ ] **Step 2: Decide coverage** — classify how many questions are *management/evidence* (guideline-sensitive: indications, thresholds, classifications, time windows, reversal/dosing) vs *anatomy/technique*. Record the count in `eval/sandbox/RUNLOG-coverage.md`.
  - **If ≥ ~15 guideline-sensitive questions exist:** use the frozen benchmark (or its guideline-sensitive subset of ids) as the A/B target. Skip Step 3.
  - **If under-covered:** author a frozen guideline-sensitive set (Step 3) — the guidelines help on management questions, so testing only anatomy/technique would under-measure them.

- [ ] **Step 3 (conditional): Author a frozen guideline-sensitive question set** — `evaluation/inputs/guidelines-questions.manifest.jsonl`, matching the benchmark manifest schema (`evaluation/schemas/benchmark-manifest.schema.json`), ~18 management/evidence questions across the guideline domains (stroke/AIS/ICH/SAH, TBI/ICP/decompressive crani, neuro-onc/WHO-CNS5, spine NASS/AO/NICE, functional/peds) **plus ~10 anatomy/technique guardrail questions** drawn from the existing benchmark verbatim. Validate:

```bash
python3 evaluation/scripts/validate_manifest.py evaluation/inputs/guidelines-questions.manifest.jsonl
```
Expected: validation OK.

- [ ] **Step 4: Commit**

```bash
git add eval/sandbox/RUNLOG-coverage.md evaluation/inputs/guidelines-questions.manifest.jsonl 2>/dev/null
git commit -m "test(sandbox): guideline-sensitive benchmark coverage check + question set"
```

---

### Task 5: Run the one-variable A/B (guidelines on/off, cheap stack) — INLINE, budget-aware

Follow the **`neuro-caseboard-ab-test` skill** procedure. This task pins the sandbox-specific settings; defer the grading sub-steps (blinded Claude subspecialty graders, drift control, early termination, regression scan) to that skill.

**Hard Gate (from the skill) — verify before any paid run:**
- Treatment change is live: `index-sandbox` has 60 books incl. the `GUIDELINES —` sources (Task 3 Step 5).
- Cheap stack is wired: Task 2 Step 3 printed `OK cheap stack wired`.

- [ ] **Step 1: Source the cheap stack + Vertex ADC check**:

```bash
set -a; . ~/.config/neuro-caseboard/sandbox.env; set +a
ls ~/.config/gcloud/application_default_credentials.json   # Vertex ADC must exist (analyze=vertex)
export PYTHONPATH="$PWD:$PWD/vendor/caseprep"
export CORPUS_DIR=/home/michael/textbook_pdfs
QSET=evaluation/inputs/benchmark-manifest.jsonl   # or guidelines-questions.manifest.jsonl (Task 4)
```

- [ ] **Step 2: Generate the FRESH cheap-stack BASELINE arm (18 textbooks)** — background, resumable, one id per call:

```bash
export INDEX_DIR=/home/michael/neuro-textbook-rag/index
BASE=evaluation/runs/sandbox-base-cheap-$(date +%Y%m%d-%H%M%S)
for ID in <ids-from-QSET>; do
  python3 evaluation/scripts/run_benchmark.py --run-dir "$BASE" --start-id "$ID" --end-id "$ID" --resume
done
python3 evaluation/scripts/finalize_run.py --run-dir "$BASE"
```

- [ ] **Step 3: Generate the TREATMENT arm (60, guidelines)** — same stack, sandbox index:

```bash
export INDEX_DIR=/home/michael/neuro-textbook-rag/index-sandbox
TREAT=evaluation/runs/sandbox-guidelines-cheap-$(date +%Y%m%d-%H%M%S)
for ID in <same-ids>; do
  python3 evaluation/scripts/run_benchmark.py --run-dir "$TREAT" --start-id "$ID" --end-id "$ID" --resume
done
python3 evaluation/scripts/finalize_run.py --run-dir "$TREAT"
```

- [ ] **Step 4: Attribution check** — confirm guidelines actually reached the graded answers:

```bash
grep -ho 'GUIDELINES — [^"]*' "$TREAT"/*.json* 2>/dev/null | sort | uniq -c | sort -rn | head
```
Expected: many citations of `GUIDELINES —` sources in the treatment answers, ~0 in baseline. If treatment answers don't cite guidelines, the lift (if any) isn't from them — investigate before grading.

- [ ] **Step 5: Blinded paired grading** — per the `neuro-caseboard-ab-test` skill: build blinded pairs (`make_blinded_pair.py`), dispatch one **Claude** subspecialty grader per question (rubric `evaluation/inputs/nsgy-grader.txt`, temperature 0, A/B order hidden), grade incrementally, and **drift-control** by re-grading the baseline blinded in the same pass. Stop early only on a one-sided, ≥30%-graded `CLEAR` verdict.

- [ ] **Step 6: Verdict + regression scan + record** — apply the graduation rule: promote only if guideline-sensitive quality ↑ AND textbook-anchored non-inferior AND citations correct/current. Scan every question for regressions / retrieval-crowding. Record both arms in the results ledger and write a SUMMARY with a keep/revert call + the latency/cost read for the cheap stack:

```bash
python3 evaluation/scripts/update_results.py --ab "$TREAT" --label "guidelines on cheap stack (deepseek-v4-flash + vertex 2.5-flash)"
```

- [ ] **Step 7: Commit the SUMMARY + results** (run dirs are gitignored; the SUMMARY/RESULTS are tracked):

```bash
git add evaluation/RESULTS.md eval/sandbox/SUMMARY-guidelines-ab.md
git commit -m "test(sandbox): A/B verdict — guidelines on the cheap stack"
```

---

## Self-Review

- **Spec coverage:** index isolation (T3), held corpus (T3 S4), sandbox model stack + DeepSeek client (T1, T2), reuse of `evaluation/` harness with fresh cheap-stack baseline (T5), benchmark coverage check (T4), graduation rule + latency/cost read (T5 S6), reversibility (held PDFs + `index-sandbox` backup, T3). All spec sections map to a task.
- **Placeholders:** the only intentional fill-ins are `<ids-from-QSET>` / `<same-ids>` in T5 (the chosen question ids depend on T4's coverage decision) — the skill's step 2 governs id selection; not a code placeholder. Grading sub-steps in T5 S5 delegate to the documented `neuro-caseboard-ab-test` skill rather than duplicating it (avoids drift from the actual scripts).
- **Type consistency:** `DeepSeekSynthClient(api_key, model, base_url, client)`, config fields `deepseek_api_key/_model/_base_url`, and provider string `"deepseek"` are used identically across T1, T2, and `make_synth_client`.
