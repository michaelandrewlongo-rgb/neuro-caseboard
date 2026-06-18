# Eval Monitor Loop — Design

- **Date:** 2026-06-18
- **Status:** Approved design; implementation not yet planned.
- **Scope:** A scheduled, evidence-driven monitoring loop that detects output-quality
  regressions in the case-board build pathway, proposes scoped fixes, tests them, and
  integrates them through two human gates. Phase 1 covers output quality; the detector
  interface is generic so code-health detectors can plug in later.

---

## 1. Motivation

The build pathway's quality rests on an LLM Explorer (planner → author → critic) whose
author call is a *conjunction* of many sub-goals (≥26 valid cards, each with a correct
named specific, no invention, full theme coverage). The probability of a fully-clean board
is roughly the product of per-item success rates, so quality degrades silently and
non-deterministically ("flicker"). Two things are currently unmeasured:

1. the **author specificity rate** (how often an authored specific is actually
   corpus-supported), and
2. the **critic-fix precision** (the critic catches fabrications with no grounding the
   author lacked — a correlated-blind-spot task).

Today's audit (`audit_manifest`) assigns `supported/verify/quarantine` by *topical*
relevance, not *entailment*, so the "supported" badge can over-promise. We want a system
that measures these properties on a cadence, surfaces real regressions with evidence, and
lets us fix them with full traceability — without handing an LLM unsupervised write access
to the codebase.

### Goals

- Detect output-quality regressions on a schedule, backed by concrete evidence.
- Quantify quality as a *distribution* (K-sampled), not a single run, to defeat flicker.
- Let a human approve **what** to fix and at **what blast radius**, then fix/test/integrate
  the tedious middle autonomously.
- Make every change traceable to an issue and an eval delta, and trivially reversible.
- Keep new surface small and offline-testable.

### Non-goals (Phase 1)

- No code-health detectors yet (test failures, crashes, perf) — but the interface admits
  them later with no redesign.
- No persisted issue database / lifecycle dashboard (that is the deferred "Approach 3"
  upgrade; state lives in git for now).
- No auto-merge: nothing lands without human review.

---

## 2. Foundational decisions

| Decision | Choice |
|---|---|
| Issue domain | **Output-quality first**, behind a generic `Detector` interface (design for both). |
| Cadence | **Scheduled only** (e.g. weekly), unattended. |
| Human gates | **Two**: GATE 1 = triage (what to fix, at what scope); GATE 2 = merge (review diff + delta). |
| Blast radius | **Per-issue**, declared in the proposal, approved (and adjustable) at GATE 1. |
| State store | **Git** — issue cards as files, suppressions as a tracked YAML, changes as branches/PRs. |

---

## 3. Architecture & data flow

Location: a new **`eval/monitor/`** package, sibling to the eval scaffolding it reuses.
This is a dev/ops tool, not part of the shipped engine.

```
[scheduled run]  (weekly; OS cron / WSL timer — must run locally; see §5)
   │
   ▼
detect()                          ← eval/monitor/detect.py   (plain Python, NO agent)
   │  for each case in eval/cases.json:  generate()  ×K   (the build pathway)
   │  run registered detectors over the run artifacts:
   │     • coverage-drop          (extends eval/coverage.py, diff vs baseline.json)
   │     • unsupported-specific   (grounded judge; §7)
   │     • flicker                (high run-to-run variance)
   │     • (later: test-failure, exception — SAME interface)
   ▼
list[Issue]  ──drop fingerprints in suppressions.yaml──►  surviving issues
   │
   ▼
write cards:  eval/monitor/issues/<id>.json   +   render digest.md
   │
   ═══════════ GATE 1 — human triage ═══════════
   per card:  approve @tier (knob-only | local | broad)  |  suppress  |  defer
   │
   ▼  (per approved card)
remediate(card)                   ← eval/monitor/remediate.py   (dispatches a subagent)
   │  git branch  monitor/<id>   (isolated worktree)
   │  apply fix WITHIN the approved tier (allowlist-enforced)
   │  re-run eval ×K (before/after delta, full sweep)  +  pytest (48 files)
   ▼
open PR   (body = eval delta + judge summary + test result + tier-compliance + card link)
   │
   ═══════════ GATE 2 — human review (diff + delta) ═══════════
   │
   ▼
merge  →  baseline.json advances to the new known-good;  card → merged
```

