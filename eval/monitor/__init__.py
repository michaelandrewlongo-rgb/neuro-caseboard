"""Eval monitor — scheduled detection of build-pathway output-quality regressions.

Milestone 1 (this package) is detection-only and read-only with respect to the
engine: it builds boards via the existing pipeline, scores them, and writes
evidence-backed issue cards. See docs/superpowers/specs/2026-06-18-eval-monitor-loop-design.md.
"""
