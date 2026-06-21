# C2 — Synthesis completeness

**Where the synthesis prompt is assembled (FACT — file:symbol):**
`neuro_core/synthesize.py` — the static `SYSTEM_PROMPT` (lines 8-20) plus the per-call user prompt built
in `synthesize()` (lines 88-103, via `_format_passages` / `_format_appended` / `_figure_note`). This is
the prompt that produces the graded Lane A answer.

**Does it require decision thresholds / comparators / risks? (FACT): No.** `SYSTEM_PROMPT`
(`synthesize.py:8-20`) instructs only to: answer **only** from the provided passages/images; **cite the
bracketed source number** for every clinical claim; describe attached figures and still cite them; emit
the verbatim refusal `"Not found in the provided sources."` when unsupported (`synthesize.py:6,15`);
**state disagreement** explicitly and attribute each view; and be "concise and clinically precise…
decision-support, not a substitute for clinical judgment." There is **no instruction** to surface
decision thresholds, patient-selection criteria, head-to-head comparators, or a structured risk/benefit
or complications profile. Completeness on those axes is therefore left to whatever the passages and the
model volunteer — it is not enforced.

**HYPOTHESIS (fix direction, not implemented):** a completeness defect for decision-support questions
would be addressed by extending `SYSTEM_PROMPT` (`synthesize.py:8-20`) to require, when the passages
support it, the decision threshold / indication criteria, the comparator (what it is being weighed
against), and the key risks/trade-offs — while keeping the grounded-citation and abstention rules
intact. Low-risk, prompt-only change; out of scope for the current C5 fix.
