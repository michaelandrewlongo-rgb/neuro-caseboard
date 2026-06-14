# Query-adaptive reasoning for variant conflation — research memo

**Date:** 2026-06-14
**Status:** Research / recommendation (not yet specced or built)
**Context:** Independent grading of a "decompressive craniectomy for TBI" briefing found the engine
**conflated two distinct operations** the corpus files under one heading — the **unilateral
frontotemporoparietal hemicraniectomy** (wanted) and the **bifrontal (Kjellberg-type)
decompression**. Symptoms: an incision described "to the *contralateral* zygoma" (a
bicoronal/bifrontal trajectory) and a bifrontal pediatric figure. The figure guard can't catch
this — both variants are cranial/anterior, so it's *intra-topic variant conflation*, not a
cross-domain leak. Goal: fix it **without forcing the user to write hyper-specific queries**.

## Empirical anchor (already validated)

Issuing the variant-resolved query a disambiguation step *would auto-generate* ("unilateral FTP
hemicraniectomy, not bifrontal") drove `bifrontal` / `bicoronal` / `Kjellberg` mentions to **0**,
removed the contralateral-zygoma incision, kept the correct 12×15 cm flap, and dropped the
bifrontal pediatric figure. **So the resolve-mechanism demonstrably works** — the open work is the
*detect* + *decide* front-end and an eval.

## Framing: this is AmbigQA, not complexity-routing

- The **Adaptive-RAG family** (Adaptive-RAG, LogicRAG, RAP-RAG) routes on query *complexity*
  (no-/single-/multi-hop). Our query isn't complex → wrong branch.
- The fit is **AmbigQA** (Min et al., EMNLP 2020): an ambiguous question should yield *every
  plausible answer*, each with a *disambiguated rewrite*. >half of natural questions are ambiguous.
  CondAmbigQA (2025) extends to condition-resolved ambiguity.
- Documented default failure: LLMs **under-ask and presume** intent (RLHF bias toward "complete but
  presumptuous" answers — Modeling Future Conversation Turns, ICLR 2025). In RAG that presumption
  becomes conflation. So an explicit disambiguation stage is required; prompt-tweaking won't do it.

## Recommended design — AmbigQA-style variant disambiguation in `neuro_core`

Three decisions:

1. **Detect** variant-ambiguity cheaply.
   - Primary: a small LLM classifier seeded with a curated **neuro procedure-variant taxonomy**
     (e.g. DHC → {unilateral FTP, bifrontal}; "ACDF vs corpectomy"; "pterional vs orbitozygomatic";
     "EVD vs lumbar drain").
   - Signal alt: detect when top-k retrieval clusters into ≥2 named variants.
   - (Research: ambiguity is linearly detectable from model internals — "Sparse Neurons", 2025 —
     but the taxonomy-classifier is the pragmatic lever.)

2. **Decide** answer-vs-clarify.
   - Default to **auto-disambiguate** (AmbigQA-style): pick the likeliest variant from context, or
     answer each variant separately (segmented). This honors "don't force the user to be specific."
   - Ask a clarifying question only as a **high-stakes fallback** when variants are genuinely
     indistinguishable (EVPI / Structured-Uncertainty framing; CLAMBER benchmark).

3. **Resolve** in the engine.
   - A pre-retrieval `query_analyze()` step → `{ambiguous, variant_axis, variants:[per-variant
     rewrite], chosen}`.
   - Re-issue retrieval with the chosen variant's rewrite (the validated lever), **plus** a
     synthesis directive: *"answer for variant X only; if the corpus blends variants, separate them
     — never merge steps across variants."*
   - Lives at the same boundary as `topic_extract` (before `_retrieve` in `neuro_core/query.py`).

## Eval plan

- Ambiguous-neuro-query set: DHC, ACDF/corpectomy, pterional/OZ, EVD/lumbar-drain, etc.
- Metrics: **conflation rate** (LLM-judge / manual: does the answer mix variants?) and
  **over-ask rate** (does it ask when it shouldn't?). Anchor: scoped DHC → 0 bifrontal mentions.
- Discipline: fixing-pipeline-output-errors — prove ACTIVE on real ambiguous queries; confirm
  non-ambiguous queries are unchanged (no regression / no spurious clarifying questions).

## Cost / risk

- +1 LLM pass (Vertex) for `query_analyze` + one extra retrieval on the resolved rewrite — modest.
- Risk: over-disambiguation / spurious clarifiers → mitigate by defaulting to auto-resolve and
  gating clarification on high ambiguity confidence.

## Relationship to other work

This is the **prose analogue of the figure-precision guard** (`figure_offtarget` strict) — right
region, wrong *variant*. It generalizes across neurosurgery and removes the burden of hyper-specific
queries.

## Next step

Brainstorm → spec → plan (it's a real architectural change: query pipeline + synthesis + eval).

## Sources

- AmbigQA — https://arxiv.org/abs/2004.10645
- CondAmbigQA — https://arxiv.org/pdf/2502.01523
- Modeling Future Conversation Turns (ICLR 2025) — https://arxiv.org/pdf/2410.13788
- Structured Uncertainty / EVPI clarification — https://arxiv.org/html/2511.08798v1
- CLAMBER (identify+clarify ambiguity) — https://arxiv.org/pdf/2405.12063
- Sparse Neurons / ambiguity signal — https://arxiv.org/pdf/2509.13664
- Adaptive-RAG — https://arxiv.org/pdf/2403.14403
- Agentic Verification for Ambiguous Query Disambiguation — https://arxiv.org/html/2502.10352
