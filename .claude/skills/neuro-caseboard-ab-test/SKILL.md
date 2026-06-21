---
name: neuro-caseboard-ab-test
description: Use when a change was made to neuro-caseboard — a textbook/PDF added to the corpus, a retrieval/prompt/code change, or a model swap — and you must prove whether answer quality improved on the frozen 67-question benchmark without regressions. Covers verifying the change is live, re-answering, blinded subspecialty grading, regression detection, and the analysis export.
---

# Neuro-Caseboard A/B Test

## Overview

Prove a change helped (or didn't) against the frozen *Contemporary Questions in Neurosurgery*
benchmark. **The only valid A/B changes ONE variable** — the change under test. Model, prompts,
benchmark, and grader rubric stay frozen, or the result is uninterpretable.

Two failure modes sink these tests; both are non-negotiable to prevent:
1. **Testing a change that isn't actually live** (e.g. a PDF dropped in but never indexed) — you
   spend money measuring nothing.
2. **Grading that inflates the new answer** — grading un-blinded, against stale baseline scores, or
   with the *answer model* grading itself.

## Hard Gate — do not run answers until BOTH are true

- **The change is live in the pipeline.** Corpus add → re-index (`build_index --new-only`) and
  confirm the new book is in `chunks.lance`. Code/prompt change → committed and on the checked-out
  branch. Model/config → set in env and echoed in the run config.
- **The change can reach the GRADED answer.** The graded answer is the *textbook lane* only
  (`neuro_core.query`). The PubMed lane runs but is NOT injected into it (ticket TKT-C1) — so a
  corpus/textbook change is testable, but a "literature currency" change is NOT visible to the
  grader until TKT-C1 ships. If the change only affects the literature lane, STOP and say so.

## Procedure

Setup (worktree root):
```bash
export PYTHONPATH="$PWD:$PWD/vendor/caseprep"
export SYNTH_PROVIDER=vertex VERTEX_MODEL=gemini-2.5-pro
export GOOGLE_CLOUD_PROJECT=project-a20782b0-fdca-45ec-bc7 GOOGLE_CLOUD_LOCATION=us-central1
export CORPUS_DIR=/home/michael/textbook_pdfs INDEX_DIR=/home/michael/neuro-textbook-rag/index
ls ~/.config/gcloud/application_default_credentials.json   # Vertex ADC must exist
```

1. **Classify & make live.** Identify change type; satisfy the Hard Gate. For a corpus add:
   `python3 -m neuro_core.scripts.build_index --new-only` then verify the book's chunk count > 0.

2. **Pick baseline & test set.** Baseline = an existing frozen run dir (default
   `evaluation/runs/baseline-20260620-134705`). Choose the test set by reasoning from the change:
   - a *spine* textbook → spine + adjacent domains; a *code fix* → the questions in
     `evaluation/failure-ledger.jsonl` it targets; a broad change → the worst-N scorers.
   - Full sweep on request: pass all 67 ids. State which ids you chose and why.

3. **Re-answer** into an immutable run dir (resumable; one id per call avoids the runner's
   contiguous-range limitation). Run it in the BACKGROUND so you can watch progress and stop early:
   ```bash
   RUN=evaluation/runs/<change>-$(date +%Y%m%d-%H%M%S)
   for ID in <ids>; do
     python3 evaluation/scripts/run_benchmark.py --run-dir "$RUN" --start-id "$ID" --end-id "$ID" --resume
   done
   python3 evaluation/scripts/finalize_run.py --run-dir "$RUN"
   ```
   Answers land atomically one-per-question; poll with `ab_progress.py` (see Observability below).

4. **Attribution check.** Confirm the change reached the graded answers — e.g. for a new book,
   count its name in the new answers' citations vs the baseline's (expect 0 → many). If the new
   answers don't cite/reflect the change, the lift (if any) isn't from it; investigate before grading.

5. **Blinded paired grading (REQUIRED — never grade un-blinded or against stale scores):**
   ```bash
   python3 evaluation/scripts/build_ab_payloads.py --baseline-run <baseline> --treatment-run "$RUN" \
       --out "$RUN/grading" --ids <ids>
   ```
   Dispatch one **Claude** grader subagent per question (subspecialty-matched to the domain,
   temperature-0, rubric = `evaluation/inputs/nsgy-grader.txt`). Each reads only its
   `$RUN/grading/<ID>.md`, scores BOTH answers 0–100, picks the better, and returns one JSON object:
   `{"question_id","score_A","letter_A","usability_A","score_B","letter_B","usability_B","better","margin","loser_defects_fixed_by_winner":[...],"any_new_safety_errors","rationale"}`.
   Use Claude, not the Vertex answer model — same-model grading is self-grading bias. **Grade
   incrementally** — append each grader's JSON to `$RUN/blinded-grades.jsonl` as it returns and
   check `ab_progress.py` between batches; if the verdict is already decisive, terminate early
   (see Observability). Once you have what you need:
   ```bash
   python3 evaluation/scripts/unblind_grades.py --keymap "$RUN/grading/keymap.json" \
       --grades "$RUN/blinded-grades.jsonl" \
       --baseline-grades <baseline>/baseline-grades.jsonl \
       --out-grades "$RUN/treatment-grades.jsonl" --out-comparison "$RUN/ab-comparison.csv"
   ```
   **Drift control is the credibility check:** `unblind_grades.py` reports the fresh blinded baseline
   mean vs the original baseline mean. Drift must be small (today: −0.1). If `|drift| > 5`, the
   graders aren't reproducing the baseline — the delta is confounded; fix grading before trusting it.

6. **Read the result.** Treatment wins head-to-head + a positive paired mean delta = real lift.
   **Always scan for regressions** (any question where baseline wins), including a **retrieval-crowding**
   check: a big new book can dominate retrieval and pull an answer off-topic (e.g. a deep-tumor
   question answered as spine-only). One regression doesn't sink a net-positive change, but name it.

7. **Export & verdict.** Generate the package, then write a SUMMARY with a keep/revert call:
   ```bash
   python3 evaluation/scripts/export_ab.py --out evaluation/runs/<change>-analysis \
       baseline:<baseline>:baseline-grades.jsonl treatment:"$RUN":treatment-grades.jsonl
   ```
   Then **record the run in the results table** so it is never lost (the gap that left the youmans
   run without a SUMMARY) — this upserts one row per arm into `evaluation/RESULTS.md`:
   ```bash
   # A/B run (one row per arm, from grading/keymap.json + ab-out/<arm>-grades.jsonl):
   python3 evaluation/scripts/update_results.py --ab "$RUN" --label "<what changed>"
   # or a single-arm run (canonical *-summary.json):
   python3 evaluation/scripts/update_results.py \
       --summary "$RUN"/<prefix>-summary.json --run "$(basename "$RUN")" --label "<what changed>"
   ```

## Observability & Early Termination

Don't run blind to completion — a one-sided result is usually obvious early, and finishing it wastes
Vertex calls and grader passes. Run answers in the background and poll:

```bash
python3 evaluation/scripts/ab_progress.py --baseline-run <baseline> --treatment-run "$RUN" \
    --total <N> --keymap "$RUN/grading/keymap.json" --blinded-grades "$RUN/blinded-grades.jsonl" \
    --new-source "<new book name>"
```

It prints answers progress, the attribution check (how many new answers cite the change), and a
running paired tally (delta, head-to-head, drift) with a **CLARITY** verdict:

- `** CLEAR **` (all-one-sided, |delta| ≥ 15) → terminate early; stop the answer job and remaining
  grading, then jump to step 7 with what you have. Note in the SUMMARY that it was an early stop and
  how many questions were graded.
- `LIKELY CLEAR` → grade 1–2 more to confirm, then stop.
- `NOT decisive` → finish the set; the tail (regressions, mixed effects) is where the answer lives.

**Stopping rule:** only call it after ≥30% (min 3) of the set is graded, and never early-stop on the
mean alone — a `** CLEAR **` verdict requires the wins to be one-sided too, so a hidden regression
can't be masked by a big average. If `ab_progress.py` reports large drift, the verdict is unreliable
regardless — fix grading first.

## Common Mistakes (from real baseline runs)

| Mistake | Fix |
|---|---|
| Grade new answers against the *old* baseline scores | Re-grade the baseline fresh, blinded, in the same pass — drift control |
| Grade un-blinded (grader knows which is new) | `build_ab_payloads.py` alternates A/B order and hides origin |
| Grade with Vertex/Gemini (the answer model) | Use Claude subspecialty graders — avoid self-grading bias |
| Run before confirming the change is indexed/live | Hard Gate: re-index + verify chunk count + confirm cited in graded answer |
| Test a literature-lane change and expect a graded lift | PubMed isn't injected (TKT-C1) — not grader-visible; stop |
| Only look at the mean | Scan every question for regressions + retrieval crowding |
| Change >1 thing at once | Freeze model/prompts/benchmark/rubric; isolate the one variable |

## Red Flags — stop

- "I'll just compare to the baseline's existing grades" → no drift control; re-grade baseline blinded.
- "The grader can tell which is new, that's fine" → it isn't; blind it.
- "The PDF is in the folder, good enough" → index it and confirm it's cited.
- "Mean went up, ship it" → check regressions first.
