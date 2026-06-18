"""Provenance: the LLM-vs-deterministic source flag carried on every Dossier."""

import json

import pytest

from neuro_caseboard.model import (
    Dossier, EvidenceSummary, Provenance, FALLBACK_BANNER, fallback_notice,
)


def test_provenance_defaults_are_benign():
    p = Provenance()
    assert p.degraded is False
    assert p.source_label  # non-empty human label
    assert fallback_notice(p) is None


def test_fallback_notice_only_when_degraded():
    assert fallback_notice(Provenance(source="deterministic", degraded=True)) == FALLBACK_BANNER
    assert fallback_notice(Provenance(source="llm_generated", degraded=False)) is None


def test_dossier_has_default_provenance():
    d = Dossier(title="t", summary=EvidenceSummary())
    assert isinstance(d.provenance, Provenance)
    assert d.provenance.degraded is False


def test_compile_dossier_threads_provenance():
    from neuro_caseboard.compile import compile_dossier
    from caseprep.audit.card_auditor import AuditedCard, AuditedManifest

    card = AuditedCard(question="A concrete operative step", why_it_matters="w",
                       target_file="04-operative-plan.md", section_key="critical_steps",
                       compiler_slot="Critical Steps", answerability="needs_patient_fact",
                       audit_status="no_evidence")
    audited = AuditedManifest(procedure_family="deterministic", cards=[card])
    prov = Provenance(source="deterministic", degraded=True, reason="llm_error", detail="RuntimeError")
    d = compile_dossier(audited, topic="acdf", provenance=prov)
    assert d.provenance is prov
    # default path still works (no provenance passed -> benign default)
    d2 = compile_dossier(audited, topic="acdf")
    assert d2.provenance.degraded is False
