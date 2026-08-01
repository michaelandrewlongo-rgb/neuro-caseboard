# neuro-caseboard — fix plan

Companion to `OUTSIDE_REVIEW.md`. Every issue in the review, mapped to a concrete change, a code
site, a precondition, and a gate. Sequenced by the decisions taken 2026-07-08:

| Decision | Choice |
|---|---|
| Re-index | **Full re-index.** GPU preflight passes (RTX 5070 Ti, 11,944 MiB free, 0% util). |
| Phase 1 | **Retrieval recall.** Everything else sequenced behind it. |
| Literature scope | **Full currency stack.** |
| Validation | **Old A/B apparatus discarded.** Protocol redesigned from scratch by an independent methodologist (§6). |

---

## 0. Three corrections to the review

Investigation while planning turned up three things that change the shape of the work. Two make it
*easier* than the review implied; the third means the review overstated one of its own numbers.

### 0.1 The chapter fix already exists in code. It never reached the index.

Commit `5e7892b` ("P0 #2: fix Youmans chapter attribution", 2026-06-22) added `max_gap=120` to
`_chapter_for_page` and a front-matter filter to `_classify_toc`. Running today's ingest against
the Youmans TOC entries returns the honest answer:

```
  page   100 -> 1 - History
  page   700 -> 25 - Positioning for Spine Surgery     ← still wrong (gap 51 ≤ 120)
  page  1119 -> None                                    ← now honest
  page  2500 -> None
  page  5710 -> None                                    ← the review's smoking gun
```

The live index (`chunks.lance`, mtime 2026-06-25 — **three days after the fix**) still serves
`300 - Radiosurgery for Intracranial Vascular Malformations` at p.5710. **The code was fixed and
the index was never rebuilt.** This is the textbook silent propagation failure: the source changed,
the artifact didn't, nothing errored, and every answer since has shipped the old labels.

Consequence for the plan: a rebuild is not optional housekeeping. It is the mechanism by which any
ingest-side fix becomes real, and the rebuild must be guarded so this cannot recur (§3.5).

Note also that `max_gap` only converts *distant* wrong labels into `None`. Pages within 120 of a
stale bookmark stay wrong (p.700). Honest-unknown is an improvement over confidently-wrong, but it
still gives the reader nothing. Positive, correct labels require the in-text `CHAPTER N` header
extraction in Phase 3.

### 0.2 The full-text literature corpus is not cerebrovascular-only. It is 815,581 works, and it is switched off.

The review said the `[D#]` lane was a 70-chapter cerebrovascular corpus. It is far larger. On disk
at `/mnt/c/dev/NSGY_DB_lean/fulltext/` (22 GB), section-tagged full text through **March 2026**:

| subspecialty | works | passages | FTS sidecar built? | in `RELEVANT_DBS`? |
|---|---:|---:|:--:|:--:|
| cerebrovascular | 262,262 | 2,568,304 | yes | yes |
| tumor_skull_base | 183,441 | 1,957,777 | yes | yes |
| **spine** | **121,349** | **795,730** | **NO** | **NO** |
| **functional_epilepsy** | **71,985** | **791,601** | **NO** | **NO** |
| trauma_general | 49,016 | 391,830 | yes | yes |
| neurointerventional | 48,392 | 381,699 | yes | yes |
| **peripheral_nerve** | **33,619** | **654,209** | **NO** | **NO** |
| pediatrics | 24,562 | 354,027 | yes | yes |
| radiosurgery | 16,844 | 122,570 | yes | yes |
| neurocritical_care | 4,111 | 79,994 | yes | yes |
| **TOTAL** | **815,581** | **8,097,741** | 7 of 10 | 7 of 10 |

`neuro_caseboard/corpus.py:69` — `enabled=_flag(os.environ.get("CORPUS_RETRIEVAL", "false"))`.

The lane is BM25 over a contentless FTS5 sidecar, already section-aware, and already boosts the
sections that carry the numbers (`_SECTION_BOOST`: results 1.15, conclusion 1.15, methods 1.08,
introduction 0.75, title 0.6). It is additive and failure-safe by construction.

Three observations that matter:

- **Spine and functional_epilepsy have no sidecar and are excluded from `RELEVANT_DBS`** — and
  Functional was the weakest benchmark domain, Spine the second-strongest textbook domain but with
  zero contemporary coverage. 193,334 works of the most relevant literature are unreachable.
- The `works` table already carries **`study_design`** and **`evidence_tier`** columns. A named-trial
  table is a `SELECT`, not a data-collection project.
- 42 tagged guideline PDFs already sit at `/home/michael/guidelines_held/`, including
  *AHA-ASA Acute Ischemic Stroke Guideline 2026* and *AO Spine Acute SCI 2024*.

So Phase 2 is not "build a currency stack." It is **switch on, extend, and route** a currency stack
that is already built and paid for.

The trial table is likewise a query, not a project. Across the 10 DBs: **28,733 works tagged
`study_design = 'rct'`, of which 9,759 are 2020 or later.** Recent titles include 2026 RCTs on
collateral status modifying steroid effect in EVT, futile recanalisation in anterior LVO, and
arachnoid-membrane opening in adult moyamoya. (`evidence_tier` is populated but its values are
design labels — `case_report`, `observational`, `meta_analysis`, 14,794 nulls — not Roman tiers.
Use `study_design`, not `evidence_tier`.)

### 0.3 The review's second headline stat was wrong. The defect it pointed at is real; the measurement was not.

`OUTSIDE_REVIEW.md` claimed `verified_fraction: 0.027` meant "expert graders could resolve only 5 of
185 of the product's citations." **False, and now corrected in the review.**

`evidence_anchors` in `summarize_grades.py:70` are the *grader's own* external references — actual
rows look like `{"title": "Elias et al., MRgFUS thalamotomy…, NEJM 2016", "url":
"https://doi.org/10.1056/NEJMoa1600159", "verification_status": "verification_unavailable"}`. The
offline grader could not reach the internet to check its own DOI. The metric describes the grading
harness. It says nothing about whether a Youmans citation opens.

This cuts *against* the product, not for it: **nobody has ever measured whether this product's
citations resolve.** The hand-traced count in the review is the first measurement. §6.2 makes it a
deterministic CI assertion, and `verified_fraction` gets deleted rather than promoted.

