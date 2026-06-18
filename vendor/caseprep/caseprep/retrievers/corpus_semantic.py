"""Embedding-based corpus retriever (BioBERT clusters via ``corpus_topology``).

Parallels :class:`caseprep.retrievers.corpus.CorpusRetriever` (which is FTS5
keyword search). Both return :class:`EvidenceRecord` and are intended to run
in parallel inside the core builder, with dedup keyed on PMID / DOI / title.

When ``corpus_topology`` or its data files are unavailable, ``retrieve``
returns ``[]`` instead of raising — the builder always emits a warning when
zero records come back from a configured retriever, so silent skipping is
visible without breaking the run.
"""

from __future__ import annotations

import logging
from typing import Any

from caseprep.core import CasePrepExternalServiceError, EvidenceRecord
from caseprep.integrations import corpus_topology as topology

logger = logging.getLogger(__name__)


def _coerce_paper_id(value: Any) -> str:
    return str(value or "").strip()


def _paper_to_record(
    paper: dict[str, Any],
    *,
    cluster_id: int,
    cluster_name: str | None,
    cluster_cosine: float,
    cluster_confidence: str,
) -> EvidenceRecord | None:
    paper_id = _coerce_paper_id(paper.get("id"))
    if not paper_id:
        return None
    title = str(paper.get("title") or "").strip()
    text = str(paper.get("abstract") or "").strip()
    metadata: dict[str, Any] = {
        "retrieval_source": "corpus_semantic",
        "semantic_cluster_id": cluster_id,
        "semantic_cluster_name": cluster_name,
        "semantic_cluster_cosine": round(float(cluster_cosine), 4),
        "semantic_confidence": cluster_confidence,
        "corpus_paper_id": paper_id,
    }
    for key in ("year", "primary_domain", "citation_count"):
        if paper.get(key) is not None:
            metadata[key] = paper[key]
    # ``corpus_topology`` paper IDs are openalex-style work IDs ("W…") or PMID
    # strings ("pmid-12345"); expose the bare PMID when present so dedup keys
    # match PubMed-sourced records.
    lowered = paper_id.casefold()
    if lowered.startswith("pmid-"):
        metadata.setdefault("pmid", paper_id.split("-", 1)[1])
    record_id = f"corpus-sem-{paper_id}"
    return EvidenceRecord(
        id=record_id,
        source="corpus",
        title=title,
        text=text,
        metadata=metadata,
    )


class SemanticCorpusRetriever:
    """Embedding-based parallel to :class:`CorpusRetriever`.

    Strategy: embed the query, take the top ``max_clusters`` BioBERT-derived
    clusters, draw up to ``papers_per_cluster`` papers from each, and return
    them flattened (capped at ``top_n``). The cluster confidence/cosine is
    attached to each record's metadata.
    """

    def __init__(
        self,
        *,
        max_clusters: int = 3,
        papers_per_cluster: int = 5,
        min_confidence: str = "low",
    ) -> None:
        self._max_clusters = max_clusters
        self._papers_per_cluster = papers_per_cluster
        self._min_confidence = min_confidence

    def retrieve(
        self,
        query: str,
        *,
        subdomain: str | None = None,  # accepted for protocol symmetry; unused
        top_n: int = 8,
    ) -> list[EvidenceRecord]:
        del subdomain  # subdomain mapping is FTS5-only; clusters are global
        if not topology.is_available():
            return []
        cleaned_query = (query or "").strip()
        if not cleaned_query:
            return []
        try:
            located = topology.locate_clusters(
                cleaned_query,
                k=self._max_clusters,
                min_confidence=self._min_confidence,
            )
        except topology.TopologyUnavailable as exc:
            raise CasePrepExternalServiceError(
                "Semantic corpus unavailable",
                details={"provider": "corpus_semantic", "cause": str(exc)},
            ) from exc
        except Exception as exc:
            raise CasePrepExternalServiceError(
                "Semantic corpus error",
                details={"provider": "corpus_semantic", "cause": str(exc)},
            ) from exc

        clusters = located.get("top") or []
        if not clusters:
            return []
        confidence = str(located.get("confidence") or "low")

        records: list[EvidenceRecord] = []
        seen_paper_ids: set[str] = set()
        for cluster in clusters:
            if len(records) >= top_n:
                break
            cluster_id = int(cluster.get("cluster_id"))
            cluster_name = cluster.get("name")
            cluster_cosine = float(cluster.get("cosine") or 0.0)
            try:
                papers = topology.papers_in_cluster(
                    cluster_id, k=self._papers_per_cluster
                )
            except topology.TopologyUnavailable as exc:
                logger.warning("papers_in_cluster failed for %s: %s", cluster_id, exc)
                continue
            except Exception as exc:
                logger.warning("papers_in_cluster error for %s: %s", cluster_id, exc)
                continue
            for paper in papers:
                paper_id = _coerce_paper_id(paper.get("id"))
                if not paper_id or paper_id in seen_paper_ids:
                    continue
                record = _paper_to_record(
                    paper,
                    cluster_id=cluster_id,
                    cluster_name=cluster_name,
                    cluster_cosine=cluster_cosine,
                    cluster_confidence=confidence,
                )
                if record is None:
                    continue
                seen_paper_ids.add(paper_id)
                records.append(record)
                if len(records) >= top_n:
                    break
        return records


__all__ = ["SemanticCorpusRetriever"]
