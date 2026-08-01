# neuro-caseboard — outside product review

*Brief: make the end product materially better at its stated purpose — answering questions
grounded in literature that are genuinely helpful to a practicing neurosurgeon. Scope excludes
security, privacy, and compliance by request.*

---

## Verdict

The engineering is strong and the measurement culture is unusually honest — a 406-item failure
ledger, blinded judge panels, a published retraction of an over-claimed result. That is rarer
than good code and it is the reason this review can be specific.

The product problem is not a bug. It is this:

> **It is a textbook-recitation engine presented as a literature-grounding engine, and the
> person it is built for already owns the textbooks.**

Two facts, both from the repo's own data, establish it.

**1. It never produces an excellent answer.** Across every graded run of the deployed
configuration — 66 to 67 questions each — the grade distribution is *zero A's*. Baseline:
`{"A": 0, "B": 38, "C": 22, "D": 6}`, mean 77.74. Best deployed arm (`youmans_pubmed`): `A:0,
B:61, C:5`, mean 83.87. A tight band of B's with no A's is the exact signature of competent
paraphrase: correct, reasonably complete, never current, never sharp enough to change a
decision. The graders' own rubric defines B as "mostly correct, limited omissions" — which is
what a resident gets by reading the chapter, minus the ability to check it.

**2. Its citations cannot be checked.** No Youmans citation this product emits can be opened by a
human: the chapter label is wrong 98.3% of the time and the page number is a PDF page, not a
printed folio (Finding 1, below — traced chunk by chunk). Verifiability is the *only* reason to
prefer a grounded system over a frontier model answering from weights. That reason does not
currently hold.

> **Correction (2026-07-08).** An earlier revision of this review cited
> `"evidence_verification": {"total_evidence_anchors": 185, "verified": 5, "verified_fraction":
> 0.027}` as evidence that "expert graders could resolve only 2.7% of its citations." **That was
> wrong.** `evidence_anchors` are the *grader's own* external references (NEJM/JAMA DOIs it cited
> while judging); `verification_unavailable` means the offline grader could not reach the internet
> to check its own DOI. The metric is a property of the grading harness, not of the product, and
> `summarize_grades.py:70` should be deleted rather than quoted.
>
> The correction cuts the other way, and harder: **nobody has ever measured whether this product's
> citations resolve.** Finding 1 is the first measurement, it was done by hand, and the answer is
> that they do not. The fix plan makes that measurement a deterministic CI assertion.

Everything below explains why (2) happens, and what to do about it and (1).

---

## Finding 1 — The citation pointer is structurally broken

I traced citations from a real benchmark answer back into the LanceDB index.

The thrombectomy answer (`NIS-02`) cites:

```
[2] Youmans and Winn Neurological Surgery — 300 - Radiosurgery for Intracranial
    Vascular Malformations (p. 5710)
```

