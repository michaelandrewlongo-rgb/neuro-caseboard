"""Single import surface for the external ``corpus_topology`` package.

``corpus_topology`` ships outside CasePrep at ``~/corpus_clustering``. This
module owns the optional import and the ``sys.path`` fallback so the rest of
the codebase never touches them. Callers ask ``is_available()`` first and
either call the wrapper functions or skip the semantic path.

When the package or its data files cannot be loaded, every wrapper raises the
same :class:`TopologyUnavailable` exception (re-exported from the underlying
module when present, locally defined when not).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_CORPUS_CLUSTERING_DEFAULT = Path("~/corpus_clustering").expanduser()


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    override = os.environ.get("CORPUS_CLUSTERING_PATH", "").strip()
    if override:
        paths.append(Path(override).expanduser())
    paths.append(_CORPUS_CLUSTERING_DEFAULT)
    return paths


def _ensure_on_sys_path() -> None:
    for candidate in _candidate_paths():
        candidate_str = str(candidate)
        if candidate.exists() and candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)


_ensure_on_sys_path()

try:
    import corpus_topology as _corpus_topology  # type: ignore
    _AVAILABLE = True
    TopologyUnavailable = _corpus_topology.TopologyUnavailable
except ImportError:
    _corpus_topology = None
    _AVAILABLE = False

    class TopologyUnavailable(RuntimeError):
        """Local stand-in raised when ``corpus_topology`` is not installed."""


def is_available() -> bool:
    """Return True if ``corpus_topology`` was imported successfully."""
    return _AVAILABLE


def _require_module():
    if _corpus_topology is None:
        raise TopologyUnavailable(
            "corpus_topology module not importable. "
            "Ensure ~/corpus_clustering/ exists or set CORPUS_CLUSTERING_PATH."
        )
    return _corpus_topology


def locate_clusters(query: str, *, k: int = 5, min_confidence: str | None = None) -> dict[str, Any]:
    return _require_module().locate_clusters(query, k=k, min_confidence=min_confidence)


def papers_in_cluster(cluster_id: int, *, k: int = 20, order_by: str = "citation_count") -> list[dict[str, Any]]:
    return _require_module().papers_in_cluster(cluster_id, k=k, order_by=order_by)


def paper_neighbors(paper_id: str, *, k: int = 10) -> dict[str, Any]:
    return _require_module().paper_neighbors(paper_id, k=k)


def get_paper(paper_id: str) -> dict[str, Any] | None:
    return _require_module().get_paper(paper_id)


def cluster_info(cluster_id: int) -> dict[str, Any] | None:
    return _require_module().cluster_info(cluster_id)


def list_clusters() -> list[dict[str, Any]]:
    return _require_module().list_clusters()


__all__ = [
    "TopologyUnavailable",
    "cluster_info",
    "get_paper",
    "is_available",
    "list_clusters",
    "locate_clusters",
    "paper_neighbors",
    "papers_in_cluster",
]