**Properties that fall out of this shape:**

- *Traceability* — every commit → PR → issue card → eval evidence. No change without a
  paper trail.
- *Reversibility* — the unit of change is a branch+PR; "undo" is "don't merge" / `git revert`.
- *Drift anchoring* — `baseline.json` advances only on merge, so "known-good" is always a
  state a human approved; the system cannot silently redefine "good."
- *Labor split* — the two autonomous spans are the tedious parts (run builds, score,
  attribute, draft, branch, patch, re-eval, test, open PR); the two human interventions
  sit exactly at the judgment calls ("worth it?", "sound?").

**Reuse vs new.** Reuses `generate()`, `eval/cases.json`, `eval/coverage.py`, pytest, and
the existing git/PR/CI flow unchanged. New surface: `detect.py`, `remediate.py`, the
contract/card schema, the grounded judge, and three data files
(`baseline.json`, `suppressions.yaml`, `issues/`).

---

## 4. Detector interface + issue card (the contract)

```python
# eval/monitor/contracts.py
@dataclass(frozen=True)
class RunArtifacts:                 # the inspection surface for one sweep
    cases:    list[dict]            # eval/cases.json
    dossiers: dict[str, list[Dossier]]   # case_id -> K compiled dossiers
    boards:   dict[str, list[str]]       # case_id -> K rendered markdown boards
    explorer: dict[str, list[ExplorerTrace]]  # themes, pre/post-critic cards (per role)
    baseline: dict                  # last known-good metrics (baseline.json)
    # later, for code-health: test_results, logs  (optional fields)

@dataclass(frozen=True)
class Evidence:
    case_id: str
    detail:  str                    # e.g. claim text, or missing must_cover label
    before:  float | None           # baseline metric
    after:   float | None           # observed metric (robust statistic over K)

@dataclass(frozen=True)
class Issue:
    kind: str            # "coverage_drop" | "unsupported_specific" | "flicker" | ...
    severity: str        # high | medium | low   (ranks the digest)
    title: str
    evidence: list[Evidence]
    locus: str           # root cause: a pipeline ROLE (planner/author/critic) or a file
    proposed_tier: str   # knob-only | local | broad   (the blast radius to approve)
    proposed_fix: str    # NL description of the intended change
    fingerprint: str     # stable hash for dedupe + suppression

class Detector(Protocol):
    name: str
    def detect(self, art: RunArtifacts) -> list[Issue]: ...
```

- The `Detector` Protocol is the firewall: new domains cost one class, never a redesign.
- **`fingerprint`** = stable hash over `(kind + locus + normalized evidence signature)`.
  Same issue → same fingerprint across weeks (enables dedupe + suppression). When the
  underlying signal *worsens*, the signature (and hash) changes, so a muted issue
  resurfaces — suppression that is permanent-until-it-gets-worse.
- **`locus`** is attributed *mechanically* using the logged explorer trace. Example for
  `coverage_drop`: a missing `must_cover` item present in the planner's themes but absent
  from authored cards → locus = **author**; absent from themes entirely → locus =
  **planner/ontology**. Root cause becomes a checked fact, which makes the card trustworthy
  and the blast-radius tier honest.

**On disk:** a card is `eval/monitor/issues/<id>.json` = serialized `Issue` + `status`
(`new → approved → fixing → merged`, or `suppressed`) + provenance (scheduled-run id, git
SHA detected against). `digest.md` renders all `new` cards for reading.

---

## 5. Scheduled run, baseline, suppression

**Detection needs the engine, not the agent.** `detect()` calls `generate()` per case
(Vertex build) and runs detectors (coverage deterministic; judge = one Vertex call). No
Claude-the-agent is involved, so the always-running piece is dumb, cheap, and auditable.
The agent only enters at remediation (§6), the gated/human-present part.

**Runs locally — a hard constraint, not a preference.** The engine reads the live
LanceDB/FTS indexes and authenticates to Vertex via local ADC (`GOOGLE_CLOUD_PROJECT` +
`google.genai`, per `explore_llm.py`). A cloud `/schedule` agent would have neither the
corpus nor the creds. The scheduler is therefore OS-level (cron / WSL systemd timer)
invoking `python -m eval.monitor.detect`.

**Baseline** (`eval/monitor/baseline.json`, last known-good metrics per case). An issue
fires on **either**:

