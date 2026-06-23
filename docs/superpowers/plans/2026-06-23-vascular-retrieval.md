# Plan — P2 #7: vascular retrieval dilution (ACoA-aneurysm query pulled AVM-radiosurgery chapters)

**Bug:** A ruptured **anterior communicating artery (ACoA) aneurysm** query retrieved **AVM-radiosurgery**
chunks — a different vascular sub-domain (aneurysm clipping/coiling vs arteriovenous-malformation
radiosurgery). The Ask textbook lane has **no sub-domain gating**: `hybrid_search` (RRF) → a generic
cross-encoder rerank on `(query, chunk.text)` only. Nothing knows "aneurysm" vs "AVM", so a topically-near
AVM chunk survives.

**Root cause (scouted):** single chokepoint `neuro_core/query.py::Engine._retrieve` (both Ask sub-paths —
separate `query()` and woven `plan_retrieval()` — funnel through it). `rerank.py` is a pure cross-encoder
with no metadata signal. Existing domain maps that DO split aneurysm-vs-AVM (`ontology._SIGNALS`,
caseprep `CORPUS_SUBDOMAIN_KEYWORDS`) live in higher layers `neuro_core` must not import; `_detect_domain`
(the P2 #8 machinery) collapses both into one `"vascular"` bucket → useless here. No per-chunk domain
column exists (adding one = full reindex — rejected as non-lazy).

**Approach (lazy, recall-safe, tuning-free):** inline a tiny vascular-subdomain keyword map in `query.py`
and demote off-subdomain hits via a **stable sort**, not a score margin.
- The cross-encoder already scores ALL `retrieve_k`(=40) candidates regardless of `top_k` (it predicts on
  every pair, then truncates) — so rerank the full pool at no extra model cost, demote, then truncate to
  `rerank_k`(=12). A demoted AVM chunk falls below aneurysm chunks that were just outside the top-12.
- **Demotion = a stable sort on a binary `_offdomain` flag** (off-domain → bottom; cross-encoder score
  order preserved within each group). No penalty constant to tune against bge-reranker logits.
- **Recall-safe gating:** the flag fires ONLY when (a) the query has exactly ONE confident vascular
  subdomain AND (b) the chunk is confidently in a DIFFERENT subdomain (and not the query's). Queries with
  no subdomain, or both subdomains, touch nothing. Demoted chunks stay in the pool (demoted, not deleted)
  to backfill if on-domain hits are scarce — mirrors the `figure_guards` "DEMOTED, not blocked" philosophy.

---

- [x] **Step 1 — Inlined vascular-subdomain demotion in Engine._retrieve (neuro_core/query.py)**
  - Add module-level pure helpers in `query.py` (no upward import):
    ```python
    _VASCULAR_SUBDOMAINS = {
        "aneurysm": ("aneurysm", "acoa", "anterior communicating", "pcom", "mca aneurysm",
                     "basilar tip", "subarachnoid", "sah", "clipping", "coiling", "vasospasm"),
        "avm":      ("arteriovenous malformation", "avm", "nidus", "radiosurgery", "spetzler",
                     "dural arteriovenous", "davf", "cavernous malformation", "cavernoma"),
    }
    def _subdomains_in(text): -> set[str]   # lowercased substring match over the map
    def _offdomain(query, text) -> bool:    # True iff len(q_subs)==1 and h_subs and q_sub not in h_subs
    ```
  - In `Engine._retrieve` (currently `return self.reranker.rerank(question, hits, self.config.rerank_k)`):
    ```python
    ranked = self.reranker.rerank(question, hits, self.config.retrieve_k)  # score all, no extra CE cost
    ranked.sort(key=lambda h: _offdomain(question, h.text))  # stable: off-domain → bottom, scores preserved
    return ranked[: self.config.rerank_k]
    ```
  - Keep behavior identical for non-vascular / single-subdomain / ambiguous queries (no flag → no reorder).
  - `tests/neuro_core/test_query.py` (extend, hermetic — `FakeIndex`/`FakeReranker`, NO live index):
    - `FakeIndex` returns `[aneurysm Hit, AVM-radiosurgery Hit, neutral Hit]`; query "ruptured ACoA
      aneurysm clipping" → assert the AVM hit is demoted BELOW the aneurysm and neutral hits (and still
      present — not dropped).
    - Non-regression: a query with NO vascular subdomain ("vestibular schwannoma resection") leaves the
      hit order unchanged.
    - A query naming BOTH subdomains does not demote (len(q_subs)!=1).
    - Pure-helper unit tests: `_offdomain("ACoA aneurysm", "<avm radiosurgery text>")` True;
      `_offdomain("AVM radiosurgery", "<aneurysm clipping text>")` True; same-domain / no-domain False.
  - **Verify:** `cd <worktree> && PYTHONPATH=vendor/caseprep pytest -q tests/neuro_core/test_query.py
    tests/neuro_core/test_rerank.py tests/neuro_core/test_retrieve_for_synthesis.py`.

**Scope guard:** this is #7 (retrieval dilution) only. #8 (false "N papers contradict expected domain"
flag) is a SEPARATE path (caseprep `card_auditor`) and a later slice — do not touch it here. The inlined
map is intentionally just the two vascular subdomains in the bug; extensible later if other axes dilute.

**Non-regression invariant:** honest retrieval — demotion never deletes a hit (recall preserved), never
fabricates, and leaves non-vascular queries byte-identical. No engine/index/schema change; no reindex.