A second, related discovery: **`corpus_fingerprint` and `prompt_fingerprint` are `None` on all 67
rows of every run record.** No run in this repo's history is reproducible, and every "uncontrolled
run-to-run noise" claim is therefore unfalsifiable — the noise may have been un-recorded config
drift. Fixing this is the first thing that should happen (§6.7).

---

## 1. Preconditions

| # | Precondition | Status | Action |
|---|---|---|---|
| P1 | Source textbook PDFs | **PASS** — all 19 PDFs (2.7 GB) at `/home/michael/textbook_pdfs` | Set `CORPUS_DIR`. The `config.py` default (`/mnt/d/textbook_pdfs`) is **stale and points at an empty mount** — fix the default, it is a latent build-failure |
| P2 | GPU free ≥ 10 GB | PASS — 11,944 MiB free, 0% util | `~/.claude/scripts/gpu_preflight.sh 10000` immediately before the rebuild |
| P3 | Full-text DBs readable | PASS — 22 GB at `/mnt/c/dev/NSGY_DB_lean/fulltext/` | — |
| P4 | Disk for a parallel index | ~2 GB needed; current index is 1.8 GB | Build to `index-next/`, promote on green. Never rebuild in place. |

**Nothing is blocking.** The rebuild can start as soon as the fixes land.

**Rebuild cost is not the problem.** Embedding 42,228 chunks with `bge-large-en-v1.5` on this GPU
is roughly 3–5 minutes; the wall clock (~45–90 min) is PDF parsing and rendering 10,367 figure PNGs,
both I/O-bound. A full rebuild is a lunch break, not a weekend. Nothing in this plan should be
compromised to avoid one.

---

## 2. Phase 1 — Retrieval recall *(the chosen first phase)*

Target: `retrieval_omission`, 175 of 406 ledger defects — the largest single bucket.

Five changes. Two are ingest-side and ride the rebuild; three are query-side and ship independently.

### 1.1 Strip bibliography text — at the LINE level, during ingest

**Not** chunk-level deletion, and **not** page-level deletion. I tested both and they are wrong.

Measured: 6,420 chunks (15.2%) are reference-dense. But a citation-signal density detector
(`Author AB,` / `1993;3` / `et al` / `45(3):123` / `doi:` per 100 words) at a threshold of 8 flags
7,669 chunks (18.2%) — and sampling the flagged set turns up real anatomy prose:

```
[9] Youmans p4239: 'the setting of hypoperfusion. Venous Drainage The territory
                    supplied by the PSAs is drained by the midline posterior spinal vein…'
```

The cause: **chunks straddle the prose→references boundary.** 1,530 chunks contain a `REFERENCES`
heading; in **495** of them the heading appears more than 200 characters in, i.e. prose and
bibliography share one chunk. Page-level deletion fails the same way — `NeuroICU p738` carries a
chapter title, prose, and `REFERENCES` on one page.

Correct granularity: **strip citation lines from `PageRecord.text` in `extract_pages`, before
`chunk_page()` ever sees them.** At that point PyMuPDF's line structure still exists; after
`chunk_page` does `record.text.split()` it is gone forever.

- Site: `neuro_core/ingest.py::extract_pages`, right after `text = page.get_text().strip()`.
- Rule: from the first line matching `^\s*(REFERENCES|BIBLIOGRAPHY)\s*$` to end-of-page, drop
  lines; independently drop any line whose citation-signal density exceeds threshold and which
  contains no clinical content token. Keep a per-book counter of lines and characters removed.
- Guard: assert removed-character fraction per book is within 5–30%. Outside that band, fail the
  build — a book whose parser broke will remove 0% or 90%, and both must stop the pipeline.
- Expected: ~15% of the candidate pool returned to clinical prose, and — critically — the chunks
  that hijack trial-name and eponym queries are gone. Reference lines are *lexically dense in
  exactly the tokens a currency-sensitive question contains.*

### 1.2 Index figure captions into the searchable text column

`Chunk.caption` exists (`chunk.py:13`) and is stored (`index.py:78`) but `index.py:89` only does
`create_fts_index("text", ...)`. The caption naming the anatomy is invisible to **both** the dense
lane and BM25. The repo already knows this bites: *"MCA is the universal ceiling: NO plate in the
whole corpus has a caption that names the M1/MCA bifurcation"* — and then 6,464 plates were
re-captioned with Gemini, producing text that retrieval still cannot see.

- Site: `neuro_core/chunk.py::chunk_page` — append the caption to the chunk's indexed text (keep
  `Chunk.caption` separate for display), or `index.py` — FTS-index `caption` as a second column and
  fuse. Prefer the former: one column, one RRF path, no new fusion weight to tune.
- Cheap, ingest-side, rides the same rebuild.

### 1.3 Union the disambiguation rewrite's hits with the original's

`neuro_core/query.py:250`:

```python
return _Resolved(resolved, self._retrieve(resolved), analysis.chosen)
```

`top` — the original query's 12 reranked hits, already computed and paid for at line 240 — is
discarded. Replace with an RRF union of `top` and `self._retrieve(resolved)`, then re-slice to
`rerank_k`. Free recall: the embeddings and the cross-encoder pass already ran.

Query-side. Ships without a rebuild.

### 1.4 Wire the heading-aware chunker

`neuro_core/chunk_strategies.py` implements five strategies (`page`, `paragraph`, `sentence`,
`heading`, `chapter`) including heading-atom packing and cross-page chapter packing. Its docstring
says it exists "for the ingestion ablation benchmark." It is imported only by
`scripts/chunking_benchmark.py`. The production chunker is a 600-word sliding window that is
structure-blind and **never crosses a page boundary** (`chunk.py:44-47`), so any concept spanning a
page break exists in no chunk.

Before wiring it, fix the id collision: `pack()` emits `id=f"strat::{meta.page}::{i}"` — a literal
`strat` prefix, non-unique across books.

Gate this one behind the benchmark that already exists (`eval/chunking-benchmark/`), re-run under
the new protocol (§5). It is the highest-variance change in Phase 1 and the only one I would be
willing to abandon.

### 1.5 Re-tune `RERANK_K`, and settle the abandoned sweeps

`RERANK_K = 12` — only 12 chunks ever reach the model. A prior test measured 12→16 at +0.95 mean,
14–6 head-to-head, ~23% slower, and correctly declined to ship on one result. It was then dropped
rather than re-run. Separately, six knob-sweep arms (`rerank-none`, `rerank-qwen3`, `rerank_k-20`,
`retrieve_k-80`, `embed-qwen3`) were generated, blinded, and **never graded into numbers**.

