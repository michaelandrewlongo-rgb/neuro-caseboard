# Retrieval-breadth sweep — concluded verdict

**Method:** paired LLM-judge (`evaluation/scripts/grade_pairs.py`), blinded + order-randomized,
independent judge `anthropic/claude-sonnet-4.5` (distinct from the glm-5.2 answer model).
Answers were already on disk (deploy-synth glm-5.2, bakeoff-21 subset). Control = `control-fixed`
(RETRIEVE_K=40 / RERANK_K=12). Total grading spend: **$1.18**.

**This is a MACHINE verdict** — the autonomous stand-in for the human blinded sheets
(`evaluation/runs/blinded-grading*/`), matching the `eval/mmr-score-pilot` precedent. A paid
human deploy-synth grade remains the confirmatory step before calling any flip final.

| Arm | n | mean ctrl | mean arm | Δ (arm−ctrl) | CI95 | t | W/L/T | verdict |
|---|---|---|---|---|---|---|---|---|
| **RERANK_K=20** | 21 | 85.24 | 88.29 | **+3.05** | **[0.89, 5.20]** | 2.77 | 16/5/0 | **DECISIVE WIN → default 12→20** |
| RETRIEVE_K=80 | 20 | 86.35 | 85.00 | −1.35 | [−4.16, 1.46] | −0.94 | 9/11/0 | null/slightly worse → keep 40 |
| rerank-none (RRF only) | 21 | 85.90 | 85.67 | −0.24 | [−4.16, 3.69] | −0.12 | 10/11/0 | null → reranker earns its keep |
| rerank-qwen3 | 21 | 85.29 | 81.86 | −3.43 | [−10.75, 3.89] | −0.92 | 9/12/0 | not better than bge → keep bge |
| embed-qwen3 | 21 | 85.33 | 86.76 | +1.43 | [−1.44, 4.30] | 0.98 | 13/8/0 | weak-positive, CI spans 0 → keep bge-large |

**Action:** `neuro_core/config.py` RERANK_K 12 → 20. All other defaults unchanged.
