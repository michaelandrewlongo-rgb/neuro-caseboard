# C1 — Corpus evidence-currency (DEFERRED — investigation only)

**FACT.** Lane A (the grounded answer) is retrieved from a **static textbook index**. The corpus is a
fixed set of textbook PDFs at `/home/michael/textbook_pdfs` (e.g. *Benzel Spine*, *Greenberg Handbook
of Neurosurgery*, *Schmidek and Sweet*, *Spine Surgery Tricks of the Trade* (Vaccaro), *Decision Making
in Neurovascular Disease*) indexed into LanceDB at `/home/michael/neuro-textbook-rag/index`
(`chunks.lance`, `figures.lance`, …). These editions predate the 2022–2025 trial readouts the benchmark
penalizes for currency; the index has no temporal-recency lane and is only refreshed by an explicit
`build_index` run (see the incremental-sync memo). So a textbook-only answer is structurally bounded by
its publication dates.

**FACT — a literature/PubMed lane exists and IS invoked by default.** `neuro_caseboard/literature/`
implements Lane B; `neuro_caseboard/qa.py:103-132` (`answer_question`) runs `lane_a` and `lane_b`
concurrently, and `lane_b` defaults to `build_literature_section(question, …)` (`qa.py:110-112`,
`qa.py:41-100`). It is **enabled by default**: `load_literature_config` reads
`LITERATURE_RETRIEVAL` defaulting to `"true"` with `recency_years` default `7`
(`neuro_caseboard/literature/config.py:73-78`).

**KEY CAVEAT (FACT).** Lane B is **strictly additive** — "any failure yields literature=None and never
blocks or alters Lane A's grounded answer" (`qa.py:1-5`). It populates a separate
`QAResult.literature` section (`qa.py:38,131`); it does **not** feed the grounded synthesis and does
**not** substitute when Lane A is thin/empty. The benchmark grades the Lane A `answer` field, so a
contemporary PubMed result does not raise the currency of the graded answer.

**HYPOTHESIS (deferred fix direction, not implemented):** currency would improve either by re-indexing
newer editions / adding a dated-evidence lane, or by letting Lane B evidence inform the graded answer
(not just ride alongside it). Out of scope for the current fix cycle.