Under the new protocol: re-run the sweep on the post-rebuild index, extract a decision, and delete
the arms. Sunk compute with no decision attached is worse than no compute.

### 1.6 Stop swallowing retrieval failures

Six paths do `except Exception: return []` (`retrieve.py:65,74,158,172,177`; `query.py:125,136`). A
dead lane is indistinguishable from "no results." **This has already happened once**: `retrieve.py`
imported a nonexistent `engine.query.search`, the exception was swallowed, and every citation
rendered `⚠ to verify` until commit `ace4d7b`. Replace with a raise, or a loud per-lane counter
surfaced in `/api/health`.

### 1.7 Fix the Build-path retriever, or delete it

`neuro_caseboard/retrieve.py` is a second, much weaker retriever used by the board/briefing path:
BM25 only, no dense vectors, no reranker, query stripped to ≤8 terms, and every token shorter than
3 characters deleted (`retrieve.py:52`) — so `CT`, `AP`, `3D`, `T1`, `T2` are silently removed from
every board query. `_SanitizingCorpus` then ANDs ≤6 terms in FTS5, which its own comment concedes
"over-constrains many card queries."

Point it at the same `Engine` the Ask path uses. Two retrievers with different recall on the same
corpus is a bug, not an architecture.

---

## 3. Phase 2 — Full currency stack

Target: `outdated_evidence` (70 defects) and the C1 cluster the repo itself scores at
**245 of 406 defects (60%), priority 200, DEFERRED**. This is the largest quality lever in the
product and its remedy is already on disk (§0.2).

### 2.1 Turn the `[D#]` lane on, with routing

Flip `CORPUS_RETRIEVAL` to `true` by default. Do **not** flip it naively — the one prior attempt at
adding contemporary sources produced a measured retrieval-crowding regression (a stroke guideline
pulled a TBI question off-topic). Route instead:

- Map the question to a subspecialty (the `_offdomain` machinery in `query.py:20-25` is a
  two-subdomain keyword stub; replace it with a real classifier over the 10 DB names — this is a
  cheap flash-tier call, and `ANALYZE_MODEL` already exists for exactly this kind of constrained
  classification).
- Query only the matched DBs. `CORPUS_DBS` already accepts a comma-separated override, and
  `load_corpus_config` already falls back to `RELEVANT_DBS` — the seam exists.
- Keep `max_per_work=1` so one prolific paper cannot monopolise the lane.

### 2.2 Build the three missing sidecars and un-exclude their domains

`spine` (121,349 works), `functional_epilepsy` (71,985), `peripheral_nerve` (33,619) have no FTS
sidecar and are absent from `RELEVANT_DBS`. That is 193,334 works — 24% of the corpus — and it
covers the *weakest* benchmark domain (Functional, mean 74.70).

```bash
python -m scripts.build_corpus_fts --db spine --db functional_epilepsy --db peripheral_nerve
```

Then add all three to `RELEVANT_DBS`. Once §2.1's routing exists, adding domains cannot crowd
out-of-domain questions, because out-of-domain DBs are never queried.

### 2.3 Replace PubMed abstracts with full-text Results sections

The `[L#]` lane retrieves **abstracts** (`literature/pubmed_client.py:171`). Abstracts contain no
effect sizes, no confidence intervals, no exclusion criteria, no subgroups — and they are the most
spin-laden text in a paper. The `[D#]` lane already section-tags and boosts `results`/`conclusion`.

Change: resolve each PubMed hit's PMID against the local `works`/`text_passages` tables first, and
serve its Results/Conclusion passages. Fall back to the abstract only when the PMID is absent from
the corpus. This costs one join and deletes an entire class of defect.

### 2.4 Guidelines lane, gated behind the routing from §2.1

42 tagged PDFs at `/home/michael/guidelines_held/`, including AHA-ASA Acute Ischemic Stroke 2026,
AHA-ASA aSAH 2023, AHA-ASA ICH 2022, AO Spine Acute SCI 2024.

A prior attempt shipped these into the general corpus and produced a crowding regression. The
diagnosis then was "gate guidelines behind query-type/domain routing before promotion." §2.1 builds
exactly that routing. So: index guidelines as their own lane with its own citation namespace, and
surface them **only** on in-domain management questions. A guideline is the single highest-authority
source a surgeon can quote at M&M; it should never be a paragraph competing with a textbook chunk
for a slot.

*(The earlier held-out verdict on guidelines is explicitly not binding here — its A/B apparatus is
retired, and the crowding it found is what §2.1 and §1.1 exist to remove.)*

### 2.5 Named-trial table

`works` already has `study_design` and `evidence_tier`. The trial table is a query plus an acronym
extractor, not a corpus project. Retrieve by acronym on exact match, ahead of BM25, so
"ARUBA", "DAWN", "SELECT2", "ESCAPE-MeVO", "ENRICH", "SANTE", "RESCUEicp", "JLGK0901" resolve
deterministically rather than probabilistically.

Columns: `acronym · full name · design · n · population · primary endpoint · result (effect size,
CI) · key caveat · year · PMID`. The failure ledger names the exact misses; every one of them is an
RCT in a DB you already own.

### 2.6 Date-stamp every claim inline

If a statement rests on a 2022 textbook page, say so where the claim is made — not in a footer. A
surgeon can price staleness, but only if it is visible at the point of decision. This is a renderer
change (`render_md.py`) plus carrying `pub_year` through `EvidenceRef`.

---

## 4. Phase 3 — Citation verifiability

Target: **Verifiability Rate**, a metric that does not yet exist (§0.3). This is the review's
headline defect and, per §0.1, partly a rebuild away. **Runs second, ahead of Phase 2** (§6.5), but
note that **3.1 and 3.2 are ingest-side and must ride the same rebuild as Phase 1** or you pay for a
second full PDF parse.

> **Scope note.** Phase 1 was chosen as the first phase. Phases 1 and 3 nonetheless share one ingest
> pass. Landing 3.1/3.2 in the Phase-1 rebuild is a scope expansion — a deliberate one, and cheap,
> because the alternative is re-parsing 19 PDFs and re-rendering 10,367 PNGs a second time. My
> recommendation is to fold them in. If you'd rather keep the phases clean, say so and I'll rebuild
> twice.

### 3.1 `printed_page` — the folio