That chunk's text begins `3357 420 This chapter includes an accompanying lecture
presentation… INTRODUCTION Intracranial occlusive disease spans a wide spectrum…`

So the passage is **Chapter 420, printed page 3357**. It is labeled Chapter 300. Retrieval found
the right text; the pointer attached to it names a chapter 120 chapters away, on a topic
(radiosurgery for AVM) unrelated to the claim (thrombectomy). A surgeon who checks this citation
finds nothing and concludes the system fabricated it. It didn't. The label did.

**This is systemic, not anecdotal.** For every Youmans chunk containing an in-text `CHAPTER N`
header, I compared that ground truth against the stored `chapter` field:

| Youmans chunks with a verifiable in-text chapter header | 1,691 |
|---|---|
| Label matches the actual chapter | 28 (**1.7%**) |
| Label is wrong | 1,663 (**98.3%**) |

Cause: `ingest.py::_classify_toc` assigns chapters by blanketing PDF TOC bookmark page-ranges.
This libgen scan of Youmans exposes 8 usable bookmarks for a 445-chapter book, so each label
smears across hundreds of chapters:

```
_H. Richard Winn - Youmans and Winn Ne…    pp 2–6329     658 chunks   (the filename, as a chapter)
DEDICATION                                 pp 8–77       126
1 - History                                pp 78–648    1081
25 - Positioning for Spine Surgery         pp 649–3001  4889   ← 38% of the book
5yk4n23ycnpq9lc2A5dqvlhvrs2rhdbs9c6jz5…    pp 3002–4180 2404   ← a hash blob, as a chapter
300 - Radiosurgery for Intracranial Va…    pp 4181–6001 3752
```

Nearly five thousand chunks — spanning tumor, vascular, functional, and pediatric neurosurgery —
are labeled *"25 - Positioning for Spine Surgery."*

Second, independent defect: **`page` is the PDF page, not the printed page.** Youmans is a
four-volume set whose folios restart per volume; the stored page runs 2–6329. `p. 5710` does not
exist in any physical volume. The measured `pdf_page − folio` offset is not even constant
(median 1455; scattered across 1028, 1142, 1588, 1672, 1728 at volume breaks). **No Youmans
citation this product emits can be opened by a human.** No metric in the repo measures this; the
count above is the first time it has been measured.

The fix is largely built already and never landed. The vendored retriever reads
`hit.get("printed_page")` (`vendor/caseprep/caseprep/retrievers/textbook.py:41`) and renders
`f"{book}, p.{folio}"`. `neuro_core`'s `Chunk` dataclass has no such field, so it is always
absent. Recovering it is cheap: a bare leading folio token is already present on 38% of pages
from a naive regex; a proper running-header parse of the top/bottom text block at ingest gets
essentially all of them.

Third: `Citation.text` is the **entire ~600-word chunk**. Nothing ever localizes which sentence
supports the claim. The model emits `[2]`; no code resolves it, checks it exists, or extracts a
span. A citation that points at 600 words is not a citation; it is a reading assignment.

---

## Finding 2 — 15% of the index is bibliography

Reference-dense chunks (≥6 `et al`, or ≥5 numbered `Author AB,` citation starts):

```
6,420 / 42,228 chunks  =  15.2% of the corpus
Youmans 2,616 · Benzel 836 · Schmidek 827 · Bridwell 663 · CNS RadOnc 308 · Greenberg 306 …
```

These pages carry no clinical content, and they are *lexically dense in exactly the tokens that
currency-sensitive questions contain* — trial acronyms, author eponyms, years, journal names. They
compete for the 40 RRF fusion slots against real prose, and they inherit the same wrong chapter
label. One example, verbatim, labeled *"25 - Positioning for Spine Surgery," p. 1119*:

> `466.e23 63 References 11. Gurrieri F, Trask BJ, van den Engh G, et al. Physical mapping of the
> holoprosencephaly critical region on chromosome 7q36. Nat Genet. 1993;3:247–251…`

Dropping them is an ingest-time filter and returns ~15% of the candidate pool to real content.
Also excluded from the indexed `text` column: **figure captions** (`chunk.py:11-13`) — the caption
that names the anatomy is invisible to both the dense and the BM25 lane.

---

## Finding 3 — The literature lane is the answer to the biggest problem, and it is switched off

The repo's own failure analysis is unambiguous. Of 406 atomic defects mined from grader
criticism, cluster **C1 — corpus evidence-currency — is 245 defects (60%), priority 200, marked
DEFERRED / UNFIXED.** Named, grader-verified misses include ESCAPE-MeVO, SELECT2, the MMA RCTs
(EMBOLISE / STEM / MAGIC-MT), ENRICH, SANTE, RESCUEicp, plasma GFAP/UCH-L1, SLIP/NORDSTEN,
JLGK0901. `NIS-01` earns a D by repeating an outdated distal-thrombectomy claim the grader calls
*"the one finding that could mislead toward over-treatment."* `NIS-05` describes the MMA RCTs as
"in progress." `TRAUMA-02` uses an ICP threshold of >20 where current practice is >22.

Meanwhile:

- The corpus is **19 textbooks**, newest Youmans 8th ed. (2022). Zero trials. Zero guidelines.
- The `[L#]` "Contemporary Literature" lane retrieves **PubMed abstracts** — `k=8..12`, 7-year
  recency. Abstracts do not contain effect sizes, confidence intervals, exclusion criteria, or
  subgroup results. They are also the most spin-laden text in the paper.
- The `[D#]` lane — 70 chapters of curated **full-text** cerebrovascular literature, already
  built and sitting in `cv_full_text/` — defaults to **off**:
  `enabled=_flag(os.environ.get("CORPUS_RETRIEVAL", "false"))` (`corpus.py:69`).

So the one component that directly attacks the 60% defect cluster ships disabled, and the
enabled currency lane reads only abstracts.

---

## Finding 4 — Retrieval leaks recall, and omission is the top failure category

`retrieval_omission` is the single largest bucket in the ledger: **175 of 406 defects (43%)**.
Consistent with the mechanics:

- **Single query.** No expansion, no HyDE, no multi-query, no multi-hop. The only "second query"
  is the disambiguation rewrite, and it **replaces** the original rather than unioning with it
  (`query.py:250`). The original query's hits are discarded. Unioning is free recall.
- **`RERANK_K = 12`.** Only 12 chunks ever reach the model. The 12→16 A/B was *measured*: mean
  +0.95, head-to-head 14–6, ~23% slower. It was correctly not shipped on one test — but it was
  then dropped rather than re-run.
- **Six knob-sweep arms** (`rerank-none`, `rerank-qwen3`, `rerank_k-20`, `retrieve_k-80`,
  `embed-qwen3`) were generated, blinded, and **never graded into numbers**. That is sunk compute
  with no decision attached.
- **Chunks are 600-word windows that never cross a page boundary and are structure-blind** —
  `record.text.split()` and slide. Any concept spanning a page break exists in no chunk.
  `chunk_strategies.py` already implements heading-aware and chapter-packing strategies; it is
  wired only to a benchmark, never to the index.
- Six retrieval paths swallow exceptions and return `[]`. A dead lane is indistinguishable from
  "no results" — this exact bug already bit once (`retrieve.py` imported a nonexistent
  `engine.query.search`; every citation rendered `⚠ to verify` until commit `ace4d7b`).
- The **Build/briefing path uses a different, much weaker retriever**: BM25 only, no dense
  vectors, no reranker, query stripped to ≤8 terms with all tokens under 3 characters deleted
  — so `CT`, `AP`, `3D`, `T1`, `T2` are silently removed from every board query.

---

## Finding 5 — The ⚠ badge is noise, and it can be gamed by omission

At the shipped NLI threshold (0.3), out-of-sample flag **precision is 0.24**. Three of every four
warnings are false. A surgeon unlearns that badge within a week.

Worse, the gate has two structural holes:

- **Uncited sentences auto-pass** (`answer_verify.py:83-85`). An answer with zero citations scores
  `groundedness = 1.0`. The metric rewards the failure mode it exists to catch.
- **The premise is the concatenation of full 600-word chunks.** The repo's own data shows why this
  matters: whole-premise precision yields groundedness 0.07; best-*sentence* premise yields 0.80.
  The system never asks "which sentence supports this claim" — the question a surgeon is asking.

And the docstring promises enforcement the code does not deliver: *"the gate may only ever REMOVE
a weak citation"* (`entailment.py:6-7`). Nothing in the Ask path removes anything. It is advisory
metadata rendered as a warning.

---

## Finding 6 — The figure lane is dead in the deployed configuration

`SESSION-HANDOFF.md` records that **glm-5.2 is text-only on OpenRouter**
(`input_modalities=['text']`), so page images 404'd and 500'd the request; the fix was to retry
text-only. The woven system prompt still instructs the model: *"Some textbook sources include an
attached page image… you may describe what the figure shows and must still cite that source
number."*

The deployed model is therefore told to describe attached images that never arrive, and cite them.
That is an invitation to hallucinate a figure description. Meanwhile the corpus contains 10,367
figures with Gemini-generated captions and rendered page images at 160 DPI — a genuinely valuable
asset the deployed path cannot see.

---

## What I would do, in order

### 1. Make one citation verifiable, end to end. *(Highest leverage. Mostly plumbing.)*

Nothing else matters until a surgeon can click a claim and land on the sentence. Four steps:

- Add `printed_page` to `Chunk` and populate it at ingest by parsing the running header/footer
  text block. The consumer already exists and reads `hit.get("printed_page")`.
- Derive `chapter` from in-text `CHAPTER \d+` headers and running heads. Fall back to `None` —
  never to a stale bookmark, never to a filename or a hash. Wrong is strictly worse than absent.
- **Make the model quote its support.** Require the supporting sentence verbatim alongside each
  `[n]`, then string-match it back into the cited chunk and reject the citation if it isn't there.
  This is simultaneously a fabrication check, a span localizer, and the thing the reader wants.
- Link the citation to its rendered page image. You already have them.

Then make **verifiability** the north-star metric, ahead of mean grade — measured properly, as the
fraction of citations whose quoted span string-matches into the cited chunk *and* whose folio
resolves to a real page. (Do **not** reuse the existing `verified_fraction`; it measures the
grader's own DOIs, not the product — delete it.) Mean grade has moved 77.7 → 83.9 while
verifiability was never measured at all. The metric you optimized is not the metric that makes the
product worth using.

### 2. Turn on the literature, and read past the abstract.

- Flip `CORPUS_RETRIEVAL` on. Route cerebrovascular questions to the 70-chapter full-text corpus
  that is already built and disabled. Measure `outdated_evidence` defects before and after.
- Pull **full-text Results sections** for PubMed hits where OA permits, rather than abstracts. The
  numbers a surgeon needs — effect size, CI, exclusions, subgroups — are never in the abstract.
- **Add a guidelines lane.** AHA/ASA, CNS/AANS, NICE. They are free, structured, versioned, and
  they are what gets quoted at M&M. There are currently zero in the corpus.
- **Add a named-trial table.** The failure ledger enumerates the exact misses. A few hundred rows
  of `trial · design · n · primary endpoint · result · caveat · year`, retrieved by acronym, would
  erase a large share of the 70 `outdated_evidence` defects and much of `missing_comparator`.
- **Date-stamp every claim inline.** If a statement rests on a 2022 textbook page, say so. A
  surgeon can price staleness — but only if you show it.

### 3. Answer the question a surgeon actually asked.

Cluster C2 (open, 102 defects) decomposes almost entirely into missing decision furniture:
`missing_comparator` 34 · `missing_decision_threshold` 33 · `missing_risk_or_tradeoff` 24 ·
`missing_patient_selection` 11.

The system prompt asks for free prose and imposes no structure. Ask for the furniture explicitly —
not as a rigid template, but as a checklist the answer must either address or explicitly declare
unestablished: **the threshold with its units · the comparator · who is excluded · the effect size
with its interval · what would change the answer.**

And un-skip C3. `overabsolute_language` (38 defects) was *deliberately* deferred to keep a
before/after clean. That was the right call for one experiment and the wrong place to leave it:
"should" and "always" in a domain this hedged is the fastest way to lose a surgeon's trust.

### 4. Recover the recall you are throwing away.

In rough order of return per unit of work:

- **Drop the 6,420 bibliography chunks at ingest.** One filter; recovers 15% of the candidate pool
  and removes precisely the chunks that hijack trial-name queries.
- **Union the disambiguation rewrite's hits with the original's** instead of replacing them.
- **Index figure captions into the `text` column**, or as their own sibling chunks.
- **Re-run the RERANK_K sweep** to a decision, and grade the six blinded arms already sitting on
  disk. Either extract a number or delete them.
- **Wire `chunk_strategies.py`'s heading-aware chunker into the index** and re-run the chunking
  benchmark that already exists.
- **Replace the six bare `except: return []`** with a raise or a loud counter. You have already
  shipped a silently dead retrieval lane once.

### 5. Make the warning mean something, or remove it.

At precision 0.24 the badge is worse than nothing: it teaches the reader that warnings are noise,
which is precisely the wrong reflex to train. Localize the premise to the best-matching sentence
— your own measurement says groundedness goes 0.07 → 0.80 — and stop scoring uncited sentences as
supported. If precision cannot clear roughly 0.6, take the badge off the screen.

### 6. Resolve the figure lane.

Route figure-bearing questions to a vision-capable model, or delete the image instructions from the
woven prompt. Today the deployed model is told to describe images it never receives.

---

## The one-sentence version

Fix the citation pointer and turn on the full-text literature; those two changes convert this from
a well-engineered paraphrase of a 2022 textbook into the only thing a neurosurgeon cannot already
get faster elsewhere — **a current claim with a sentence behind it that he can open and read.**
