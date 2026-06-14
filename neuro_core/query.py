from dataclasses import dataclass, field

from .config import load_config
from .embed import Embedder
from .index import Index, reciprocal_rank_fusion
from .rerank import Reranker
from .synthesize import synthesize, is_refusal
from .synth_clients import make_synth_client
from .gpu_guard import ensure_gpu_ready
from .visual_embed import VisualEmbedder
from .visual_index import VisualIndex
from .caption_index import CaptionIndex


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
                 synth_fn=synthesize, visual_embedder=None, visual_index=None,
                 caption_index=None):
        self.config = config
        self.embedder = embedder
        self.index = index
        self.reranker = reranker
        self.synth_client = synth_client
        self.synth_fn = synth_fn
        self.visual_embedder = visual_embedder
        self.visual_index = visual_index
        self.caption_index = caption_index

    def _visual_hits(self, question):
        if not (self.config.visual_retrieval and self.visual_embedder is not None
                and self.visual_index is not None):
            return []
        try:
            qv = self.visual_embedder.embed_query(question)
            return self.visual_index.image_search(qv, self.config.visual_retrieve_k)
        except Exception:
            # The visual lane is an enhancement; a runtime failure (model load,
            # OOM) must never break the worded answer — fall back to text-only.
            return []

    def _caption_hits(self, question):
        # caption_index first: if no lane is wired, it's off regardless of config (and we must
        # not touch a config that predates the caption_retrieval flag).
        if self.caption_index is None or not getattr(self.config, "caption_retrieval", False):
            return []
        try:
            return self.caption_index.caption_search(question, self.config.caption_retrieve_k)
        except Exception:
            return []      # enhancement lane: never break the answer

    def _collect_figures(self, question, top):
        """Return aligned (figures, images): RRF-fuse figure-bearing text hits with
        visual-lane hits (keyed by figure_path), dedupe, cap, assign citation source
        numbers (reuse a passage number if the page is cited, else append), and read
        bytes (dropping unreadable PNGs from BOTH lists)."""
        text_fig = [h for h in top if h.has_figure and h.figure_path]
        visual = self._visual_hits(question)
        caption = self._caption_hits(question)

        by_path = {}
        for h in visual:        # later lanes win metadata on overlap
            if h.figure_path:
                by_path[h.figure_path] = h
        for h in text_fig:
            if h.figure_path:
                by_path[h.figure_path] = h
        for h in caption:       # caption lane carries the richer (Gemini) caption
            if h.figure_path:
                by_path[h.figure_path] = h

        # Dedup each lane by figure_path (preserving best rank) BEFORE fusing: a
        # multi-chunk figure page yields several hits with the same path, which
        # would otherwise inflate its RRF score once per chunk and bias toward
        # text-dense pages — the exact effect the visual lane exists to counter.
        fused = reciprocal_rank_fusion([
            list(dict.fromkeys(h.figure_path for h in text_fig if h.figure_path)),
            list(dict.fromkeys(h.figure_path for h in visual if h.figure_path)),
            list(dict.fromkeys(h.figure_path for h in caption if h.figure_path)),
        ])

        passage_index = {}
        for i, h in enumerate(top, 1):
            passage_index.setdefault((h.book, h.page), i)

        figures, images = [], []
        next_appended = len(top) + 1
        for path, _score in fused:
            if len(figures) >= self.config.max_figure_images:
                break
            h = by_path.get(path)
            if h is None:
                continue
            image = self._read_image(path)
            if image is None:
                continue
            src = passage_index.get((h.book, h.page))
            if src is None:
                src = next_appended
                next_appended += 1
            # Prefer the richer (Gemini) caption for display when available, even for a
            # figure surfaced by the text or visual lane.
            cap = h.caption or ""
            if self.caption_index is not None:
                cap = self.caption_index.caption_by_path.get(path, cap)
            figures.append(Figure(source_n=src, book=h.book,
                                  chapter=h.chapter or "", page=h.page,
                                  image_path=path, caption=cap))
            images.append(image)
        return figures, images

    @staticmethod
    def _read_image(path):
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None

    def _retrieve(self, question):
        qv = self.embedder.embed_query(question)
        hits = self.index.hybrid_search(question, qv, self.config.retrieve_k)
        return self.reranker.rerank(question, hits, self.config.rerank_k)

    def select_figures(self, question):
        """Figures the system would attach, without calling synthesis (for eval)."""
        figures, _ = self._collect_figures(question, self._retrieve(question))
        return figures

    def query(self, question):
        top = self._retrieve(question)
        figures, images = self._collect_figures(question, top)
        syn = self.synth_fn(question, top, figures, images, self.synth_client)
        if is_refusal(syn.answer):
            # Synthesis found nothing relevant. The figures and citations were
            # collected from retrieval independently of the answer, so on a refusal
            # they are spurious — drop both rather than show sources/plates that
            # don't support a "Not found" answer.
            return QueryResult(answer=syn.answer, citations=[], figures=[])
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
    visual_embedder = None
    visual_index = None
    if config.visual_retrieval:
        try:
            visual_index = VisualIndex(config.index_dir)
            visual_embedder = VisualEmbedder(config.visual_model,
                                             device=config.embed_device)
        except Exception:
            visual_index = None
            visual_embedder = None
    caption_index = None
    if config.caption_retrieval:
        try:
            caption_index = CaptionIndex(config.index_dir)
        except Exception:
            caption_index = None
    _engine = Engine(config, embedder, index, reranker, synth_client,
                     visual_embedder=visual_embedder, visual_index=visual_index,
                     caption_index=caption_index)
    return _engine


def query(question, config=None, force=False):
    config = config or load_config()
    if config.synth_provider == "local" and config.gpu_guard:
        ensure_gpu_ready(config, force=force)
    return get_engine(config).query(question)
