from __future__ import annotations

from eval.monitor.fingerprint import fingerprint


def test_fingerprint_is_stable():
    a = fingerprint("coverage_drop", "author", "itemA|itemB")
    b = fingerprint("coverage_drop", "author", "itemA|itemB")
    assert a == b
    assert len(a) == 16


def test_fingerprint_changes_when_signature_worsens():
    base = fingerprint("coverage_drop", "author", "itemA|itemB")
    worse = fingerprint("coverage_drop", "author", "itemA|itemB|itemC")
    assert base != worse


def test_fingerprint_normalizes_whitespace_and_case():
    assert fingerprint("k", "l", "Item A") == fingerprint("k", "l", "item   a")
