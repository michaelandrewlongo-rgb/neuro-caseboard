# TKT-C3 — Over-absolute / under-qualified language

- **Failure-mode ID / category:** C3 / `overabsolute_language`
- **Severity / priority:** minor / **P3** (priority 90; 38 defects)
- **Labels:** `severity:minor` `subsystem:prompting` `stage:answer` `status:open`
- **Affected questions:** scattered (38 defects across domains).
- **Artifact links:** `failure-analysis.md` (C3), `failure-ledger.jsonl` (category overabsolute_language).

## Observed vs expected
- **Observed:** claims insufficiently hedged given genuine evidence uncertainty/equipoise.
- **Expected:** calibrated uncertainty — qualify where evidence is mixed or evolving (the spec explicitly prioritizes calibrated uncertainty).

## Suspected layer & causal confidence
prompting / synthesis. **Causal confidence: medium. Fixability: high** (a calibration instruction in the synthesis prompt).

## Status — OPEN (candidate intervention #2)
Low clinical severity but cheap and low-risk; a narrow synthesis-prompt calibration instruction with an easy regression test (sentinel strong answers must not degrade; over-absolute phrasing reduced on affected questions). Preferred over C2 for a second pass because it is the narrowest, lowest-risk lever.

## Acceptance criteria
Reduced over-absolute phrasing on affected questions per re-grade, no degradation of previously strong (B+) answers, no latency/safety regression.
