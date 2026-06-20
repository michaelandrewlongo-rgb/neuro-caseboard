"""Regression guards for the Build quantitative outcome summary (BACKLOG P5 #15).

Behavioral logic is covered by vitest (web/src/lib/quant.test.ts via `npm test`); CI is pytest-only,
so these static checks lock in a "By the numbers" outcome summary derived from dossier claims."""
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web" / "src"


def test_quant_extractor_present_and_pure():
    src = (WEB / "lib" / "quant.ts").read_text()
    assert "export function extractMetrics" in src
    assert "export function summarizeDossier" in src
    # the kinds the dossier summary surfaces
    for kind in ('"percent"', '"count"', '"interval"', '"pvalue"', '"duration"', '"ratio"'):
        assert kind in src, kind


def test_dossier_view_renders_quant_summary_from_claims():
    src = (WEB / "components" / "build" / "DossierView.tsx").read_text()
    assert "summarizeDossier" in src
    assert "By the numbers" in src
    # derived from the dossier's own claims (no fabrication)
    assert "s.claims.map" in src


def test_quant_has_vitest_spec():
    assert (WEB / "lib" / "quant.test.ts").exists()