- a *relative regression* — robust statistic over K runs dropped vs baseline beyond a
  noise margin, OR
- an *absolute floor* breach — e.g. coverage < 70%, or any miscited span — regardless of
  baseline.

`detect.py` reads the baseline; it never writes it (only merge advances it, §8).

**Noise control (K-sampling).** Because the build is non-deterministic, each case is built
**K times** (default 3) and a robust statistic (e.g. worst-of-K, or mean−1σ) is compared to
baseline; a regression is flagged only when it clears the noise band. The same K-sample
yields a free **flicker** detector: high run-to-run variance is itself an issue even if the
mean is acceptable. Cost is bounded and configurable: `K × |cases| × ~4 build calls`
(≈180 Vertex calls/week at K=3, 15 cases) + judge calls; both K and the case subset are
config.

**Suppression** (`eval/monitor/suppressions.yaml`): list of
`{fingerprint, reason, date, expires?}`. After detectors run, any Issue with an actively
suppressed fingerprint is dropped *before* it becomes a card. `expires` time-boxes a mute;
worsening auto-resurfaces (via fingerprint change). Dedupe uses the same fingerprint: a
still-open card from a prior run is updated, not duplicated.

---

## 6. GATE 1 triage + remediation runner

**GATE 1 — triage** (`python -m eval.monitor.triage`). Lists `new` cards ranked by
severity; each shows title, evidence, locus, proposed tier, proposed fix. Per card the
human picks:

- **approve** — and may *adjust the tier* (`broad→local→knob-only` or up). Records
  `status=approved` + the approved tier.
- **suppress** — appends the fingerprint to `suppressions.yaml` with a reason.
- **defer** — leave as `new`.

Human-only: small file writes (status + suppressions), no code changes, no agent.

**Remediation runner** (`eval/monitor/remediate.py`) — dispatches a **subagent** per
approved card with a brief built mechanically from the card: issue, evidence, locus,
approved tier, and a **file/symbol allowlist derived from the tier**:

- `knob-only` → declared knobs only: prompt constants in `explore_llm.py`, threshold/param
  constants, `config`, ontology dimensions, eval cases.
- `local` → knobs + single-function edits inside the locus file.
- `broad` → wider, but scoped to the files the diagnosis named.

