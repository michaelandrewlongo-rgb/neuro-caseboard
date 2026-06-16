# Design — WS-3: PubMed in the case build (separate `[L#]` axis)

- **Date:** 2026-06-16
- **Status:** Approved (locked by LOOP_PROMPT §4 WS-3); implementation in progress
- **Branch:** `worktree-streamlit-executive-navy-loop`
- **Loop:** Case Dossier engine, Pass 3 of 5 · builds on WS-1/WS-2

## 1. Context & problem
The PubMed lane (`literature/` + `qa.build_literature_section`) today augments **`ask` only**. The
case dossier's **Clinical Reasoning**, **Alternatives**, and **Risks** surfaces must each carry a
synthesized, recency-bounded contemporary-literature paragraph with `[L#]` PMID/DOI citations, on a
**separate axis** from corpus `[n]` (mirror the ask lane's separation; never merge the spaces).

## 2. Decisions
- **Reuse the existing lane verbatim.** `qa.build_literature_section(question, *, client, synth_client,
  lit_config, cache)` already returns a `LiteratureSection(narrative, citations=[LiteratureCitation
  (n,pmid,title,journal,year,doi,url)])` or `None`, fully injectable for offline tests, and **never
  fabricates** (synth cites only the records passed; citations enumerate those same records). WS-3
  calls it once per target section with a case-tuned query — no new synthesis logic.
- **Separate axis, structurally.** Literature attaches to the **`Section`** (new optional field
  `literature`), numbered `[L1..]` *per section*. Corpus evidence stays where it is (claim markers +
  appendix "Evidence Sources"); the dossier shows no inline corpus `[n]`, so the spaces cannot
  collide. The model field is duck-typed (`literature=None`, holds a `LiteratureSection`-shaped
  object) so `model.py` stays decoupled (no import of `qa`).
- **Respect env flags.** Gating via `load_literature_config()` (`LITERATURE_RETRIEVAL`,
  `LITERATURE_RECENCY_YEARS`, `LITERATURE_K`, `NCBI_API_KEY`). `build_case_dossier` gains a
  `literature=None` arg (None → `config.enabled`); offline tests/eval pass `literature=False` or
  inject canned clients so **required CI never touches the network**.
- **Topic-agnostic queries.** Per-section query = `case.to_topic()` + a generic focus token
  (`indications outcomes` / `treatment alternatives` / `complications`) — process words, not clinical
  content. The lane's own `rewrite_pubmed_query` (LLM) refines it when a provider exists.

## 3. Detailed design
### 3.1 `model.py` (extend, non-breaking)
Add to `Section`: `literature: object | None = None` (duck-typed; a `LiteratureSection`-shaped object
with `.narrative` + `.citations`). Default `None` → no behavior change for build/ask. No confidence
axis (unchanged).

### 3.2 `neuro_caseboard/case_literature.py` (new)
```python
LIT_SECTIONS = {"Clinical Reasoning": "indications outcomes",
                "Alternatives": "treatment alternatives comparison",
                "Risks": "complications"}

def section_query(heading, case) -> str | None:   # to_topic() + focus token; None if not a lit section

def attach_case_literature(dossier, case, *, client=None, synth_client=None,
                           lit_config=None, cache=None, build_fn=None) -> Dossier:
    """For each section in LIT_SECTIONS, build a LiteratureSection via build_literature_section
    (injectable build_fn for tests) and set section.literature. Per-section failure → left None
    (additive, never blocks). Returns the dossier."""
```

### 3.3 `pipeline.build_case_dossier` (extend)
Add `literature=None, lit_client=None, lit_synth_client=None, lit_cache=None`. After
`compile_case_dossier`, if `literature` (None → `load_literature_config().enabled`), call
`attach_case_literature(dossier, case, client=lit_client, synth_client=lit_synth_client,
cache=lit_cache)`. Lane failures are swallowed by `build_literature_section` (additive).

### 3.4 `render_md.py` (extend)
After a section's claims/figures, if `sec.literature` and its narrative: render a
`**Contemporary Literature**` block — the narrative then one `[L#] title — journal year · link`
row per citation (link = `https://doi.org/{doi}` or `url`). Mirrors the ask CLI's literature print.
(PDF case surface lands in WS-5; markdown + board_view cover WS-3.)

## 4. Acceptance criteria (LOOP_PROMPT §5 WS-3)
- Reasoning / Alternatives / Risks each cite **≥1 real PubMed item** on the `[L#]` axis (proved
  offline with injected canned records).
- **Zero fabricated citations** — every `[L#]` resolves to a returned record (synth cites only the
  provided studies; citations enumerate `syn.records`). A test asserts the rendered `[L#]` set ⊆ the
  injected records' PMIDs.
- Corpus `[n]` and literature `[L#]` spaces **never collide** (distinct render lanes; test asserts the
  literature block is separate from claims/appendix).
- Offline tests with injected responses green; no network in required CI. Existing `ask` literature
  path unchanged.

## 5. Testing strategy (offline)
`tests/test_case_literature.py`:
- `section_query` returns a query for the 3 sections (containing the topic), `None` otherwise;
  topic-agnostic (built from case fields).
- `attach_case_literature` with an injected `cache` (canned `LiteratureRecord`s) + `synth_client`
  (stub `.generate`) + a `lit_config(enabled=True)`: the 3 target sections get `.literature` with
  `[L#]` citations; non-target sections stay `None`; every citation PMID ∈ the injected records
  (no fabrication); `LITERATURE_RETRIEVAL` disabled → no attachment.
`tests/test_render_md.py` (extend): a Section with a `literature` object renders the narrative +
`[L#]` rows; a section without one is unchanged.
`tests/test_pipeline.py` (extend): `build_case_dossier(..., literature=True, lit_cache=<canned>,
lit_synth_client=<stub>)` attaches literature to the 3 sections offline; `literature=False` attaches
none. Existing offline section test passes `literature=False`.
`tests/test_compile.py`/`test_model`: `Section.literature` defaults None; no confidence axis.

## 6. EVAL
`eval/case_eval.py` (extend): with an injected canned lit cache+synth, report how many of the 3
lit-bearing sections carry ≥1 `[L#]` per case, and assert no `[L#]` outside the injected PMIDs.
Live PubMed grade (real recency/relevance) **deferred** — no `NCBI_API_KEY` here (as WS-1/WS-2).

## 7. Risks
- **Network in CI** → mitigated: offline tests inject cache/synth; `build_case_dossier` offline
  callers pass `literature=False`.
- **Citation-space collision** → mitigated: `[L#]` lives only in the per-section literature block,
  `[n]`/figures elsewhere; test guards separation.
- **Fabrication** → inherited guarantee from `synthesize_literature` + enumerated citations; test
  asserts `[L#] ⊆ injected PMIDs`.

## 8. Out of scope
PDF rendering of the case literature (WS-5), generated figures (WS-4), CLI/Streamlit (WS-5). No new
runtime dependency (httpx already core).
