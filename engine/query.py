from dataclasses import dataclass, field

from .config import load_config
from .embed import Embedder
from .index import Index
from .rerank import Reranker
from .synthesize import synthesize
from .synth_clients import make_synth_client


@dataclass
class Figure:
    source_n: int
    book: str
    chapter: str
    page: int
    image_path: str
    caption: str


@dataclass
class QueryResult:
    answer: str
    citations: list = field(default_factory=list)
    figures: list = field(default_factory=list)


class Engine:
    def __init__(self, config, embedder, index, reranker, synth_client,
                 synth_fn=synthesize):
        self.config = config
        self.embedder = embedder
        self.index = index
        self.reranker = reranker
        self.synth_client = synth_client
        self.synth_fn = synth_fn

    def _collect_figures(self, hits):
        """Return aligned (figures, images) for figure-bearing top hits, deduped
        by path and capped by max_figure_images. A figure whose PNG can't be read
        is dropped from BOTH lists rather than crashing the query."""
        figures = []
        images = []
        seen = set()
        for i, h in enumerate(hits, 1):
            if len(figures) >= self.config.max_figure_images:
                break
            if not (h.has_figure and h.figure_path) or h.figure_path in seen:
                continue
            seen.add(h.figure_path)
            image = self._read_image(h.figure_path)
            if image is None:
                continue
            figures.append(Figure(source_n=i, book=h.book,
                                  chapter=h.chapter or "", page=h.page,
                                  image_path=h.figure_path, caption=h.caption or ""))
            images.append(image)
        return figures, images

    @staticmethod
    def _read_image(path):
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None

    def query(self, question):
        qv = self.embedder.embed_query(question)
        hits = self.index.hybrid_search(question, qv, self.config.retrieve_k)
        top = self.reranker.rerank(question, hits, self.config.rerank_k)
        figures, images = self._collect_figures(top)
        syn = self.synth_fn(question, top, figures, images, self.synth_client)
        return QueryResult(answer=syn.answer, citations=syn.citations,
                           figures=figures)


_engine = None


def get_engine(config=None):
    global _engine
    if _engine is not None:
        return _engine
    config = config or load_config()
    embedder = Embedder(config.embed_model, device=config.embed_device)
    index = Index(config.index_dir)
    reranker = Reranker(config.rerank_model, device=config.embed_device)
    synth_client = make_synth_client(config)
    _engine = Engine(config, embedder, index, reranker, synth_client)
    return _engine


def query(question, config=None):
    return get_engine(config).query(question)
