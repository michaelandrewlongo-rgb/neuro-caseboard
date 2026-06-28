"""Tests for api.server._probe_synth across synth providers.

Regression for PR #80: the default synth flipped to openrouter (glm-5.2), but the health
probe only knew how to check vertex and reported the now-default provider as unavailable
(which would fail the health-gated CD rollout for a glm deployment). Client modules
(openai / google.genai) are optional extras absent in the required `.[dev]` CI env, so the
tests inject fake modules to exercise the import check deterministically.
"""

import sys
import types

import api.server as server


def _cfg(**kw):
    base = dict(synth_provider="vertex", google_cloud_project="",
                openrouter_api_key="", local_base_url="")
    base.update(kw)
    return types.SimpleNamespace(**base)


def _patch_config(monkeypatch, cfg):
    monkeypatch.setattr("neuro_core.config.load_config", lambda: cfg)


def test_probe_synth_openrouter_available(monkeypatch):
    _patch_config(monkeypatch, _cfg(synth_provider="openrouter", openrouter_api_key="sk-test"))
    monkeypatch.setitem(sys.modules, "openai", types.ModuleType("openai"))
    info = server._probe_synth()
    assert info["provider"] == "openrouter"
    assert info["client_import"] is True
    assert info["available"] is True


def test_probe_synth_openrouter_missing_key(monkeypatch):
    _patch_config(monkeypatch, _cfg(synth_provider="openrouter", openrouter_api_key=""))
    monkeypatch.setitem(sys.modules, "openai", types.ModuleType("openai"))
    info = server._probe_synth()
    assert info["available"] is False
    assert "OPENROUTER_API_KEY" in (info["detail"] or "")


def test_probe_synth_local_available(monkeypatch):
    _patch_config(monkeypatch, _cfg(synth_provider="local",
                                    local_base_url="http://localhost:11434/v1"))
    monkeypatch.setitem(sys.modules, "openai", types.ModuleType("openai"))
    info = server._probe_synth()
    assert info["provider"] == "local"
    assert info["available"] is True


def test_probe_synth_vertex_unchanged(monkeypatch):
    # The refactor must preserve the existing vertex behavior.
    _patch_config(monkeypatch, _cfg(synth_provider="vertex", google_cloud_project="proj"))
    monkeypatch.setattr(server, "_adc_present", lambda: True)
    monkeypatch.setitem(sys.modules, "google", types.ModuleType("google"))
    monkeypatch.setitem(sys.modules, "google.genai", types.ModuleType("google.genai"))
    info = server._probe_synth()
    assert info["provider"] == "vertex"
    assert info["available"] is True
