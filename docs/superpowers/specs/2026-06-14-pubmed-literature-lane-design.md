# Contemporary Literature Lane (PubMed) for Caseboard Q&A — Design

**Date:** 2026-06-14
**Status:** Approved design, pre-implementation
**Branch:** `worktree-pubmed-literature-lane`

## 1. Goal

When a user asks a Q&A question, augment the existing textbook+figure grounded
answer with a **separate "Contemporary Literature" section**: a *synthesized
narrative summary* (compressed, readable prose — not a bullet list of one-liners)
of relevant recent PubMed literature, with **per-study citations**. The textbook
answer's strict grounding is never weakened by open-world literature.

### Decisions locked in brainstorming
- **Output shape:** separate section, *synthesized narrative prose* with per-study
  citations. More than a one-line takeaway per study; compressed and readable.
- **Trigger:** **always-on** — every Q&A question fires the PubMed lane.
- **Access path:** **port caseprep's proven httpx E-utilities client** into caseboard.
  The in-session PubMed MCP server is a dev aid only; it does not exist at the
  CLI/Streamlit runtime, so it cannot be the product dependency.

## 2. Architecture — two non-crossing grounded lanes

The two existing systems have opposite grounding philosophies. We preserve both by
keeping them as independent lanes with **separate citation namespaces**:

- **Lane A (unchanged):** `neuro_core.query.query()` → `QueryResult(answer,
  citations, figures)`, grounded in the local textbook corpus, cites `book/page`,
  refuses when it can't ground. `neuro_core` stays a pure closed-corpus engine.
- **Lane B (new):** question → PubMed retrieve → `synthesize_literature()` →
  narrative prose grounded only in retrieved abstracts, cites `[L#]` → PMID/DOI.

**Composition point:** both Q&A entry points (`neuro_caseboard/cli.py`,
`app/streamlit_app.py`) currently call `neuro_core.query.query()` directly. They
switch to a single new caseboard orchestrator that runs Lane A + Lane B
**concurrently** and returns an extended result. `neuro_core` is not modified.

```
question ──┬─► Lane A: neuro_core.query.query() ─► answer + figures   [1][2] book/page
           │                                       (unchanged)
           └─► Lane B: literature lane ─► narrative + [L1][L2]         PMID/DOI
                                          │
                   QAResult ◄─────────────┘  (answer, citations, figures, literature)
                       └─► render: cli.py / streamlit_app.py / briefing_pdf (PDF)
```

## 3. Components

### New module `neuro_caseboard/literature.py`

| Unit | Responsibility | Source |
|------|----------------|--------|
| `PubMedClient` | httpx E-utilities: `esearch`/`esummary`/`efetch` + **structured abstracts** (Background/Methods/Results/Conclusions). API-key injection (`NCBI_API_KEY`, fallback `NCBI_API_KEY_2`), rate-limit (10/s with key), 429 retry. | port of caseprep `mcp_server._pubmed_*` + `_ncbi_get` |
| `LiteratureRecord` (dataclass) | Normalized hit: `pmid, title, journal, year, doi, url, abstract, sections, pub_types`. | parallels caseprep `EvidenceRecord` |
| `LiteratureRetriever` | question → PubMed query (+ recency/pub-type filters) → `list[LiteratureRecord]`. Injectable `search`/`summaries`/`abstracts` fns for tests. | port of caseprep `PubMedRetriever` |
| `synthesize_literature(question, records, client)` | grounded synth over abstracts → compressed narrative + `[L#]` citations; **refusal path** when nothing relevant. | parallels `neuro_core.synthesize` |
| `LiteratureCache` | on-disk TTL cache keyed by normalized query+filters. | new |

### New orchestrator `neuro_caseboard/qa.py`
- `QAResult` dataclass: `answer, citations, figures, literature` (literature =
  `LiteratureSection(narrative, records)` or `None`).
- `answer_question(question, config=None) -> QAResult`: runs Lane A
  (`neuro_core.query.query`) and Lane B concurrently; merges. **Lane B is strictly
  additive** — any failure yields `literature=None`, never blocks/alters Lane A.

### Modified
- `neuro_caseboard/cli.py`, `app/streamlit_app.py`: call `answer_question()` instead
  of `neuro_core.query.query()`; render the literature section.
- `neuro_caseboard/briefing_pdf.py`: `build_briefing_html` already duck-types fields
  via `_g(result, key)`; add a styled "Contemporary Literature" block reading
  `_g(result, "literature")`, with `[L#]` → DOI/PMID links rendered distinctly from
  textbook `[n]` citations.