`Chunk` has no folio field, so citations carry the PDF page. Youmans is a four-volume set whose
folios restart per volume; the stored page runs 2–6329, and the measured `pdf_page − folio` offset
is not constant (median 1455, scattered across 1028 / 1142 / 1588 / 1672 / 1728 at volume breaks).
`p. 5710` exists in no physical book.

The consumer already exists and is waiting: `vendor/caseprep/caseprep/retrievers/textbook.py:41`
reads `hit.get("printed_page")` and renders `f"{book}, p.{folio}"`. It always misses, because
`neuro_core` never sets it.

- Add `printed_page: Optional[int]` to `PageRecord` and `Chunk`; add the column in `index.py`.
- Extract at ingest from the running header/footer — take PyMuPDF's top and bottom text blocks and
  find the bare integer. A naive leading-token regex already recovers 38% of pages; a proper
  header/footer block parse gets nearly all of them.
- Guard: assert monotonicity of `printed_page` within a volume, and that ≥90% of a book's content
  pages resolve. A book below that fails the build.
- Cite `printed_page`; fall back to `p. [pdf N]` clearly marked when absent. Never silently print a
  PDF page as if it were a book page.

### 3.2 Real chapter labels from in-text headers

Today: 1,663 of 1,691 verifiable Youmans chunks (**98.3%**) carry the wrong chapter. `max_gap`
(§0.1) converts the distant ones to `None` on rebuild, which is honest but empty.

Extract positively instead: the running header carries the chapter, and body pages carry
`CHAPTER \d+`. Prefer in-text evidence over the TOC bookmark; fall back to the bookmark only when
within `max_gap`; fall back to `None` otherwise. **Wrong is strictly worse than absent** — a wrong
chapter is a citation the reader disproves, and a disproved citation discredits every other citation
on the page.

Guard: on the rebuilt index, re-run the check from the review — for every chunk with an in-text
`CHAPTER N`, the label must agree. Target ≥95% agreement, versus 1.7% today. This assertion is free,
deterministic, and belongs in CI.

### 3.3 Make the model quote its support

`Citation.text` is the **entire ~600-word chunk** (`synthesize.py:89-100`). Nothing localizes the
supporting sentence; nothing even checks that a `[n]` the model emitted exists. A citation pointing
at 600 words is a reading assignment.

Change the contract: for each `[n]`, the model returns the supporting sentence **verbatim**. Then
string-match it back into the cited chunk (normalized whitespace, ≥90% character match against the
best-matching window). If it isn't there, the citation is rejected — not flagged.

This one change is simultaneously:
- a **fabrication detector** that needs no NLI model and cannot be tuned into self-deception,
- the **span localizer** the entailment gate has been missing (§4.2), and
- **the thing the reader actually wants to see.**

#### 3.3.1 The quote is a verification artifact. It never enters the prose.

The obvious failure of a quote contract is that answers become mechanical — a chain of stitched
quotations that verifies perfectly and teaches nothing. A surgeon cannot learn from, or remember,
prose written to satisfy a string matcher. **That failure is a design choice, not a consequence, and
this plan rejects it.**

Two channels, one generation:

```
prose channel     the answer, written exactly as it is written today — narrative,
                  synthetic, hedged where the evidence hedges. Carries [n] markers
                  and nothing else. No quotation marks, no block quotes, no
                  "according to Youmans, …".

evidence sidecar  structured output, never rendered inline:
                  {claim_id, marker, verbatim_quote, chunk_id, printed_page}
```

`D15` string-matches the **sidecar**, never the prose. The reader sees an ordinary paragraph; hovering
or clicking `[3]` reveals the quoted sentence beside the rendered page image (§3.4). Verification is
one click away and zero words away.

Assert the separation deterministically, free: **no sidecar quote may appear verbatim in the prose**
(≥40-character overlap = fail), and prose length must stay within ±15% of the pre-contract arm. If
the model starts smuggling quotes into the answer to make matching easier, the build fails.

#### 3.3.2 Two claim classes, two obligations — so explanation survives

Requiring a quote for *every* sentence is what would flatten the prose: it permits only
chunk-shaped assertions and forbids the connective reasoning that makes an answer memorable. So
split the obligation by what the sentence is doing.

| Class | What it is | Obligation |
|---|---|---|
| **Evidential** | any sentence carrying a number, a threshold, a comparator, a recommendation, an attribution, or a trial result | citation **+** verbatim quote in the sidecar. `D15` applies. |
| **Derived** | a synthesis across sources ("these three series converge on…") | cites ≥2 markers, **each** with its own quote. The *inputs* are quoted; the *inference* is the model's, and is allowed to be. |
| **Connective** | mechanism, framing, why-this-matters, transitions — the teaching tissue | **no quote required.** Subject instead to the entity-bleed check. |

The bleed check already exists and is the right instrument: `entailment.py::unsupported_entities`
flags medical entities asserted in a sentence that appear in **none** of the spans cited anywhere in
that section. It costs nothing, needs no model, and it is precisely what catches the fabrication class
this repo has already documented — *"anterior choroidal artery mislocated to the MCA bifurcation."*
Connective prose stays free to explain; it is not free to introduce anatomy that no source mentions.

This also closes `D13`'s hole properly. Today uncited sentences auto-pass, so the safest strategy is
to cite nothing. Under this contract an uncited sentence is not exempt — it is bleed-checked. Nothing
auto-passes.

#### 3.3.3 Memorability is a separate lever, and it is §4.1

Nothing in the quote contract makes an answer worth remembering. What does is the decision furniture
in §4.1 — the threshold with its units, the comparator, who is excluded, the effect size, what would
change the answer. That is the structure a surgeon actually retains, because it is the structure of the
decision he is about to make. **Verifiability and memorability are orthogonal; buy them separately.**
If Phase 3 lands and answers feel flatter, the remedy is to pull §4.1 forward, not to loosen `D15`.

### 3.4 Link each citation to its rendered page image

10,367 figure PNGs at 160 DPI already exist in `ASSETS_DIR`. Every cited chunk knows its book and
page. Render (or reuse) the page image and link it. "Show me the page" is one hop from "trust me."

### 3.5 The rebuild guard — so §0.1 cannot happen again

Build to `index-next/`, then assert **before promotion**:

```
1. chunk count within ±20% of the previous index (catches a parser that silently dropped a book)
2. book count == 19, and every book's chunk_count > 0
3. bibliography strip removed 5–30% of characters per book        (§1.1)
4. ≥90% of content pages resolved a printed_page                  (§3.1)
5. ≥95% in-text CHAPTER agreement                                 (§3.2)
6. zero chunks whose chapter is a filename, a hash, or front matter
7. index fingerprint (embed model + chunker + config hash) written to the `meta` table
8. a golden query returns a citation whose printed_page and chapter both resolve
```

