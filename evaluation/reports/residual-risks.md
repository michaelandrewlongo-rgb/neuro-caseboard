# Residual Risks & Limitations

Honest accounting of what this evaluation does **not** establish and what remains unresolved.

## R1 — A single 67-item set cannot establish generalization (methodological)

The benchmark is the **only** evaluation set; there is no held-out split. With one set you optimize
against, you **cannot statistically distinguish a real improvement from overfitting** — this is a
property of the experimental design, not something more analysis fixes.

- We mitigated *fix-level* overfitting by construction: the one shipped change (C5) is a **content-
  agnostic structural invariant**, proven by a **benchmark-independent unit test** (stubbed synthesis),
  and reasoned about at the code/mechanism level — not selected because a benchmark number moved. The
  tell: it did **not** make the benchmark's failing question pass.
- We avoided *evaluation-level* overfitting (Goodhart) by using the benchmark as a **diagnostic**, never
  a loss function: `failure → root-cause → fix the mechanism`, never patch-the-question. The clearest
  evidence is that the highest-score-leverage cluster (C1 corpus currency, 60% of defects) was
  **deferred** precisely because the tempting "fix" (inject the named 2022–2025 trials) would game these
  67 without generalizing.
- **What would actually measure generalization (required next experiment):** a **disjoint held-out set**
  of contemporary neurosurgery questions, never inspected during fixing, re-scored with the patched
  engine. This is the single highest-value follow-up. Until then, generalization rests on mechanism +
  benchmark-independent tests, not on the score.

## R2 — Engine non-determinism confounds the before/after (measurement)

vertex/gemini-2.5-pro exposes no seed, so the per-question score varies run-to-run independent of any
code change. The observed +1.62 mean delta (CI [+0.92, +2.36]) is therefore **uncontrolled noise**, not
a treatment effect (the C5 change is content-neutral; see final-comparison.md). A control rerun (same
code, no fix) was not performed (budget); it would be the clean way to quantify the noise floor.

## R3 — Grader is an LLM (measurement)

Grading used 7 Claude subspecialty graders (deliberately *not* the gemini answer-model, to avoid
self-grading bias). Graders are themselves non-deterministic and could over/under-weight currency vs.
the rubric. Evidence-verification coverage is honestly low (≈5/185 anchors PubMed-verified in baseline;
the rest `verification_unavailable`, never fabricated). Grades are defensible expert judgments, not
ground truth.

## R4 — C1 corpus evidence-currency: DEFERRED (the real, unaddressed capability gap)

60% of defects are the corpus predating 2022–2025 practice-changing evidence (ESCAPE-MeVO, SELECT2, the
MMA RCTs, ENRICH, SANTE, RESCUEicp, GFAP/UCH-L1, SLIP/NORDSTEN, JLGK0901). This is the dominant driver
of B/C/D grades and is **not fixed**. The generalizing remediation is a literature-retrieval lane
(`neuro_caseboard/literature/`) that surfaces recent evidence for *any* recency gap — a substantial,
network-dependent change with its own latency/regression profile, to be done and measured separately
(TKT-C1).

## R5 — SPINE-02 / nested re-clarification: follow-up (reliability)

SPINE-02 stays `not_gradable` because a re-clarified rewrite returns `None` through the runner's
single-level `_resolve_answer` — upstream of the C5 guard. Follow-up: (a) a runner guard that resolves
nested clarifications or falls back to the original question on an empty/clarification re-call, and/or
(b) the deeper C4 fix (don't split a coordinated "A and/or B" question). Not done this pass to avoid
changing the eval harness mid-comparison.

## R6 — Open tickets (not addressed this pass)

C2 (synthesis decision-coverage), C3 (over-absolute language calibration), C4 (question
mis-scoping/decomposition) remain OPEN with documented root causes and acceptance criteria. Intervention
#2 was deliberately skipped (see experiment-ledger.md) to keep the comparison attributable.

## Strongly-supported vs uncertain conclusions

**Strongly supported:** the engine is clinically **safe** on this benchmark (0 unsafe / 0 safety-critical
across 67, both runs); its failure mode is **currency/completeness, not danger**; the C5 reliability
guard is correct and test-proven. **Uncertain / not claimed:** any benchmark *score* improvement from the
fix (it's noise); generalization to unseen questions (no held-out set); the magnitude of the C1 gap's
remediability.
