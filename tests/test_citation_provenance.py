"""Regression guards for citation provenance interaction (BACKLOG P5 #14).

Behavioral logic is covered by vitest (web/src/lib/provenance.test.ts via `npm test`); CI is
pytest-only, so these static checks lock in clickable, provenance-distinct, jump-to-source markers."""
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web" / "src"


def test_provenance_distinguishes_three_origins():
    src = (WEB / "lib" / "provenance.ts").read_text()
    for kind in ('"textbook"', '"literature"', '"card"'):
        assert kind in src, kind
    assert "classifyMarker" in src and "splitCitations" in src


def test_citation_pills_are_clickable_jump_anchors():
    src = (WEB / "lib" / "citations.tsx").read_text()
    assert "splitCitations" in src                 # uses the pure classifier
    assert "href={`#${anchor}`}" in src            # clickable jump-to-source
    assert "PROVENANCE_LABEL[kind]" in src         # hover/aria provenance label


def test_source_lists_have_matching_jump_targets():
    sources = (WEB / "components" / "ask" / "SourcesList.tsx").read_text()
    literature = (WEB / "components" / "ask" / "LiteratureBlock.tsx").read_text()
    assert "src-textbook-${c.n}" in sources         # textbook anchor target
    assert "src-literature-${c.n}" in literature     # literature anchor target


def test_provenance_has_vitest_spec():
    assert (WEB / "lib" / "provenance.test.ts").exists()