Then, at query time, refuse to serve an index whose fingerprint doesn't match the running config.
The 2026-06-25 index served stale labels for two weeks under a fixed codebase because nothing
compared the two. Make that comparison mechanical.

---

## 5. Phase 4 — Answer shape, honesty, and the dead figure lane

Sequenced last, but 4.2 is cheap and worth pulling forward.

### 4.1 Decision furniture

Cluster C2 (open, 102 defects) is almost entirely missing decision furniture:
`missing_comparator` 34 · `missing_decision_threshold` 33 · `missing_risk_or_tradeoff` 24 ·
`missing_patient_selection` 11.

The system prompt (`woven_synth.py:16`) asks for free prose and imposes no structure. Add a
checklist the answer must address **or explicitly declare unestablished**: the threshold with its
units · the comparator · who is excluded · the effect size with its interval · what would change the
answer. Not a rigid template — a set of questions the answer is not allowed to silently skip.

"Not established in the sources" is a correct, useful answer. Silence is not.

### 4.2 Fix the ⚠ badge or remove it

Out-of-sample flag precision is **0.24**: three of four warnings are false. That trains the reader
to ignore warnings — the exact reflex you least want in a clinical tool. Two structural holes:

- Uncited sentences auto-pass (`answer_verify.py:83-85`), so an answer with **zero citations scores
  `groundedness = 1.0`**. The metric rewards the failure mode it exists to catch.
- The premise is the concatenation of full 600-word chunks. The repo's own measurement:
  whole-premise precision → groundedness 0.07; best-**sentence** premise → 0.80.

§3.3 makes both moot: the model hands you the sentence, so the premise is the sentence. Once that
lands, re-measure precision. **If it cannot clear ~0.6, take the badge off the screen.** A warning
nobody believes is worse than no warning.

Also: `entailment.py:6-7` promises *"the gate may only ever REMOVE a weak citation."* Nothing in the
Ask path removes anything. Either implement the docstring or delete it.

### 4.3 Un-skip over-absolute language

38 defects, deliberately deferred to keep a before/after attributable. That was right for one
experiment and wrong as a resting place. "Should" and "always" in a domain this hedged is the
fastest way to lose a surgeon.

### 4.4 Resolve the figure lane

`glm-5.2` is **text-only** on OpenRouter (`input_modalities=['text']`). Page images 404'd; the fix
was to retry text-only. But the woven system prompt still tells the model: *"Some textbook sources
include an attached page image… you may describe what the figure shows and must still cite that
source number."*

The deployed model is instructed to describe images it never receives, and to cite them. That is an
invitation to hallucinate. Either route figure-bearing questions to a vision-capable model, or strip
the image instructions from the prompt when the synth client reports `input_modalities` without
`image`. Detect it at startup from the model's own capability report — never hardcode.

---

## 6. Validation

The old apparatus is retired by decision. This protocol was designed from scratch by an independent
methodologist who was given the facts and explicitly told not to anchor on the existing harness. I
have adopted it essentially intact; the reasoning survived my checks and it caught an error in my
own review (§0.3).

### 6.1 The gating metric is the Trust Rate

> **Trust Rate** = the fraction of benchmark questions where the surgeon would act on the answer
> without opening another source **AND** every load-bearing claim is machine-verifiable — the
> model's verbatim quote string-matches into the chunk it cites, and that citation resolves to a
> printed folio he can physically open.

A conjunction, because the product's promise is a conjunction. An answer he would act on but cannot
check is a liability. An answer he can check but would not act on is a search engine.

It decomposes into a free factor and an expensive one:

- **Verifiability Rate (VR)** — deterministic, zero LLM, zero human, computed on all 67.
- **Actionability Rate (AR)** — human, sampled.
- **VR is a hard ceiling on Trust Rate.** Trust Rate ≤ VR, always.

That relation is the whole argument. **Today the ceiling is near zero, and no amount of mean-grade
improvement can lift it.** Mean grade climbed 77.74 → 79.36 → 83.87 while the ceiling did not move.
That is the proof that the metric was wrong: it moved while the product's promise did not.

**Hard veto, independent of everything:** any answer flagged unsafe blocks merge. `unsafe = 0` is a
precondition, not a metric.

**Mean judge grade survives only as a logged drift monitor,** annotated in perpetuity with the
measured noise floor (§6.7). It never gates a merge again.

### 6.2 Deterministic assertions — free, offline, no LLM, no human

Land as pytest under `evaluation/assertions/`. CI here is pytest-only, so these become required
gates for free. Abridged; the full table is in the methodologist's protocol.

**Corpus/index** — D1 bibliography-chunk fraction **< 1.0%** (today 15.2%) · D2 chapter label is a
real TOC member, not a filename or hash, **≥ 95%** (today 1.7% on Youmans) · D3 folio exists, is
monotone within a book, and `printed_page − page` is constant within a chapter run, **≥ 98%** (today
the field does not exist) · D4 the folio string appears in the top/bottom 8% band of the page text,
**≥ 95%** · D5 a figure caption's exact text self-retrieves its chunk at rank 1, **100%** · D6 chunk
boundary sanity · D7 **every run row carries a non-null `corpus_fingerprint` and `prompt_fingerprint`
or the runner refuses to start** · D8 near-duplicate chunks < 0.5%.

**Retrieval** — D9 self-retrieval of 500 random chunks into top-40, **≥ 98%** · D10 known-item recall
on a hand-built needle set · D11 union-not-replace is an exact set assertion, **100%** · D18
retrieval is byte-identical across two runs at temp 0 (*retrieval nondeterminism is a bug, not
noise*).

**Answer/citation** — D12 **zero** citations point at a bibliography chunk (hard fail) · D13
`groundedness is None` when there are no cited claims, **never 1.0** · D14 every `[n]` resolves to a
real chunk **and** a real page image on disk · **D15 the model's verbatim quote is found in the cited
chunk, `partial_ratio ≥ 95`, on ≥ 98% of *evidential* claims** (§3.3.2) · D16 named-trial coverage ·
D17 latency.

**Prose non-inferiority** (§3.3.1, §6.5) — D19 no sidecar quote appears verbatim in the prose · D20
prose length within ±15% of the pre-contract arm · D21 sentence-length distribution unchanged (KS,
α = 0.05) · D22 inline quotation-mark count does not rise. *These exist because a quote contract that
is allowed to leak into the answer text buys verifiability by destroying readability.*