**Tier is enforced, not requested.** After the subagent finishes on its branch, the runner
**validates the diff against the allowlist**. A diff that exceeds the approved tier is
**rejected** (`status=needs-review`), not merged. The system **cannot self-escalate
scope**: if `knob-only` is insufficient, the agent reports back (`status=blocked`, "needs
`local`") and waits for a fresh GATE 1 approval — it gets one bounded attempt at the scope
the human set, and asks rather than grinds. This is the structural answer to "the LLM
fixating on a non-issue / sprawling."

**Isolation.** Each remediation runs on its own `monitor/<id>` branch/worktree (the project
already uses worktrees), so the main checkout is untouched until merge and concurrent fixes
never collide.

**Fix discipline (TDD).** The subagent first confirms the issue *reproduces* (the failing
eval/assertion from the card), makes the change, then confirms the eval *improves* and the
suite stays green. No green delta → no PR.

**Failure handling** (all report back; none grind or sprawl):

- can't fix within tier → `blocked`, suggests a higher tier, awaits re-triage;
- diff exceeds tier → `needs-review`, nothing proceeds;
- eval doesn't improve / tests fail → `failed` with evidence, no PR;
- bounded retry budget (default 2) so it cannot loop indefinitely.

---

## 7. Testing the fix + grounded judge

**Two bars before a PR opens:**

1. **Eval delta — full sweep.** Re-run the K-sampled eval on the fix branch vs baseline:
   the targeted metric on the targeted case **must improve past the trigger threshold**,
   AND **every other case/metric must not regress**. The whole-sweep comparison is
   deliberate — it kills the "fixed A, dented B" whack-a-mole that prompt/threshold tweaks
   invite.
2. **Suite.** `pytest` (48 files, strict markers) stays green.

**Grounded judge** (`eval/monitor/judge.py`) — the new detector/scorer. For each authored
specific claim, an LLM judge (Vertex) checks *is this claim entailed by a retrieved span?*
→ `supported / unsupported / contradicted`, yielding the **unsupported-specific rate** per
board. Detection uses it to *raise* hallucination issues; remediation uses it to *score*
whether a fix reduced them. The judge is treated as an instrument:

- *Grounded* — judges claim-vs-span, never free recall (avoids the critic's correlated
  blind spot).
- *Conservative* — only *flags*, never edits a board; a false positive costs a human glance,
  never a silent deletion.
- *Audited* — every verdict cites the span it judged against.
- *Calibrated* — a small labeled fixture (claims with known supported/unsupported labels)
  measures the judge's own accuracy, so its rate carries error bars. This is the concrete
  realization of "test the probability of an LLM achieving a task": the judge *is* that
  probe, calibrated before it is trusted.

---

## 8. GATE 2 artifact + closing the loop

The runner opens a PR on branch `monitor/<id>`. The body is auto-composed to answer exactly
"is this sound?":

- link to the issue card (the *why*);
- the diff (the *what* — tier-bounded, so small);
- **before/after eval-delta table** (targeted ↑, all-cases no-regression, K-sample spread);
- **grounded-judge summary** (unsupported rate before/after + which claims changed status);
- pytest result;
- **tier-compliance line** (diff stayed inside the approved allowlist).

CI runs as the usual independent check. The human merges or rejects.

- **On merge:** `baseline.json` advances to the new metrics; card → `merged`. The loop
  closes — next week measures against the raised bar.
- **On reject:** branch abandoned; card → `deferred`/closed; optionally suppress the
  fingerprint if it is deemed a non-issue.

---

## 9. Error handling & fail-safe posture

A broken monitor must produce **nothing**, never bad cards:

- detection-run failure (engine error, Vertex down) → no cards, logged run-record, baseline
  untouched;
- judge unavailable → coverage/flicker lanes still run; hallucination lane skipped with a
  note (graceful degradation, mirroring the engine's own design);
- a case that errors mid-build → flagged separately, **never counted as a regression** (a
  crash ≠ a quality drop).

---

## 10. Testing the monitor itself

Pure functions, tested offline with fixtures (no live LLM), matching the engine's `*_fn`
injection discipline:

- detectors (coverage-drop, unsupported-specific, flicker) over synthetic `RunArtifacts`;
- fingerprint stability + suppression filtering;
- tier→allowlist derivation and **diff-validation** (in-tier accepted, out-of-tier
  rejected);
- eval-delta comparison (targeted-up + no-collateral-regression logic);
- baseline read/advance semantics.

Live parts (the judge, real builds) are injected and mockable.

---

## 11. File / module layout

```
eval/monitor/
  __init__.py
  contracts.py        # RunArtifacts, Evidence, Issue, Detector Protocol
  detect.py           # scheduled entry: build ×K, run detectors, write cards
  detectors/
    coverage_drop.py
    unsupported_specific.py
    flicker.py
  judge.py            # grounded entailment judge (+ calibration fixture loader)
  suppress.py         # suppressions.yaml load + fingerprint filter
  triage.py           # GATE 1 CLI
  remediate.py        # subagent dispatch, tier allowlist, diff-validation, PR open
  baseline.json       # last known-good metrics (advanced only on merge)
  suppressions.yaml   # {fingerprint, reason, date, expires?}
  issues/             # <id>.json cards + digest.md
tests/eval/monitor/   # offline unit tests with fixtures
```

---

## 12. Success criteria

- A weekly run produces a digest of evidence-backed, deduped, role-attributed issue cards
  with zero false positives from flicker (K-sampling validated against a known-noisy case).
- Suppressing a fingerprint prevents recurrence until the signal worsens.
- An approved `knob-only` fix that an agent tries to implement out-of-tier is **rejected** by
  diff-validation (tested).
- A merged fix advances `baseline.json` and is not re-raised next run.
- The grounded judge's accuracy is reported with error bars from the calibration fixture.
- New `detect.py`/`remediate.py`/contracts/judge are covered by offline unit tests; the
  engine and existing eval scaffolding are reused unchanged.

---

## 13. Deferred / future

- **Code-health detectors** (test-failure, exception, perf) — implement the same `Detector`
  interface against `RunArtifacts.test_results`/`logs`.
- **Approach 3 upgrade** — persisted issue store (SQLite) with lifecycle, cross-run trend
  metrics, and a triage dashboard — added only if git-as-state proves insufficient.
- **Pre-merge CI gate** — optionally run a fast subset of detectors as a PR check, once the
  detectors are trusted.
