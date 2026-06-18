# Eval monitor — detection core (Milestone 1)

Unattended detection sweep. Builds each eval case K times, scores must_cover
coverage against `baseline.json`, and writes issue cards + `issues/digest.md`.
Read-only with respect to the engine: it never modifies the pipeline.

Run manually:

    python3 -m eval.monitor.detect --k 3

Schedule weekly (local cron — must run where the corpus + Vertex ADC live, so
detection can build boards):

    # crontab -e
    0 6 * * 1 cd /home/michael/PROJECTS/neuro-caseboard && python3 -m eval.monitor.detect >> eval/monitor/cron.log 2>&1

Triage by reading `eval/monitor/issues/digest.md`. To mute a known non-issue,
add its fingerprint (printed on the card) to `suppressions.yaml`:

    - fingerprint: <16-hex from the card>
      reason: why this is not worth fixing
      expires: 2026-12-31   # optional; omit for a permanent mute

A muted issue auto-resurfaces if it worsens (its fingerprint changes when the
set of missing items changes).

## Scope (this milestone)

Detection only. Triage UX, the grounded hallucination judge, and the
autonomous remediation runner (with blast-radius enforcement + the two human
gates) are later milestones — see
`docs/superpowers/specs/2026-06-18-eval-monitor-loop-design.md`.
