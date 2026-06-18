"""Tests for the SemanticCorpusRetriever and corpus_topology adapter.

The adapter import is always available (it owns its own optional-import
fallback), so we test it directly. The retriever has unit tests against a
fake topology, plus a smoke test gated on the real ``corpus_topology``
package being importable.
"""

from __future__ import annotations

from typing import Any

import pytest

from caseprep.integrations import corpus_topology as topology
from caseprep.retrievers.corpus_semantic import SemanticCorpusRetriever


class _FakeTopology:
    """In-process stand-in for ``corpus_topology``."""

    available = True
    TopologyUnavailable = topology.TopologyUnavailable

    def __init__(self, *, clusters: list[dict[str, Any]], papers: dict[int, list[dict[str, Any]]]):
        self._clusters = clusters
        self._papers = papers

    def is_available(self) -> bool:
        return self.available

    def locate_clusters(self, query, *, k, min_confidence=None):
        return {
            "query": query,
            "confidence": "high",
            "best_cosine": self._clusters[0]["cosine"] if self._clusters else 0.0,
            "top": list(self._clusters)[:k],
        }

    def papers_in_cluster(self, cluster_id, *, k=20, order_by="citation_count"):
        return self._papers.get(int(cluster_id), [])[:k]


@pytest.fixture
def fake_topology(monkeypatch):
    fake = _FakeTopology(
        clusters=[
            {"cluster_id": 7, "name": "thrombectomy outcomes", "cosine": 0.93},
            {"cluster_id": 18, "name": "stroke imaging", "cosine": 0.88},
        ],
        papers={
            7: [
                {"id": "W1", "title": "HERMES pooled analysis", "abstract": "…", "year": 2016, "primary_domain": "Medicine", "citation_count": 2000},
                {"id": "pmid-9999", "title": "MR CLEAN trial", "abstract": "…", "year": 2015, "primary_domain": "Medicine", "citation_count": 3000},
            ],
            18: [
                {"id": "W2", "title": "CT perfusion in LVO", "abstract": "…", "year": 2020, "primary_domain": "Medicine", "citation_count": 100},
            ],
        },
    )

    import caseprep.retrievers.corpus_semantic as module
    monkeypatch.setattr(module, "topology", fake)
    return fake


def test_semantic_retriever_returns_records_from_top_clusters(fake_topology):
    retriever = SemanticCorpusRetriever(max_clusters=2, papers_per_cluster=3)
    records = retriever.retrieve("M1 LVO thrombectomy", top_n=8)
    assert [r.id for r in records] == ["corpus-sem-W1", "corpus-sem-pmid-9999", "corpus-sem-W2"]
    assert all(r.metadata["retrieval_source"] == "corpus_semantic" for r in records)
    assert records[0].metadata["semantic_cluster_id"] == 7
    assert records[0].metadata["semantic_cluster_cosine"] == pytest.approx(0.93)
    # pmid-prefixed IDs should also expose the bare PMID for dedup against PubMed.
    assert records[1].metadata["pmid"] == "9999"


def test_semantic_retriever_respects_top_n(fake_topology):
    retriever = SemanticCorpusRetriever(max_clusters=2, papers_per_cluster=3)
    records = retriever.retrieve("M1 LVO", top_n=2)
    assert len(records) == 2


def test_semantic_retriever_returns_empty_when_unavailable(monkeypatch):
    import caseprep.retrievers.corpus_semantic as module

    class _Unavailable:
        TopologyUnavailable = topology.TopologyUnavailable

        def is_available(self):
            return False

    monkeypatch.setattr(module, "topology", _Unavailable())
    retriever = SemanticCorpusRetriever()
    assert retriever.retrieve("anything", top_n=5) == []


def test_semantic_retriever_empty_query_returns_empty(fake_topology):
    retriever = SemanticCorpusRetriever()
    assert retriever.retrieve("   ", top_n=5) == []


# ── Smoke test against the real corpus_topology package ─────────────────────


@pytest.mark.skipif(not topology.is_available(), reason="corpus_topology not installed")
def test_real_corpus_topology_smoke():
    """End-to-end check that the adapter can drive the real package.

    Skipped when corpus_topology or its data files are not present. We only
    verify that ``locate_clusters`` returns the documented shape — not that
    it returns specific clusters (the corpus may evolve).
    """
    try:
        located = topology.locate_clusters("thrombectomy m1 large vessel occlusion", k=2)
    except topology.TopologyUnavailable as exc:
        pytest.skip(f"corpus_topology data not loadable: {exc}")
    assert isinstance(located, dict)
    assert "top" in located
    assert "confidence" in located
    assert "best_cosine" in located