## 4. Query construction & quality filters

- **Query (LLM rewrite, not the raw question):** `rewrite_pubmed_query` turns the NL
  question into a focused entity query (disease/anatomy/intervention) via the synth
  client, with `build_query_terms` as the deterministic fallback. *Rationale:* feeding
  the whole question to esearch ANDs every token — the real question "subdural hematoma
  resolution time course after MMA embolization" matched **total=1** vs **736** for the
  entity query. Two axes: primary + a `systematic_review` filter axis.
- **Recency:** bias to **last ~7 years** (`LITERATURE_RECENCY_YEARS=7`); do not
  hard-drop landmark older trials if they dominate relevance.
- **Ranking (relevance-bucketed rerank):** fetch **25** candidates (esearch
  `sort=relevance`); bucket by relevance (size 5), then order by publication-type tier +
  recency *within* a bucket — relevance gates selection, quality/recency reorder peers.
  Keep top **`LITERATURE_K`=8**, cite only those used. This replaced an earlier
  metadata-only sort that discarded esearch relevance and buried on-topic recent RCTs.

## 5. Grounding & citations
- **Separate namespace:** textbook `[1][2]`; literature `[L1][L2]`. Never collide;
  PDF styles them distinctly; each `[L#]` links to `https://doi.org/{doi}` (or
  PubMed PMID when no DOI).
- `synthesize_literature` inherits Lane A discipline: **every sentence grounded in a
  supplied abstract or omitted**; empty/irrelevant → section dropped (no
  hallucinated "recent literature").

## 6. Error handling, caching, config
- **Strictly additive:** any Lane B failure (network, rate-limit exhaustion, empty
  results, synth refusal) → omit section. Mirrors the visual-lane `try/except` in
  `neuro_core/query.py`.
- **Cache:** on-disk TTL cache keyed by normalized query+filters; default **14-day**
  TTL (`literature_cache_ttl_days=14`). Essential under always-on. Location under the
  config index/cache dir.
- **Config flags** live in the **caseboard layer** (read from env in
  `neuro_caseboard/qa.py`/`literature.py`), so `neuro_core` stays untouched. They
  follow the *same env-var style* as neuro_core's `visual_retrieval`/
  `caption_retrieval`: `LITERATURE_RETRIEVAL` (bool, default on),
  `LITERATURE_RECENCY_YEARS` (7), `LITERATURE_K` (8),
  `LITERATURE_CACHE_TTL_DAYS` (14). API keys from env (`NCBI_API_KEY`, fallback
  `NCBI_API_KEY_2`).

## 7. Surfaces
All three, since always-on means the section flows everywhere the answer renders:
**CLI** (`cli.py`), **Streamlit app** (`streamlit_app.py`), **Signal-styled PDF
export** (`briefing_pdf.py`).

## 8. Testing
Reuse caseprep's injection pattern — `LiteratureRetriever` and
`synthesize_literature` take injectable dependencies, so tests run with **fake
fixtures, no live network**:
- retrieval normalization (summaries+abstracts → `LiteratureRecord`),
- query/filter construction (recency + pub-type mapping),
- synthesis grounding + refusal,
- cache hit/miss + TTL expiry,
- orchestrator additivity (Lane B exception ⇒ `literature=None`, Lane A intact),
- `briefing_pdf` renders/omits the literature block correctly.
- One **opt-in live smoke test**, gated on `NCBI_API_KEY` presence.

## 9. Non-goals (YAGNI for v1)
- No PMC full-text ingestion into the local corpus (abstracts only).
- No multi-axis case planner (that's caseprep's structured-case path).
- No intent-gating or manual toggle (trigger is always-on by decision).
- No Scite/MCP runtime dependency.

## 10. Open ports list (from caseprep, to vendor into caseboard)
- `mcp_server.py`: `_client`, `_ncbi_get`, `_rate_limit`, `_pubmed_search`,
  `_pubmed_summaries`, `_pubmed_abstracts`, `_pubmed_structured_abstracts`,
  `EUTILS`, `_NCBI_API_KEY`/`_DELAY` logic.
- `retrievers/pubmed.py`: `PubMedRetriever` normalization shape.
- `retrieval_planning.py`: the `filter_type` → publication-type filter concept only
  (not the full 5-axis case planner).
