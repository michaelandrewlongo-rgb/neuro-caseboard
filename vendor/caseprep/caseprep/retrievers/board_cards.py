"""Board-cards retriever: semantic search over ABNS flashcards via BioBERT + pgvector.

Delegates the heavy lifting (embedding + DB query) to
``docker exec corpus_pipeline_api python3 /app/scripts/search_board_cards.py``
so that the caseprep venv does not need PyTorch or sentence-transformers.

Returns :class:`BoardCardRecord` objects, which are lighter than full
:class:`EvidenceRecord` — they carry question/answer/tags/similarity, not
bibliographic metadata.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# How long to wait for the embedding + search subprocess
_TIMEOUT_SECONDS = 120


@dataclass
class BoardCardRecord:
    """One ABNS board card hit."""

    id: str
    deck: str
    question: str
    answer: str
    tags: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    similarity: float = 0.0


class BoardCardRetriever:
    """Semantic retriever for board knowledge cards.

    Delegates embedding and pgvector search to the corpus_pipeline_api
    container (which has the BioBERT model and DB access).
    """

    def __init__(
        self,
        *,
        top_n: int = 5,
        script_path: str = "/app/scripts/search_board_cards.py",
        docker_cmd: str = "docker.exe",
        container: str = "corpus_pipeline_api",
    ) -> None:
        self.top_n = top_n
        self._script_path = script_path
        self._docker_cmd = docker_cmd
        self._container = container

    def _is_available(self) -> bool:
        """Check whether the docker container is reachable."""
        try:
            result = subprocess.run(
                [self._docker_cmd, "exec", self._container, "true"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def retrieve(
        self,
        query: str,
        *,
        top_n: int | None = None,
        source: str = "Liles_Longo_ABNS_Board_Review",
    ) -> list[BoardCardRecord]:
        """Search board cards by semantic similarity to *query*.

        Returns an empty list if the container is unreachable or the search
        fails — callers should handle gracefully.
        """
        if not self._is_available():
            logger.warning("BoardCardRetriever: container %s not reachable", self._container)
            return []

        cleaned = (query or "").strip()
        if not cleaned:
            return []

        n = top_n if top_n is not None else self.top_n
        cmd = [
            self._docker_cmd, "exec",
            "-e", "HF_HUB_DISABLE_PROGRESS_BARS=1",
            "-e", "TOKENIZERS_PARALLELISM=false",
            self._container,
            "python3", self._script_path,
            cleaned,
            "--top", str(n),
            "--source", source,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            logger.warning("BoardCardRetriever: timed out after %ds", _TIMEOUT_SECONDS)
            return []
        except Exception as exc:
            logger.warning("BoardCardRetriever: subprocess error: %s", exc)
            return []

        if result.returncode != 0:
            logger.warning("BoardCardRetriever: non-zero exit %d: %s", result.returncode, result.stderr[:500])
            return []

        # Parse JSON from stdout; stderr may contain HF warnings (ignored)
        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning("BoardCardRetriever: failed to parse JSON output")
            return []

        if not isinstance(raw, list):
            logger.warning("BoardCardRetriever: unexpected output shape: %s", type(raw))
            return []

        records: list[BoardCardRecord] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            records.append(BoardCardRecord(
                id=item.get("id", ""),
                deck=item.get("deck", ""),
                question=item.get("question", ""),
                answer=item.get("answer", ""),
                tags=item.get("tags", []),
                concepts=item.get("concepts", []),
                similarity=float(item.get("similarity", 0)),
            ))
        return records


__all__ = ["BoardCardRecord", "BoardCardRetriever"]