**D15 is load-bearing.** A quote that string-matches back into the chunk it cites has *precision 1.0
against fabricated citation, by construction.* It is deterministic, free, and strictly better than an
entailment gate running at 0.24 out-of-sample flag precision. It does **not** catch a true statement
supported by a wrong chunk — that is what canary C3 is for (§6.6). It applies to *evidential* claims
only; connective prose is held to the entity-bleed check instead (§3.3.2), which is what keeps the
answer teachable rather than stitched.

**D13 is a live bug shipping today**: an answer with zero citations scores perfect groundedness. The
metric currently tells the model that the safest thing to do is cite nothing.

### 6.3 The surgeon: at most 105 minutes per gate

Only he can adjudicate two questions: *is this the current standard of care*, and *would acting on
this harm someone*. Everything else is bought cheaper elsewhere.

**Instrument A — paired forced-choice (90 min, 30 items).** Two answers side by side, order and arm
randomized per item. He clicks one of five (`A strongly / A slightly / tie / B slightly / B
strongly`), then picks — required — the single worst defect in the answer he did *not* prefer, from
the ledger categories — now ten, `degraded_readability` having been added in §6.5. **Not a 0–100
score.** That scale is where his time evaporates, where the noise lives, and where fluency gets
rewarded over correctness.

Four countermeasures against the blinding leakage the repo admits to (*"a sufficiently diligent
grader keeps DEDUCING which set is the fix"*):

1. **Style normalization.** A *third* model — neither the author nor either judge — rewrites both
   answers into an identical template: same headers, same sentence-count band, same hedging register,
   citations replaced by opaque tokens. Verify with a D15-style quote-match that no claim was added
   or dropped; any mismatch voids the item.
2. **Sham arms.** **6 of the 30 items are A/A pairs** — the same arm, sampled twice. His preference
   split on identical arms *is his noise floor*. If he systematically prefers one side of an identical
   pair, blinding is broken — and that finding is worth more than the preference number it voids.
3. **Deferred unblinding.** The key is sha256'd and committed *before* he starts.
4. **He is never told what changed.** The request says "30 pairs, 90 minutes." Nothing else.

**Instrument B — citation-opening audit (15 min, 20 items, Phase 3 only).** Not a preference task, so
no blinding needed; it is a fact check. He sees the claim, the model's quoted supporting sentence,
and the rendered page image of the cited folio. One click of three: *quote is on this page and
supports the claim* / *on this page, does not support it* / *not on this page*.

This measures the exact thing nobody has ever measured. **If D15 says 0.95 and he says 12/20, then
D15 is measuring the wrong thing — and that discrepancy is the single most valuable number this whole
program can produce.**

### 6.4 LLM judges, without the traps. Five controls, all mandatory.

1. **Three roles, three labs, no overlap.** The author is `glm-5.2`; the two judges come from two
   *different* labs, neither of them the author's. The answer judge currently shares a provider with
   the author. `judge_verifier.py` already does this correctly for the verifier panel — extend it.
2. **Split the 67 and freeze it.** `dev-27` for all tuning, prompt work, and knob sweeps. `gate-40`
   touched **exactly once per phase per arm**, logged to a monotonic counter. A second gate run in one
   phase retires the set. This is the structural fix for the repo's own retraction ("an artifact of
   tuning on the 40-claim in-sample set").
3. **The judge is graded every run on controls it doesn't know about.** Twelve injected items: 4 with
   a fabricated citation, 4 with a swapped comparator, 4 clean. A judge that misses ≥2 fabrications or
   fails ≥2 clean answers is **rejected and its verdicts for that run are void.** Twelve extra calls
   buys you a judge that cannot quietly fool itself.
4. **Concordance is the licence to extrapolate.** Compute κ(judge, surgeon) on the 30 items he graded.
   κ ≥ 0.5 → judge verdicts on the remaining questions count **at half weight**. κ < 0.5 → the judge
   counts for nothing that phase. This is the honest way to buy leverage on 90 minutes of attending
   time, and the judge must re-earn it every phase.
5. **Pairwise, and control the two known confounds.** Same instrument as the human, which is what
   makes κ computable. Every pair judged twice with order swapped; disagreement scores as a tie.
   Regress preference on length delta — **if length explains > 30% of preference variance the
   comparison is void** and both arms are regenerated under a shared token budget. Inter-judge κ ≥ 0.6
   between labs or the judge signal is discarded. Additionally run the author's own provider as a
   judge and **log its self-preference coefficient. Report it; never gate on it.**

### 6.5 Per-phase gates — pre-registered, or void

Write `evaluation/gates/phase-N.preregistration.json` — primary metric, threshold, n, split hash,
analysis method, stopping rule — and commit it **before generating a single answer**. Any post-hoc
metric change voids the phase.

**Phase order is 1 → 3 → 2**, not 1 → 2 → 3. Phase 3 is nearly free, moves the metric with the most
headroom, and *is the precondition for Phase 2 being gradeable at all*: when the surgeon disputes a
currency claim, he must be able to open the citation to settle it. Phase 2 is the most expensive
change and carries the highest regression risk. Do the cheap unlocking change first. (Phase 1 stays
first, as chosen.)

**Phase 1 — retrieval recall. Zero human, zero judge, entirely free.** It is a retrieval change;
grade it on retrieval, not on prose.
- Primary: needle-set recall@rerank_k, pre-registered **≥ +8 pts absolute**. Reject below **+5**.
- Co-primary, both hard: D1 < 1.0%, D12 = 0.
- Guardrails: D6, D9 ≥ 98%, D11 = 100%, D17 p95 ≤ 90s.
- **Ablate; never bundle.** Five sub-changes, five separate indexes, one needle set. **Any sub-change
  worth < +1.0 pt with no other assertion benefit is dropped, not shipped.**
- `RERANK_K` is a retrieval knob and gets tuned on the needle set — never on the 67, never on a 20-Q
  cheap-proxy subset. Sweep k ∈ {8,12,16,20,24}; **pre-commit the selection rule** (smallest k where
  marginal gain < +0.5 pt per +4 k) so the choice is not post-hoc.

**Phase 3 — citation verifiability. Free + 27 human minutes.**
- Primary: **Verifiability Rate** = D15 ∧ D14 ∧ D3. Pre-registered **≥ 0.95**.
- Co-primary (human): Instrument B, **≥ 18/20**.
- Co-primary: D2 ≥ 0.95, D3 ≥ 0.98.
- **Guardrail — prose non-inferiority. This is the gate that protects against a mechanical answer,
  and it is the reason Phase 3 is allowed to touch the prose contract at all.**
  - *Deterministic (free):* **D19** no sidecar quote appears verbatim in the prose (≥40-char overlap
    = hard fail) · **D20** prose length within ±15% of the pre-contract arm · **D21** sentence-length
    distribution not significantly different from the pre-contract arm (two-sample KS, α = 0.05) ·
    **D22** inline quotation-mark count does not rise.
  - *Human — Instrument C, 10 paired items, ~12 min.* Pre-contract vs post-contract answers to the
    same questions, blinded, order randomized, style-normalization **disabled** (the prose *is* the
    treatment here, so normalizing it would erase the effect being tested). Forced choice, plus a
    required tag when he disprefers an arm — the ledger's nine categories **plus a tenth,
    `degraded_readability`, added for exactly this purpose.**
  - **Reject Phase 3 if his win rate for the pre-contract arm has a lower 90% bound exceeding the
    upper 90% bound of his A/A sham floor** — i.e. if he can reliably tell that the old prose reads
    better. Verifiability is not worth an answer he won't read.
- Reject also if VR < 0.90, or the human audit < 16/20, or **any claim ships without a quote**. A
  missing quote must be an explicit refusal, never a silent downgrade.
- **On success, retire the entailment gate** as both a merge gate and a user-facing badge. Advisory
  annotation in the run record only. *(The bleed check survives — it is not the entailment gate; it is
  a free, deterministic, model-free check and it becomes the obligation on connective prose, §3.3.2.)*

Sentinel-21 (§6.6, C2) is extended for this phase: diff **prose**, not only claims. A change that
preserves every claim while destroying the writing passes a claim-level diff and fails the product.

**Phase 2 — currency. The expensive one, gated last.**
- Primary: named-trial coverage on the 25-question trial table, deterministic string match,
  pre-registered **≥ 0.80**. Baseline is near zero for the 2022–2025 trials — which *is* the 70
  `outdated_evidence` defects.
- Co-primary (judge): `outdated_evidence` defect count on `gate-40`, one run, cross-lab panel,
  **≥ 60% reduction**. Valid only if the panel passed its 12 control items and κ ≥ 0.6.
- Co-primary (human): Instrument A, 30 pairs. This is the phase where his judgment is genuinely
  irreplaceable — a judge model trained before a trial cannot arbitrate whether that trial changed
  the standard of care.
- **Guardrails, reject on violation:** `retrieval_omission` must not rise > 10% (the new lanes must
  not crowd out textbook context — the documented crowding risk, and the reason §2.1 routing exists);
  D17 p95 ≤ 120s; D12 still 0; entailment flag rate does not double.
- Reject if trial coverage < 0.65, or `retrieval_omission` up > 10%, or the surgeon's win rate for
  the new arm has a lower 90% bound not exceeding the upper 90% bound of **his own A/A sham floor**.

> **A note the ledger cannot tell you.** Phases 1 and 2 address ~60% of the 406 defects. **Phase 3
> addresses none of them** — and that is not a mark against Phase 3. An unopenable citation was never
> *scored* as a defect, because the grader could not open it either. The ledger is structurally blind
> to exactly the failure Phase 3 fixes. That is why VR is a gate and not a ledger category.

### 6.6 Canaries — the regressions the metrics miss

- **C1 — the A/A sham arm** (§6.3). The only instrument that can catch the deduction problem the repo
  admits to.
- **C2 — Sentinel-21.** Freeze the 15 highest-scoring baseline questions plus the 6 D-grades. Every
  phase, diff at the claim level against the frozen baseline. Any claim present before and absent
  after goes on a "dropped claims" list — 10 lines, 2 minutes of his time. This catches the canonical
  RAG regression the mean grade structurally hides: **a change that raises the average by rescuing
  weak answers while quietly gutting the strong ones.** Open-CV is the strongest domain (83.6) and is
  precisely what a currency lane will crowd.
- **C3 — poisoned-corpus canary.** Insert 12 synthetic chunks into a **shadow** index (never
  production) carrying plausible false claims with real-looking attribution — e.g. *"ENRICH
  demonstrated no benefit of minimally invasive evacuation."* Two findings, both required in writing:
  the poisoned chunk **passes D15**, because the quote really is in the chunk — *D15 cannot detect a
  true quote from a false source, and this must be documented, not discovered later*; and the
  poisoned-chunk citation rate must stay ≤ 1/67. A retrieval change that starts preferentially
  surfacing fluent, confident, wrong text is a real regression no answer-quality metric will show.
- **C4 — the unarmed canary.** `corpus_fingerprint` and `prompt_fingerprint` are `None` in every run
  record in this repo. Until the runner refuses to start without them, nobody can rule out that some
  of the "uncontrolled run-to-run noise" was un-recorded config drift — **including the +1.62 and the
  +6.13.**

### 6.7 Statistical discipline

**Measure the noise floor first. Before Phase 1. Before anything.**

Run the same config twice — different sampling seeds, identical everything else — end to end, and
grade both with the full apparatus. The observed |Δ| between two identical configs *is* the noise
floor. Publish it. Cost: ~2.2 h wall clock, zero human time.

The methodologist's prediction, recorded here in advance so it can be scored: **the mean-grade noise
floor is ≈ ±2.5 points.** If that holds, it retroactively invalidates the +1.62 (C5 guard), the +0.92
(recent arm), and the +0.95 (rerank_k, t = 2.29). Run it, publish the number, and stop arguing about
deltas smaller than it.

**Kill the mean of a 0–100 LLM score as an inferential object.** The repo reported "+1.62, paired
bootstrap 95% CI [+0.92, +2.36]" for a change it *simultaneously proved could not have moved any
score* — the guard is content-neutral and never fired. The CI was tight and the effect was exactly
zero. That is what a confidence interval on a meaningless quantity looks like. Do not build a second
one.

**Everything is paired.** Same questions, same seed, same corpus and prompt fingerprints.

| Outcome | Test | Power |
|---|---|---|
| Deterministic assertions | none — they are facts; report the count | — |
| Needle recall, n=120 | McNemar exact on paired hit/miss | 80% power to detect **+9 pts** — which is why the Phase-1 threshold is +8 and the reject line +5. **Build 300 needles if a resident can spend 4 hours; 120 is the floor.** |
| Judge pairwise, gate-40 | McNemar, ties dropped; Wilson CI | at n=40 with ~30% ties you need roughly a **72/28 split among decided pairs** for p<0.05. Write that in the pre-registration so nobody is surprised. |
| Surgeon pairwise, 24 real + 6 sham | exact binomial CI | decision rule: lower 90% bound of the real-item win rate **> upper 90% bound of his own sham floor**. He is compared against his own measured noise, not against a coin. |

**Variance reduction, in order:** temperature 0 for synthesis → fix retrieval determinism (D18) →
generate 3 samples per question per arm and take the modal judge verdict across the 3×3 pairwise
comparisons. That roughly halves effective σ and triples a generation cost that is already trivial.
It is how you get real signal at n=67 without buying more questions.

**One primary plus at most three co-primaries per phase**, Bonferroni across co-primaries at
α = 0.05/k. Guardrails are one-sided non-inferiority at α = 0.05 with **no correction** — you *want*
to be trigger-happy about regressions.

**Never gate on `dev-27`. Never touch `gate-40` twice in one phase.**

### 6.8 What gets thrown away

- **Mean 0–100 judge grade as a gate.** Logged only, annotated with the noise floor.
- **The `Δ vs base` column in `RESULTS.md`.** It compares runs across three different synthesis
  models; the `+8.66` is a model swap. A column whose values are not mutually comparable is worse than
  no column.
- **`verified_fraction`** (§0.3). It measures the grading harness. Delete it; D14/D15 replace it.
- **`groundedness = 1 − flags/1380`.** Not groundedness — one minus a flag rate, and it scores 1.0 on
  a zero-citation answer. Delete the name and the number.
- **The entailment gate as a merge gate and as a rendered badge.** Advisory only.
- **The seven-subspecialty absolute-scoring pipeline.** Replaced by pairwise.
- **The six ungraded knob-sweep arms.** Do **not** grade them. They were generated against an index
  that is about to be deleted and rebuilt; grading them buys a comparison against a corpus that will
  not exist. Delete the arms, keep the runbook. *(This supersedes §1.5's "grade them" — the
  methodologist is right and I was wrong: the arms are pre-rebuild and worthless.)*
- **The 20-Q `RERANK_K` result** (+0.95, t = 2.29). Below an unmeasured noise floor, cheap-proxy
  synth, 20-question subset. Do not flip the default. Re-decide it on the needle set.

**Kept:** the 406-defect ledger and its taxonomy — nine categories plus `degraded_readability`, the
best artifact in the repo. Make *defect counts by category* the reported outcome in place of the mean
grade; the frozen 67-question
manifest and its checksums (now split 27/40); the per-run `run-config.json`, *fixed*; the
experiment-ledger discipline, plus two new fields `preregistration_sha` and `noise_floor`;
`judge_verifier.py`'s two-lab blind panel; and **the retraction, prominently** — a project that
publishes its own retraction is the only kind whose remaining numbers are worth believing.

---

## 7. Execution order

```
STEP 0  ── land two live bugs, one afternoon, no rebuild
          D7  fingerprints; run_benchmark.py refuses to start without them
          D13 zero-citation groundedness returns None, not 1.0
          + fix the stale CORPUS_DIR default (config.py points at an empty mount)

STEP 1  ── measure the noise floor.  Two identical runs. ~2.2h wall, 0 human minutes.
          Publish evaluation/noise-floor/noise-floor.json. Predicted ≈ ±2.5 pts.
          Everything downstream must clear this number.

STEP 2  ── PHASE 1, retrieval recall.  Free. Zero human, zero judge.
          query-side (no rebuild):  1.3 union · 1.6 no-swallow · 1.7 one retriever
          ONE ingest pass → index-next/ → rebuild guard (§3.5) → promote:
              1.1 bibliography strip (LINE level)     1.2 caption indexing
              1.4 heading chunker (ablated)           3.1 printed_page      ← fold in
                                                      3.2 chapter from headers ← fold in
          Ablate all five separately against the needle set. Ship only what earns +1.0 pt.
          1.5 rerank_k decided here, on needles, by a pre-committed rule.

STEP 3  ── PHASE 3, citation verifiability.  Free + 27 human minutes.
          3.3 quoted spans (SIDECAR ONLY — never inline) → 3.4 page images → VR ≥ 0.95
          Gated on prose non-inferiority (D19-D22 + Instrument C). Verifiability must
          not cost readability. Unlocks 4.2 (the badge) and makes Phase 2 gradeable.

STEP 4  ── PHASE 2, currency.  90 human minutes. Now gradeable.
          2.2 three sidecars → 2.1 routing → 2.3 full-text Results → 2.4 guidelines
          → 2.5 trial table → 2.6 date-stamps

STEP 5  ── PHASE 4, answer shape.  4.1 decision furniture · 4.2 badge · 4.3 language · 4.4 figures
```

**Total attending time for the entire program: about 4 hours** (90 + 15 + 12 min of instruments, plus Sentinel-21 diffs). Everything else is bought with
deterministic assertions and cross-lab judges that must pass a control panel before their verdicts
are allowed to count.

**If only one thing ships, ship 3.3 — the verbatim quote contract.** It depends on nothing but a
prompt change and a string match. It is simultaneously the fabrication detector, the span localizer,
and the thing the reader actually wants. It raises the ceiling that everything else is measured
against.

---

## 8. New files this plan requires

```
evaluation/assertions/test_corpus_invariants.py       # D1-D8
evaluation/assertions/test_retrieval_invariants.py    # D9-D11, D18
evaluation/assertions/test_citation_invariants.py     # D12-D17
evaluation/needles/needles-v1.jsonl                   # question -> chunk_id; 120 floor, 300 target
evaluation/trials/named-trials.jsonl                  # 25 question_id -> trial + year
evaluation/splits/split-v1.json                       # dev-27 / gate-40 + sha256
evaluation/gates/phase-{1,3,2}.preregistration.json   # committed BEFORE any arm is generated
evaluation/holdout-usage.log                          # monotonic; >1/phase retires gate-40
evaluation/noise-floor/noise-floor.json               # the number that ends the delta arguments
evaluation/human/<gate>/{items,blinding-key,key.sha256,responses}
evaluation/canary/sentinel-21.json
evaluation/canary/poisoned-chunks.jsonl               # shadow index only
```

